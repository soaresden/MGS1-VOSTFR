#!/usr/bin/env python3
"""
chd2bin.py - Convertit un CHD v5 (CD) en BIN/CUE 2352 octets, sans chdman.

Codecs gérés : cdlz (LZMA + deflate), cdzl (deflate + deflate), cdfl non géré
(audio FLAC : inutile pour les disques de MGS qui n'ont qu'une piste de données).

Usage : python chd2bin.py jeu.chd sortie.bin
"""

import hashlib, lzma, struct, sys, zlib
from pathlib import Path

import numpy as np

from cdsector import fix_ecc

CD_FRAME = 2448          # 2352 de données + 96 de sous-code
CD_SECTOR = 2352
CD_SUB = 96
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


class Bits:
    """Lecture de bits MSB d'abord (comme bitstream.c de libchdr)."""

    def __init__(self, data):
        self.data, self.pos = data, 0

    def read(self, n):
        v = 0
        for _ in range(n):
            byte = self.data[self.pos >> 3] if (self.pos >> 3) < len(self.data) else 0
            v = (v << 1) | ((byte >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return v


class Huffman:
    def __init__(self, numcodes, maxbits, bits):
        numbits = 5 if maxbits >= 16 else 4 if maxbits >= 8 else 3
        lens, cur = [0] * numcodes, 0
        while cur < numcodes:
            nb = bits.read(numbits)
            if nb != 1:
                lens[cur] = nb; cur += 1
            else:
                nb = bits.read(numbits)
                if nb == 1:
                    lens[cur] = nb; cur += 1
                else:
                    rep = bits.read(numbits) + 3
                    for _ in range(rep):
                        lens[cur] = nb; cur += 1
        # codes canoniques
        histo = [0] * 33
        for l in lens:
            histo[l] += 1
        start = 0
        for cl in range(32, 0, -1):
            nxt = (start + histo[cl]) >> 1
            histo[cl] = start
            start = nxt
        self.codes = {}
        for sym, l in enumerate(lens):
            if l:
                self.codes[(l, histo[l])] = sym
                histo[l] += 1

    def decode(self, bits):
        code, l = 0, 0
        while True:
            code = (code << 1) | bits.read(1); l += 1
            if (l, code) in self.codes:
                return self.codes[(l, code)]
            if l > 32:
                raise ValueError("code Huffman invalide")


class CHD:
    def __init__(self, path):
        self.f = open(path, "rb")
        h = self.f.read(124)
        if h[:8] != b"MComprHD" or struct.unpack(">I", h[12:16])[0] != 5:
            raise ValueError("CHD v5 attendu")
        self.codecs = [h[16 + 4 * i:20 + 4 * i] for i in range(4)]
        self.logical, self.mapoff, self.metaoff = struct.unpack(">QQQ", h[32:56])
        self.hunkbytes, self.unitbytes = struct.unpack(">II", h[56:64])
        self.rawsha1 = h[64:84]
        self.hunkcount = (self.logical + self.hunkbytes - 1) // self.hunkbytes
        self._read_map()
        self.cache = {}

    def _read_map(self):
        f = self.f
        f.seek(self.mapoff)
        mh = f.read(16)
        mapbytes = struct.unpack(">I", mh[0:4])[0]
        firstoffs = int.from_bytes(mh[4:10], "big")
        lengthbits, selfbits, parentbits = mh[12], mh[13], mh[14]
        bits = Bits(f.read(mapbytes))
        huff = Huffman(16, 8, bits)
        comp, rep, last = [], 0, 0
        for _ in range(self.hunkcount):
            if rep > 0:
                comp.append(last); rep -= 1
                continue
            v = huff.decode(bits)
            if v == 7:      # RLE_SMALL
                comp.append(last); rep = 2 + huff.decode(bits)
            elif v == 8:    # RLE_LARGE
                comp.append(last)
                rep = 2 + 16 + (huff.decode(bits) << 4)
                rep += huff.decode(bits)
            else:
                comp.append(v); last = v
        self.map = []
        cur, last_self, last_parent = firstoffs, 0, 0
        for hn, c in enumerate(comp):
            length = offset = 0
            if c in (0, 1, 2, 3):
                length = bits.read(lengthbits); offset = cur; cur += length; bits.read(16)
            elif c == 4:    # NONE
                length = self.hunkbytes; offset = cur; cur += length; bits.read(16)
            elif c == 5:    # SELF
                offset = last_self = bits.read(selfbits)
            elif c == 6:    # PARENT
                offset = last_parent = bits.read(parentbits)
            elif c == 9:    # SELF_0
                c, offset = 5, last_self
            elif c == 10:   # SELF_1
                last_self += 1; c, offset = 5, last_self
            elif c in (11, 12, 13):
                raise ValueError("CHD avec parent non géré")
            self.map.append((c, offset, length))

    def hunk(self, hn):
        if hn in self.cache:
            return self.cache[hn]
        c, offset, length = self.map[hn]
        if c == 5:
            data = self.hunk(offset)
        elif c == 4:
            self.f.seek(offset); data = self.f.read(length)
        else:
            self.f.seek(offset)
            data = self._decomp_cd(self.codecs[c], self.f.read(length))
        if len(self.cache) > 64:
            self.cache.clear()
        self.cache[hn] = data
        return data

    def _decomp_cd(self, codec, src):
        frames = self.hunkbytes // CD_FRAME
        complen_bytes = 2 if self.hunkbytes < 65536 else 3
        ecc_bytes = (frames + 7) // 8
        hb = ecc_bytes + complen_bytes
        clen = int.from_bytes(src[ecc_bytes:hb], "big")
        if codec == b"cdlz":
            filt = [{"id": lzma.FILTER_LZMA1, "dict_size": 1 << 20, "lc": 3, "lp": 0, "pb": 2}]
            d = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=filt)
            base = d.decompress(src[hb:hb + clen], frames * CD_SECTOR)
        elif codec == b"cdzl":
            base = zlib.decompressobj(-15).decompress(src[hb:hb + clen])
        else:
            raise ValueError(f"codec {codec!r} non géré")
        sub = zlib.decompressobj(-15).decompress(src[hb + clen:]) if len(src) > hb + clen else b""
        sub = sub.ljust(frames * CD_SUB, b"\0")
        secs = np.frombuffer(base[:frames * CD_SECTOR], np.uint8).reshape(frames, CD_SECTOR).copy()
        # chdman retire synchro + ECC quand il sait les recalculer : on les régénère
        stripped = [i for i in range(frames) if src[i // 8] & (1 << (i % 8))]
        if stripped:
            secs[stripped, 0:12] = np.frombuffer(SYNC, np.uint8)
            secs[stripped] = fix_ecc(secs[stripped])
        subs = np.frombuffer(sub[:frames * CD_SUB], np.uint8).reshape(frames, CD_SUB)
        return np.concatenate([secs, subs], axis=1).tobytes()

    def metadata(self):
        out, off = [], self.metaoff
        while off:
            self.f.seek(off)
            mh = self.f.read(24)
            tag = mh[0:4]
            length = int.from_bytes(mh[5:8], "big")
            nxt = struct.unpack(">Q", mh[8:16])[0]
            out.append((tag, self.f.read(length).split(b"\0")[0].decode("ascii", "replace")))
            off = nxt
        return out


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    chd = CHD(src)
    tracks = [m for t, m in chd.metadata() if t in (b"CHT2", b"CHTR")]
    print(f"{src.name}: {chd.hunkcount} hunks, pistes: {tracks}")
    if len(tracks) != 1 or "MODE2_RAW" not in tracks[0] and "MODE1_RAW" not in tracks[0]:
        raise SystemExit("Seuls les disques à une piste de données sont gérés")
    nframes = int(tracks[0].split("FRAMES:")[1].split()[0])
    fph = chd.hunkbytes // CD_FRAME
    sha = hashlib.sha1()
    with open(dst, "wb") as out:
        for hn in range(chd.hunkcount):
            h = chd.hunk(hn)
            sha.update(h[:max(0, min(chd.hunkbytes, chd.logical - hn * chd.hunkbytes))])
            fr = hn * fph
            if fr >= nframes:
                continue
            for i in range(min(fph, nframes - fr)):
                out.write(h[i * CD_FRAME:i * CD_FRAME + CD_SECTOR])
            if hn % 2000 == 0:
                print(f"  {fr * 100 // nframes}%", flush=True)
    if sha.digest() != chd.rawsha1:
        raise SystemExit("ERREUR : le SHA-1 des données ne correspond pas au CHD")
    print("SHA-1 brut identique au CHD")
    mode = "MODE2/2352" if "MODE2" in tracks[0] else "MODE1/2352"
    dst.with_suffix(".cue").write_text(
        f'FILE "{dst.name}" BINARY\n  TRACK 01 {mode}\n    INDEX 01 00:00:00\n', encoding="ascii")
    print(f"OK -> {dst} ({nframes} secteurs)")


if __name__ == "__main__":
    main()
