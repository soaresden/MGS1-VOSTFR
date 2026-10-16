#!/usr/bin/env python3
"""
combine.py - « CD Combiner » : les 2 disques de MGS1 PS1 en une seule image BIN/CUE (émulateurs).

  python combine.py disque1.bin disque2.bin [sortie.bin]

Entrées : deux images déjà construites par build.py (VOSTFR, VF ou EN, avec ou sans options),
dans n'importe quel ordre (le disque est reconnu par MGS1.EXE / MGS2.EXE). Sortie par défaut :
« <nom du disque 1 sans (Disc 1)> (1 CD).bin » à côté du disque 1.

Pourquoi le son change : une position CD est un MSF en BCD (99:59:74 au plus = 449 849 secteurs,
DuckStation refuse au-delà) et les deux disques font ~1,17 Go. Les voix (VOX.DAT) passent de
22 050 à 11 025 Hz (mono), les cinématiques (DEMO.DAT) de 33 075 à 22 050 Hz (stéréo) : ~990 Mo.
Image pour émulateurs seulement (trop grande pour un CD-R).

Étapes, pour chaque disque :
1. VOX.DAT / DEMO.DAT : chaque banque est refaite (spuadpcm : décodage, filtre entier, réencodage),
   en-tête 0x02 (taille audio, fréquence SPU 0x400 / 0x800), nouveaux blocs 0x01 de 8192 octets
   (stéréo : 4096 gauche + 4096 droite) placés à la place des anciens (bloc j à la place de
   l'ancien bloc ⌊j·down/up⌋), les autres blocs inchangés et dans le même ordre ; banques
   recollées alignées sur 2048. Table ancien secteur de début -> nouveau.
2. Codes : RADIO.DAT (commandes VOICE, radio.scan) et scripts GCX de STAGE.DIR (gcx.codes)
   renumérotés ; stage « sound » (test sonore) : codes du disque 2 sur les deux disques.
3. EXE (MGS1.EXE et MGS2.EXE, FR et UK, retrouvés par motifs) : répertoire « MGS » ou « MGS2 »
   selon FS_DiskNum, reset logiciel -> MGS1.EXE, pilote de flux : fréquence 0x400 à la place
   de 0xC00 (une interruption sur quatre).
4. Overlays abst / title / change / demosel de STAGE.DIR : pas d'attente du capot, FS_DiskNum
   = disque voulu avant la relecture des fichiers (FS_ResetCdFilePosition).
Image : secteurs 0 à 202 du disque 1 (zone système, descripteurs, tables des chemins, racine
modifiée : MGS2 ajouté, DUMMY3M.DAT retiré), fichiers du disque 1 dans MGS/, répertoire MGS2/
et fichiers du disque 2 (BRF.DAT / FACE.DAT identiques : partagés), 150 secteurs de fin.
"""

import struct, sys, time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

import gcx, psxiso, radio, spuadpcm, vox
from cdsector import SECTOR, fix_form1
from isorebuild import copy_raw, form1_sectors, set_msf

EXE_LOAD = 0x80010000
LIMIT = 449850 - 150                      # dernier secteur adressable : 99:59:74
TARGETS = {"VOX.DAT": (1, 2, 0x400), "DEMO.DAT": (2, 3, 0x800)}   # (up, down, fréquence SPU)
OVB = {0x800AE1D8: 0x800C47D8, 0x800ADC48: 0x800C4248}            # FS_DiskNum -> overlays (FR, UK)
AUDIO, HEAD, END = 0x01, 0x02, 0xF0


# ---- son ---------------------------------------------------------------------------------------

def block(code, data):
    return bytes([code]) + (len(data) + 4).to_bytes(3, "little") + data


