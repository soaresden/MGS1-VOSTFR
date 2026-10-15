#!/usr/bin/env python3
"""
isorebuild.py - Reconstruit une image PS1 (BIN MODE2/2352) en remplaçant des fichiers.

Un fichier remplacé peut changer de taille : tout ce qui le suit sur le disque est décalé
d'autant de secteurs (secteurs bruts recopiés tels quels, XA Form 2 compris, seule
l'adresse MSF de l'en-tête change : ni l'EDC ni l'ECC du Mode 2 ne la couvrent). Puis les
enregistrements de répertoire ISO 9660 (LBA, taille) et la taille du volume sont réécrits,
avec EDC/ECC recalculés.

Le jeu retrouve ses fichiers par nom au démarrage (FS_CdMakePositionTable) : aucun LBA en
dur à corriger. Les répertoires doivent se trouver avant le premier fichier qui bouge.
"""

import struct

import numpy as np

import psxiso
from cdsector import SECTOR, fix_form1

BATCH = 4096
SYNC = bytes([0] + [0xFF] * 10 + [0])


def bcd(x):
    return (x // 10) << 4 | x % 10


def msf(lba):
    x = lba + 150
    return bytes([bcd(x // 4500), bcd(x // 75 % 60), bcd(x % 75)])


def set_msf(sec, first_lba):
    """Adresses MSF d'un tableau (N, 2352) de secteurs consécutifs."""
    x = np.arange(first_lba, first_lba + len(sec)) + 150
    for col, v in ((12, x // 4500), (13, x // 75 % 60), (14, x % 75)):
        sec[:, col] = ((v // 10) << 4 | v % 10).astype(np.uint8)


def form1_sectors(data, first_lba, sub, sub_last):
    """Secteurs Mode 2 Form 1 complets pour data (aligné ou non sur 2048)."""
    n = max(1, (len(data) + 2047) // 2048)
    data = data.ljust(n * 2048, b"\0")
    for start in range(0, n, BATCH):
        k = min(BATCH, n - start)
        sec = np.zeros((k, SECTOR), np.uint8)
        sec[:, :12] = np.frombuffer(SYNC, np.uint8)
        sec[:, 15] = 2
        set_msf(sec, first_lba + start)
        sec[:, 16:20] = np.frombuffer(sub, np.uint8)
        sec[:, 20:24] = np.frombuffer(sub, np.uint8)
        if start + k == n:
            sec[-1, 16:20] = np.frombuffer(sub_last, np.uint8)
            sec[-1, 20:24] = np.frombuffer(sub_last, np.uint8)
        sec[:, 24:24 + 2048] = np.frombuffer(data[start * 2048:(start + k) * 2048], np.uint8).reshape(k, 2048)
        yield fix_form1(sec).tobytes()


def copy_raw(src, dst, lba, count, new_lba):
    """Recopie count secteurs bruts de lba vers new_lba (MSF réécrite si décalage)."""
    for start in range(0, count, BATCH):
        k = min(BATCH, count - start)
        src.seek((lba + start) * SECTOR)
        buf = src.read(k * SECTOR)
        if new_lba != lba:
            sec = np.frombuffer(buf, np.uint8).reshape(k, SECTOR).copy()
            set_msf(sec, new_lba + start)
            buf = sec.tobytes()
        dst.write(buf)


def changed_sectors(src, lba, data, dst_lba, out):
    """Fichier de même taille : ne recalcule que les secteurs modifiés."""
    n = (len(data) + 2047) // 2048
    data = data.ljust(n * 2048, b"\0")
    for start in range(0, n, BATCH):
        k = min(BATCH, n - start)
        src.seek((lba + start) * SECTOR)
        sec = np.frombuffer(src.read(k * SECTOR), np.uint8).reshape(k, SECTOR).copy()
        new = np.frombuffer(data[start * 2048:(start + k) * 2048], np.uint8).reshape(k, 2048)
        diff = np.any(sec[:, 24:24 + 2048] != new, axis=1)
        if dst_lba != lba:
            set_msf(sec, dst_lba + start)
        if diff.any():
            sec[diff, 24:24 + 2048] = new[diff]
            sec[diff] = fix_form1(sec[diff])
        out.write(sec.tobytes())


def dir_records(disc, lba, size):
    """[(lba_secteur, offset_dans_secteur, nom, lba, taille, est_dossier)]"""
    out = []
    for s in range((size + 2047) // 2048):
        data = disc.sector(lba + s)
        i = 0
        while i < 2048 and data[i]:
            ln = data[i]
            elba, esize = struct.unpack_from("<I", data, i + 2)[0], struct.unpack_from("<I", data, i + 10)[0]
            nlen = data[i + 32]
            name = data[i + 33:i + 33 + nlen].decode("ascii", "replace").split(";")[0]
            out.append((lba + s, i, name, elba, esize, bool(data[i + 25] & 2)))
            i += ln
    return out


def rebuild(src_bin, dst_bin, replace):
    """replace : {"MGS/VOX.DAT": données, ...}. Écrit dst_bin, renvoie {chemin: (lba, taille)}."""
    disc = psxiso.Disc(src_bin)
    files = disc.files()
    order = sorted(files.items(), key=lambda kv: kv[1][0])
    # nouvelles positions
    new, delta = {}, 0
    for path, (lba, size) in order:
        nsize = len(replace[path]) if path in replace else size
        new[path] = (lba + delta, nsize)
        delta += max(1, (nsize + 2047) // 2048) - max(1, (size + 2047) // 2048) if path in replace else 0
    first_move = min((lba for p, (lba, _) in files.items() if new[p][0] != lba), default=disc.nsectors)
    # répertoires (récursif depuis la racine)
    pvd = disc.sector(16)
    root = pvd[156:156 + 34]
    dirs, todo = [], [(struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0], "")]
    while todo:
        lba, size, prefix = todo.pop()
        if lba + (size + 2047) // 2048 > first_move:
            raise ValueError("un répertoire se trouve après un fichier déplacé")
        for rec in dir_records(disc, lba, size):
            dirs.append((prefix, rec))
            _, _, name, elba, esize, isdir = rec
            if isdir and name not in ("\x00", "\x01") and elba != lba:
                todo.append((elba, esize, f"{prefix}/{name}" if prefix else name))
    src = disc.f
    with open(dst_bin, "wb") as out:
        pos = 0
        for path, (lba, size) in order:
            if lba > pos:  # trou entre fichiers (descripteurs, répertoires...)
                copy_raw(src, out, pos, lba - pos, pos + (new[path][0] - lba))
            nsec = max(1, (size + 2047) // 2048)
            nlba, nsize = new[path]
            if path not in replace:
                copy_raw(src, out, lba, nsec, nlba)
            elif (nsize + 2047) // 2048 == nsec:
                changed_sectors(src, lba, replace[path], nlba, out)
            else:
                raw = disc.raw(lba)
                last = disc.raw(lba + nsec - 1)
                for chunk in form1_sectors(replace[path], nlba, raw[16:20], last[16:20]):
                    out.write(chunk)
            pos = lba + nsec
        if pos < disc.nsectors:  # fin du disque (postgap)
            copy_raw(src, out, pos, disc.nsectors - pos, pos + delta)
    # enregistrements de répertoire et taille du volume
    patches = {}

    def sector(lba):
        if lba not in patches:
            patches[lba] = bytearray(disc.sector(lba))
        return patches[lba]

    for prefix, (slba, off, name, elba, esize, isdir) in dirs:
        path = f"{prefix}/{name}" if prefix else name
        if isdir or path not in new:
            continue
        nlba, nsize = new[path]
        if (nlba, nsize) != (elba, esize):
            s = sector(slba)
            struct.pack_into("<I", s, off + 2, nlba)
            struct.pack_into(">I", s, off + 6, nlba)
            struct.pack_into("<I", s, off + 10, nsize)
            struct.pack_into(">I", s, off + 14, nsize)
    vol = struct.unpack_from("<I", pvd, 80)[0] + delta
    s = sector(16)
    struct.pack_into("<I", s, 80, vol)
    struct.pack_into(">I", s, 84, vol)
    with open(dst_bin, "r+b") as out:
        for lba, data in patches.items():
            out.seek(lba * SECTOR)
            sec = np.frombuffer(out.read(SECTOR), np.uint8).reshape(1, SECTOR).copy()
            sec[0, 24:24 + 2048] = np.frombuffer(bytes(data), np.uint8)
            out.seek(lba * SECTOR)
            out.write(fix_form1(sec).tobytes())
    return new
