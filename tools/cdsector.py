"""
cdsector.py - EDC/ECC des secteurs CD Mode 2 Form 1, vectorisé avec numpy.

Algorithme identique à ECM / cdrtools : EDC sur [0x10, 0x818), ECC P puis Q calculés
avec l'adresse (octets 12-15) mise à zéro, comme l'exige le Mode 2.
"""

import numpy as np

SECTOR = 2352


def _tables():
    f_lut = np.zeros(256, np.uint8)
    b_lut = np.zeros(256, np.uint8)
    edc = np.zeros(256, np.uint32)
    for i in range(256):
        j = ((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF
        f_lut[i] = j
        b_lut[i ^ j] = i
        e = i
        for _ in range(8):
            e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
        edc[i] = e
    return f_lut, b_lut, edc


F_LUT, B_LUT, EDC_LUT = _tables()


def _ecc_index(major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    idx = np.zeros((minor_count, major_count), np.int64)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        for minor in range(minor_count):
            idx[minor, major] = index
            index += minor_inc
            if index >= size:
                index -= size
    return idx


P_IDX = _ecc_index(86, 24, 2, 86)
Q_IDX = _ecc_index(52, 43, 86, 88)


def _ecc_block(src, idx):
    """src : (N, 2340) octets à partir de 0xC. Renvoie (N, 2*major_count)."""
    n = src.shape[0]
    a = np.zeros((n, idx.shape[1]), np.uint8)
    b = np.zeros((n, idx.shape[1]), np.uint8)
    for minor in range(idx.shape[0]):
        t = src[:, idx[minor]]
        a ^= t
        b ^= t
        a = F_LUT[a]
    a = B_LUT[F_LUT[a] ^ b]
    return np.concatenate([a, a ^ b], axis=1)


def fix_ecc(sectors):
    """Recalcule seulement l'ECC P/Q (adresse à zéro en Mode 2, telle quelle en Mode 1)."""
    mode2 = sectors[:, 15] == 2
    addr = sectors[:, 12:16].copy()
    sectors[mode2, 12:16] = 0
    sectors[:, 0x81C:0x8C8] = _ecc_block(sectors[:, 0xC:0xC + 2340], P_IDX)
    sectors[:, 0x8C8:0x930] = _ecc_block(sectors[:, 0xC:0xC + 2340], Q_IDX)
    sectors[:, 12:16] = addr
    return sectors


def fix_form1(sectors):
    """Recalcule EDC + ECC d'un tableau (N, 2352) de secteurs Mode 2 Form 1 (modifié en place)."""
    # EDC sur sous-en-tête + données
    e = np.zeros(sectors.shape[0], np.uint32)
    for k in range(0x10, 0x818):
        e = EDC_LUT[(e ^ sectors[:, k]) & 0xFF] ^ (e >> 8)
    sectors[:, 0x818:0x81C] = e.view(np.uint8).reshape(-1, 4)
    return fix_ecc(sectors)


def write_file_inplace(bin_path, lba, data, batch=4096):
    """Réécrit le contenu d'un fichier Form 1 à son LBA (même taille en secteurs)."""
    nsec = (len(data) + 2047) // 2048
    data = data.ljust(nsec * 2048, b"\0")
    with open(bin_path, "r+b") as f:
        for start in range(0, nsec, batch):
            n = min(batch, nsec - start)
            f.seek((lba + start) * SECTOR)
            sec = np.frombuffer(f.read(n * SECTOR), np.uint8).reshape(n, SECTOR).copy()
            if np.any(sec[:, 18] & 0x20):
                raise ValueError("secteur Form 2 dans un fichier Form 1")
            new = np.frombuffer(data[start * 2048:(start + n) * 2048], np.uint8).reshape(n, 2048)
            changed = np.any(sec[:, 24:24 + 2048] != new, axis=1)
            if not changed.any():
                continue
            sec[:, 24:24 + 2048] = new
            sec[changed] = fix_form1(sec[changed])
            f.seek((lba + start) * SECTOR)
            f.write(sec.tobytes())