def shrink_bank(bank, up, down, freq):
    """Banque VOX / DEMO -> même banque avec le son rééchantillonné (sans alignement final)."""
    blocks = list(vox.blocks(bank, 0))
    heads = [b for b in blocks if b[0] == HEAD]
    if not heads:
        return bank
    assert len(heads) == 1, "plusieurs flux audio dans une banque"
    _, hoff, hsize = heads[0]
    head = bytearray(bank[hoff + 4:hoff + hsize])
    stereo = head[8] != 1
    audio = [b for b in blocks if b[0] == AUDIO]
    raw = b"".join(bank[o + 4:o + s] for _, o, s in audio)
    # la taille annoncée (head[0:4]) n'est pas vérifiée : la banque 127 du disque 2 FR annonce 8192
    # octets de plus que ses blocs (erreur d'origine) ; la nouvelle taille est celle des données
    chunks = [raw[i:i + 4096] for i in range(0, len(raw), 4096)]
    chans = [b"".join(chunks[0::2]), b"".join(chunks[1::2])] if stereo else [raw]
    enc = []
    for ch in chans:
        ch = ch[:len(ch) // 16 * 16]
        y = spuadpcm.resample(spuadpcm.decode(ch), up, down)
        nb = (len(y) + 27) // 28
        if stereo:
            nb = (nb + 255) // 256 * 256
        y = np.concatenate([y, np.zeros(nb * 28 - len(y), np.int64)])
        flags = [2] * nb
        flags[-1] = ch[-15] if ch else 2
        enc.append(spuadpcm.encode(y, flags))
    new = b"".join(enc[0][i:i + 4096] + enc[1][i:i + 4096] for i in range(0, len(enc[0]), 4096)) \
        if stereo else enc[0]
    nblocks = [new[i:i + 8192] for i in range(0, len(new), 8192)]
    struct.pack_into(">I", head, 0, len(new))
    struct.pack_into(">H", head, 6, freq)
    out, a, j = bytearray(), 0, 0
    for code, off, size in blocks:
        if code == AUDIO:
            while j < len(nblocks) and (j * down) // up <= a:
                out += block(AUDIO, nblocks[j])
                j += 1
            a += 1
            if a == len(audio):
                while j < len(nblocks):
                    out += block(AUDIO, nblocks[j])
                    j += 1
        elif code == HEAD:
            out += block(HEAD, bytes(head))
        else:
            out += bank[off:off + size]
    return bytes(out)


def _shrink_task(args):
    return shrink_bank(*args)


def shrink_files(jobs, pool):
    """jobs : [(données, nom)] -> [(nouvelles données, {ancien secteur de banque: nouveau})]."""
    tasks, spans = [], []
    for data, name in jobs:
        up, down, freq = TARGETS[name]
        bk = vox.banks(data)
        spans.append(bk)
        tasks += [(data[s:e], up, down, freq) for s, e in bk]
    res = iter(pool.imap(_shrink_task, tasks, chunksize=2))
    out = []
    for (data, name), bk in zip(jobs, spans):
        new, mp, pos = bytearray(), {}, 0
        for s, e in bk:
            new += data[pos:s]                     # entre deux banques (rien en pratique)
            mp[s // 2048] = len(new) // 2048
            new += next(res)
            new += bytes(-len(new) % 2048)
            pos = (e + 2047) // 2048 * 2048
        new += data[pos:]
        out.append((bytes(new), mp))
    return out


# ---- codes -------------------------------------------------------------------------------------

def renumber_radio(data, vmap):
    out, n, miss = bytearray(data), 0, 0
    for off, code, _ in radio.scan(data):
        if code in vmap:
            struct.pack_into(">I", out, off + 4, vmap[code])
            n += 1
        else:
            miss += 1
    return bytes(out), n, miss


def renumber_stage(st, vmap, dmap, sound_map):
    out = bytearray(st)
    n = {"vox": 0, "demo": 0, "sound": 0}
    for p, kind, name in gcx.codes(st, set(vmap), set(dmap)):
        if name != "sound":
            v = struct.unpack_from(">I", st, p + 1)[0]
            struct.pack_into(">I", out, p + 1, (vmap if kind == "vox" else dmap)[v])
            n[kind] += 1
    for p, kind, name in gcx.codes(st, set(sound_map), set()):
        if name == "sound" and kind == "vox":
            v = struct.unpack_from(">I", st, p + 1)[0]
            struct.pack_into(">I", out, p + 1, sound_map[v])
            n["sound"] += 1
    return bytes(out), n


# ---- EXE ---------------------------------------------------------------------------------------

def _w(b, i):
    return struct.unpack_from("<I", b, i)[0]


def _put(b, i, w):
    struct.pack_into("<I", b, i, w)


def _target(w, at):
    """Cible d'un branchement conditionnel (w à l'adresse at)."""
    off = (w & 0xFFFF) - ((w & 0x8000) << 1)
    return at + 4 + 4 * off


def exe_info(exe):
    """FS_DiskNum et FS_ResetCdFilePosition (motifs du reset logiciel et de FS_CDInit)."""
    fs = reset = None
    for i in range(0x800, len(exe) - 20, 4):
        if _w(exe, i) == 0x3C058001 and _w(exe, i + 4) == 0x24A50ACC and _w(exe, i + 8) in (0x00021080, 0x00001021):
            hi, lo = _w(exe, i - 8), _w(exe, i - 4)
            assert hi >> 16 == 0x3C02 and lo >> 16 == 0x8C42
            fs = ((hi & 0xFFFF) << 16) + (lo & 0xFFFF) - ((lo & 0x8000) << 1)
        if _w(exe, i) == 0x3C048011 and _w(exe, i + 4) >> 26 == 3 and _w(exe, i + 8) == 0x34847000:
            reset = 0x80000000 | (_w(exe, i + 4) & 0x3FFFFFF) << 2
    assert fs and reset, "EXE non reconnu"
    return fs, reset


def patch_exe(exe):
    """Retouches de l'EXE (idempotent : un EXE déjà patché est renvoyé tel quel)."""
    exe = bytearray(exe)
    fs, _ = exe_info(exe)
    addr = lambda i: EXE_LOAD + i - 0x800
    off = lambda a: a - EXE_LOAD + 0x800
    # chaîne "MGS read_sector %d\n" (printf retiré ci-dessous) -> "MGS2"
    s = off(0x800105F8)
    if exe[s:s + 5] == b"MGS2\0":
        return bytes(exe)
    assert exe[s - 4:s + 20] == b"MGS\0MGS read_sector %d\n\0", "chaîne MGS introuvable"
    exe[s:s + 5] = b"MGS2\0"
    # 1. FS_CdMakePositionTable : nom du répertoire = "MGS" + 4·FS_DiskNum
    hits = [i for i in range(0x800, len(exe) - 80, 4)
            if _w(exe, i) == 0x27A40010 and _w(exe, i + 4) == 0x3C058001 and _w(exe, i + 8) == 0x24A505F4
            and _w(exe, i + 64) == 0x3C048001 and _w(exe, i + 68) == 0x248405F8]
    assert len(hits) == 1
    i = hits[0]
    w = [_w(exe, i + 4 * k) for k in range(20)]
    assert w[12] >> 26 == 3 and w[13] == 0x00C28825 and w[14] >> 16 == 0x1440 and w[15] == 0x32420001
    bnez_to = _target(w[14], addr(i + 56))
    hi, lo = (fs + 0x8000) >> 16 & 0xFFFF, fs & 0xFFFF
    new = [w[0], 0x3C010000 | hi, 0x8C280000 | lo] + w[3:11] + \
          [0x00084080, 0x3C058001, 0x00A82821, 0x24A505F4, w[11], w[12], w[13],
           0x14400000 | ((bnez_to - addr(i + 72) - 4) // 4 & 0xFFFF), w[15]]
    for k, x in enumerate(new):
        _put(exe, i + 4 * k, x)
    # 2. reset logiciel : toujours MGS_DiskName[0] (MGS1.EXE, dans MGS/)
    i = next(i for i in range(0x800, len(exe) - 12, 4)
             if _w(exe, i) == 0x3C058001 and _w(exe, i + 4) == 0x24A50ACC and _w(exe, i + 8) == 0x00021080)
    _put(exe, i + 8, 0x00001021)                       # sll v0,v0,2 -> addu v0,zero,zero
    # 3. UserSpuIRQProc : case 0xC00 (3 interruptions sur 4) -> case 0x400 (1 sur 4)
    a = [i for i in range(0x800, len(exe) - 8, 4)
         if _w(exe, i) == 0x24020C00 and _w(exe, i + 4) >> 16 in (0x1062, 0x1462)]
    assert len(a) == 2 and _w(exe, a[0] + 4) >> 16 == 0x1062 and _w(exe, a[1] + 4) >> 16 == 0x1462
    p800 = off(_target(_w(exe, a[0] - 8), addr(a[0] - 8)))
    pc00 = off(_target(_w(exe, a[0] + 4), addr(a[0] + 4)))
    tail = pc00 + 20
    assert [_w(exe, p800 + 8), _w(exe, p800 + 12), _w(exe, p800 + 20)] == [0, 0x24430001, 0x30420001]
    assert _w(exe, p800 + 16) == 0x08000000 | (addr(tail) >> 2 & 0x3FFFFFF)
    assert [_w(exe, pc00 + 8), _w(exe, pc00 + 12), _w(exe, pc00 + 16)] == [0, 0x24430001, 0x30420003]
    lui_at = _w(exe, tail)
    assert lui_at >> 16 == 0x3C01 and _w(exe, tail + 4) >> 16 == 0xAC23 and _w(exe, tail + 8) >> 16 == 0x1040
    _put(exe, a[0], 0x24020400)
    _put(exe, a[1], 0x24020400)
    _put(exe, p800 + 8, lui_at)                                    # nop -> lui at (délai du lw)
    _put(exe, p800 + 16, 0x08000000 | (addr(tail + 4) >> 2 & 0x3FFFFFF))
    _put(exe, pc00 + 8, lui_at)
    _put(exe, tail, 0x2C420001)                                    # sltiu v0,v0,1
    return bytes(exe)


# ---- overlays ----------------------------------------------------------------------------------

def patch_overlays(st, fs, reset, ovb):
    """abst / title / change / demosel : pas de capot, FS_DiskNum = disque voulu."""
    st = bytearray(st)
    hi, lo = (fs + 0x8000) >> 16 & 0xFFFF, fs & 0xFFFF
    jal = 0x0C000000 | (reset & 0x3FFFFFF) >> 2
    done = []
    for name, a, _ in gcx.stage_table(st):
        if name not in ("abst", "title", "change", "demosel"):
            continue
        _, mode, ext, size = struct.unpack_from("<HBBi", st, a + 4)
        assert (chr(mode), chr(ext)) == ("s", "b")
        base = a + 2048
        n = size // 4
        w = list(struct.unpack_from(f"<{n}I", st, base))
        calls = [k for k in range(n) if w[k] == jal]
        assert len(calls) == 1, name
        c = calls[0]
        k = c - 7
        if w[k] >> 16 == 0x3C01 or w[k] >> 16 == 0x8E28:       # déjà patché
            done.append(name)
            continue
        assert w[k] >> 16 == 0x3C04 and w[k + 1] >> 16 == 0x2484 and w[k + 2] >> 26 == 3 and w[k + 3] == 0 \
            and w[k + 4] >> 26 == 3 and w[k + 5] == 0x24042000, f"{name} : motif"
        if name == "abst":                                       # FS_DiskNum = disc_no - 1
            dn = next(x for x in w[c:c + 8] if x >> 16 == 0x8E26)   # lw a2,disc_no(s1)
            code = [0x8E280000 | dn & 0xFFFF, 0x3C010000 | hi, 0x2508FFFF, 0xAC280000 | lo]
        elif name == "change":                                   # disque 2
            code = [0x3C010000 | hi, 0x24080001, 0xAC280000 | lo, 0]
        else:                                                    # disque 1
            code = [0x3C010000 | hi, 0xAC200000 | lo, 0, 0]
        w[k:k + 4] = code
        # table de sauts des 11 états : 0-5 -> état 6 (CdlGetTN), sans CdlStop ni capot
        tabs = []
        for i in range(n - 5):
            if w[i] >> 16 == 0x3C01 and w[i + 1] == 0x00220821 and w[i + 2] >> 16 == 0x8C22 and w[i + 4] == 0x00400008 \
                    and any(x >> 26 == 11 and x & 0xFFFF == 11 for x in w[max(0, i - 8):i]):
                t = ((w[i] & 0xFFFF) << 16) + (w[i + 2] & 0xFFFF) - ((w[i + 2] & 0x8000) << 1)
                e = (t - ovb) // 4
                if 0 <= e <= n - 11 and w[e + 8] <= ovb + 4 * c < w[e + 9]:
                    tabs.append(e)
        assert len(tabs) == 1, f"{name} : table"
        e = tabs[0]
        w[e:e + 6] = [w[e + 6]] * 6
        struct.pack_into(f"<{n}I", st, base, *w)
        done.append(name)
    assert sorted(done) == ["abst", "change", "demosel", "title"], done
    return bytes(st)


# ---- image -------------------------------------------------------------------------------------

def _dir_records(sec):
    out, i = [], 0
    while i < 2048 and sec[i]:
        ln, nl = sec[i], sec[i + 32]
        out.append((i, ln, sec[i + 33:i + 33 + nl].split(b";")[0]))
        i += ln
    return out


def _root(d):
    return struct.unpack_from("<I", d.sector(16), 158)[0]


def _mgs_dir(d):
    sec = d.sector(_root(d))
    i = next(i for i, ln, nm in _dir_records(sec) if nm == b"MGS")
    return struct.unpack_from("<I", sec, i + 2)[0]


def _set_extent(sec, i, lba, size):
    struct.pack_into("<I", sec, i + 2, lba)
    struct.pack_into(">I", sec, i + 6, lba)
    struct.pack_into("<I", sec, i + 10, size)
    struct.pack_into(">I", sec, i + 14, size)


def _form1(raw, data, lba):
    """Secteur brut raw (sous-en-tête gardé) avec de nouvelles données, à la position lba."""
    s = np.frombuffer(raw, np.uint8).reshape(1, SECTOR).copy()
    s[0, 24:24 + 2048] = np.frombuffer(bytes(data).ljust(2048, b"\0"), np.uint8)
    set_msf(s, lba)
    return fix_form1(s).tobytes()


def write_image(discs, files, out_bin):
    """discs : (Disc 1, Disc 2) ; files : ({chemin MGS/...: données | None (copie brute)}, idem)."""
    d1, d2 = discs
    f1, f2 = d1.files(), d2.files()
    root_lba = _root(d1)
    first = min(l for p, (l, s) in f1.items() if p.startswith("MGS/"))
    mgsdir, mgsdir2 = _mgs_dir(d1), _mgs_dir(d2)
    # disposition
    order1 = sorted((p for p in f1 if p.startswith("MGS/")), key=lambda p: f1[p][0])
    order2 = sorted((p for p in f2 if p.startswith("MGS/")), key=lambda p: f2[p][0])
    size = lambda d, f, p, fl: len(f[p]) if f[p] is not None else fl[p][1]
    pos, place = first, {}
    for p in order1:
        n = size(d1, files[0], p, f1)
        place[1, p] = (pos, n)
        pos += max(1, (n + 2047) // 2048)
    dir2 = pos
    pos += 1
    for p in order2:
        n = size(d2, files[1], p, f2)
        same = p in ("MGS/BRF.DAT", "MGS/FACE.DAT") and files[1][p] is None and files[0][p] is None \
            and d1.read(*f1[p]) == d2.read(*f2[p])
        if same:
            place[2, p] = place[1, p]
            continue
        place[2, p] = (pos, n)
        pos += max(1, (n + 2047) // 2048)
    tail = 150
    total = pos + tail
    assert total - 1 <= LIMIT + 150, f"image trop grande : {total} secteurs (max {LIMIT + 150})"
    with open(out_bin, "wb") as out:
        # zone système + descripteurs + répertoires + SYSTEM.CNF + SLES (identiques sauf retouches)
        copy_raw(d1.f, out, 0, first, 0)
        for k, (d, f, fl, order) in enumerate(((d1, files[0], f1, order1), (d2, files[1], f2, order2)), 1):
            if k == 2:
                out.write(b"\0" * SECTOR)                       # répertoire MGS2 (écrit plus bas)
            for p in order:
                lba, n = place[k, p]
                if out.tell() // SECTOR != lba:
                    continue                                    # fichier partagé
                slba, ssize = fl[p]
                nsec = max(1, (ssize + 2047) // 2048)
                if f[p] is None:
                    copy_raw(d.f, out, slba, nsec, lba)
                else:
                    for chunk in form1_sectors(f[p], lba, d.raw(slba)[16:20], d.raw(slba + nsec - 1)[16:20]):
                        out.write(chunk)
        last = d1.nsectors - tail
        copy_raw(d1.f, out, last, tail, total - tail)
        assert out.tell() == total * SECTOR
    # répertoires et descripteur
    with open(out_bin, "r+b") as out:
        def put(lba, data, raw):
            out.seek(lba * SECTOR)
            out.write(_form1(raw, data, lba))

        def fix_dir(sec, k, fl, self_lba):
            sec = bytearray(sec)
            for i, ln, nm in _dir_records(sec):
                p = "MGS/" + nm.decode("latin1")
                if nm == b"\x00":
                    _set_extent(sec, i, self_lba, 2048)
                elif nm == b"\x01":
                    _set_extent(sec, i, root_lba, 2048)
                elif (k, p) in place:
                    _set_extent(sec, i, *place[k, p])
            return sec

        put(mgsdir, fix_dir(d1.sector(mgsdir), 1, f1, mgsdir), d1.raw(mgsdir))
        put(dir2, fix_dir(d2.sector(mgsdir2), 2, f2, dir2), d2.raw(mgsdir2))
        # racine : DUMMY3M.DAT retiré, MGS2 ajouté après MGS
        rsec = d1.sector(root_lba)
        recs = []
        for i, ln, nm in _dir_records(rsec):
            if nm == b"DUMMY3M.DAT":
                continue
            recs.append(bytes(rsec[i:i + ln]))
            if nm == b"MGS":
                r = bytearray(rsec[i:i + 33]) + b"MGS2\0" + rsec[i + 36:i + ln]
                r[0], r[32] = len(r), 4
                _set_extent(r, 0, dir2, 2048)
                recs.append(bytes(r))
        put(root_lba, b"".join(recs), d1.raw(root_lba))
        # tables des chemins (L petit-boutiste, M gros-boutiste, et leurs copies)
        pvd = bytearray(d1.sector(16))
        psize = struct.unpack_from("<I", pvd, 0x84)[0]
        for fld, little in ((0x8C, True), (0x90, True), (0x94, False), (0x98, False)):
            lba = struct.unpack_from("<I" if little else ">I", pvd, fld)[0]
            if not lba:
                continue
            pt = bytearray(d1.sector(lba)[:psize])
            j, ins = 0, None
            while j < len(pt):
                nl = pt[j]
                if pt[j + 8:j + 8 + nl] == b"MGS":
                    ins = j + 8 + nl + (nl & 1)
                j += 8 + nl + (nl & 1)
            e = bytearray(12)
            e[0] = 4
            struct.pack_into("<IH" if little else ">IH", e, 2, dir2, 1)
            e[8:12] = b"MGS2"
            pt = pt[:ins] + e + pt[ins:]
            put(lba, pt, d1.raw(lba))
        struct.pack_into("<I", pvd, 0x84, psize + 12)
        struct.pack_into(">I", pvd, 0x88, psize + 12)
        struct.pack_into("<I", pvd, 80, total)
        struct.pack_into(">I", pvd, 84, total)
        put(16, pvd, d1.raw(16))
    return total


# ---- disques -----------------------------------------------------------------------------------

def disc_number(d):
    names = d.files()
    return 1 if "MGS/MGS1.EXE" in names else 2 if "MGS/MGS2.EXE" in names else None


def combine(a, b, out_bin, log=print):
    t0 = time.time()
    discs = {}
    for p in (a, b):
        d = psxiso.Disc(p)
        n = disc_number(d)
        assert n and n not in discs, f"{p} : disque non reconnu ou en double"
        discs[n] = d
    d1, d2 = discs[1], discs[2]
    rd = lambda d, name: d.read(*d.files()["MGS/" + name])
    exes = {1: "MGS1.EXE", 2: "MGS2.EXE"}
    fs, reset = exe_info(rd(d1, exes[1]))
    assert exe_info(rd(d2, exes[2])) == (fs, reset), "les deux disques ne sont pas de la même version"
    ovb = OVB[fs]
    log(f"Version {'France' if fs == 0x800AE1D8 else 'Europe (anglais)'}")
    log("Son : voix 22 -> 11 kHz, cinématiques 33 -> 22 kHz...")
    with Pool() as pool:
        res = shrink_files([(rd(discs[n], f), f) for n in (1, 2) for f in ("VOX.DAT", "DEMO.DAT")], pool)
    (vox1, vm1), (demo1, dm1), (vox2, vm2), (demo2, dm2) = res
    log(f"  {time.time() - t0:.0f} s ; VOX {len(rd(d1, 'VOX.DAT')) >> 20}+{len(rd(d2, 'VOX.DAT')) >> 20} -> "
        f"{len(vox1) >> 20}+{len(vox2) >> 20} Mo, DEMO {len(rd(d1, 'DEMO.DAT')) >> 20}+{len(rd(d2, 'DEMO.DAT')) >> 20} -> "
        f"{len(demo1) >> 20}+{len(demo2) >> 20} Mo")
    files = []
    for n, d, vx, dm, vm, dmm in ((1, d1, vox1, demo1, vm1, dm1), (2, d2, vox2, demo2, vm2, dm2)):
        radio_new, nr, miss = renumber_radio(rd(d, "RADIO.DAT"), vm)
        st, cnt = renumber_stage(rd(d, "STAGE.DIR"), vm, dmm, vm2)
        st = patch_overlays(st, fs, reset, ovb)
        log(f"Disque {n} : RADIO.DAT {nr} codes ({miss} hors banque), STAGE.DIR {cnt['vox']} voix, "
            f"{cnt['demo']} cinématiques, {cnt['sound']} test sonore")
        fl = {p: None for p in d.files() if p.startswith("MGS/")}
        fl.update({"MGS/VOX.DAT": vx, "MGS/DEMO.DAT": dm, "MGS/RADIO.DAT": radio_new, "MGS/STAGE.DIR": st,
                   "MGS/" + exes[n]: patch_exe(rd(d, exes[n]))})
        files.append(fl)
    total = write_image((d1, d2), files, out_bin)
    out_bin = Path(out_bin)
    out_bin.with_suffix(".cue").write_text(
        f'FILE "{out_bin.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n', encoding="ascii")
    log(f"Image -> {out_bin.name} : {total} secteurs ({total * SECTOR / 1e6:.0f} Mo, "
        f"max {LIMIT + 150}), {time.time() - t0:.0f} s")
    return total


def default_name(disc1):
    p = Path(disc1)
    return p.with_name(p.stem.replace(" (Disc 1)", "").replace(" (Disc 2)", "") + " (1 CD).bin")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    a, b = sys.argv[1], sys.argv[2]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    if not out:
        one = a if disc_number(psxiso.Disc(a)) == 1 else b
        out = default_name(one)
    combine(a, b, out)


if __name__ == "__main__":
    main()
