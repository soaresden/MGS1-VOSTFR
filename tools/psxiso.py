#!/usr/bin/env python3
"""
psxiso.py - Lecture d'une image PS1 BIN (MODE2/2352) : liste, extraction, vérification EDC.

  python psxiso.py list    disque.bin
  python psxiso.py extract disque.bin dossier_sortie
  python psxiso.py verify  disque.bin [pas]   (EDC d'un secteur sur [pas], 1 = tous)
"""

import struct, sys
from pathlib import Path

SECTOR = 2352


def _edc_table():
    t = []
    for i in range(256):
        e = i
        for _ in range(8):
            e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
        t.append(e)
    return t


EDC_TABLE = _edc_table()


def edc(data):
    e = 0
    for b in data:
        e = EDC_TABLE[(e ^ b) & 0xFF] ^ (e >> 8)
    return e


class Disc:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.nsectors = Path(path).stat().st_size // SECTOR

    def raw(self, lba):
        self.f.seek(lba * SECTOR)
        return self.f.read(SECTOR)

    def sector(self, lba):
        """Données utilisateur d'un secteur Mode 2 (2048 en Form 1, 2324 en Form 2)."""
        r = self.raw(lba)
        form2 = r[18] & 0x20
        return r[24:24 + (2324 if form2 else 2048)]

    def read(self, lba, size):
        out = bytearray()
        n = (size + 2047) // 2048
        self.f.seek(lba * SECTOR)
        buf = self.f.read(n * SECTOR)
        for i in range(n):
            out += buf[i * SECTOR + 24:i * SECTOR + 24 + 2048]
        return bytes(out[:size])

    def files(self):
        """{chemin: (lba, taille)} de tout le disque."""
        files = {}

        def walk(lba, size, prefix):
            data = self.read(lba, size)
            i = 0
            while i < len(data):
                ln = data[i]
                if ln == 0:
                    i = (i // 2048 + 1) * 2048
                    continue
                elba, esize = struct.unpack_from("<I", data, i + 2)[0], struct.unpack_from("<I", data, i + 10)[0]
                flags, nlen = data[i + 25], data[i + 32]
                name = data[i + 33:i + 33 + nlen].decode("ascii", "replace").split(";")[0]
                if name not in ("\x00", "\x01"):
                    path = f"{prefix}/{name}" if prefix else name
                    if flags & 2:
                        walk(elba, esize, path)
                    else:
                        files[path] = (elba, esize)
                i += ln

        pvd = self.read(16, 2048)
        root = pvd[156:156 + 34]
        walk(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")
        return files


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    d = Disc(path)
    if cmd == "list":
        for p, (lba, size) in sorted(d.files().items(), key=lambda x: x[1][0]):
            print(f"{lba:7d} {size:11d}  {p}")
    elif cmd == "extract":
        out = Path(sys.argv[3])
        for p, (lba, size) in d.files().items():
            dst = out / p
            dst.parent.mkdir(parents=True, exist_ok=True)
            d.f.seek(lba * SECTOR)
            form2 = d.raw(lba)[18] & 0x20 if size else 0
            if form2:
                # fichiers XA/STR : on garde les secteurs bruts 2352
                n = (size + 2047) // 2048
                d.f.seek(lba * SECTOR)
                dst.with_suffix(dst.suffix + ".raw2352").write_bytes(d.f.read(n * SECTOR))
            else:
                dst.write_bytes(d.read(lba, size))
            print(p)
    elif cmd == "verify":
        bad, step = 0, int(sys.argv[3]) if len(sys.argv) > 3 else 37
        for lba in range(0, d.nsectors, step):
            r = d.raw(lba)
            if r[15] != 2:
                continue
            if r[18] & 0x20:
                stored, calc = struct.unpack_from("<I", r, 2348)[0], edc(r[16:2348])
                if stored == 0:
                    continue
            else:
                stored, calc = struct.unpack_from("<I", r, 2072)[0], edc(r[16:2072])
            if stored != calc:
                bad += 1
                if bad < 10:
                    print(f"EDC faux secteur {lba}")
        print(f"{d.nsectors} secteurs, {bad} erreurs EDC")


if __name__ == "__main__":
    main()
