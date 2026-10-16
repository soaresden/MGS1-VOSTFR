#!/usr/bin/env python3
"""
spuadpcm.py - ADPCM du SPU (PS1) : décodage, encodage, rééchantillonnage.

Format : blocs de 16 octets = octet 0 (filtre << 4 | décalage), octet 1 (drapeaux de boucle),
14 octets = 28 échantillons de 4 bits (quartet bas d'abord). Filtres du SPU :
(0, 0), (60, 0), (115, -52), (98, -55), (122, -60) / 64.

L'encodeur choisit pour chaque bloc le filtre qui donne le plus petit écart maximal (prédiction
sur les échantillons d'origine), puis le plus petit décalage qui le contient, et quantifie en
suivant le décodeur (arrondi au plus proche). Il est déterministe : mêmes entrées, mêmes octets
(le portage JavaScript de la page doit refaire exactement les mêmes calculs).

Rééchantillonnage : par transformée de Fourier sur tout le flux (ratio exact, coupure nette
à la nouvelle fréquence de Nyquist avec une pente en cosinus sur les 5 % du haut).
"""

import numpy as np

F0 = (0, 60, 115, 98, 122)
F1 = (0, 0, -52, -55, -60)


def decode(raw):
    """raw : octets (multiple de 16). Renvoie un tableau int64 (28 échantillons par bloc)."""
    n = len(raw) // 16
    b = np.frombuffer(raw, np.uint8)[:n * 16].reshape(n, 16)
    shift = np.minimum(b[:, 0] & 15, 12).astype(np.int64)
    filt = np.minimum((b[:, 0] >> 4) & 7, 4)
    nib = np.empty((n, 28), np.int64)
    nib[:, 0::2] = b[:, 2:] & 15
    nib[:, 1::2] = b[:, 2:] >> 4
    nib = np.where(nib >= 8, nib - 16, nib)
    t = ((nib << 12) >> shift[:, None]).tolist()
    fl = filt.tolist()
    out = [0] * (n * 28)
    s1 = s2 = 0
    o = 0
    for k in range(n):
        f0, f1 = F0[fl[k]], F1[fl[k]]
        for v in t[k]:
            s = v + ((s1 * f0 + s2 * f1 + 32) >> 6)
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            out[o] = s
            o += 1
            s2, s1 = s1, s
    return np.array(out, np.int64)


def encode(x, flags):
    """x : échantillons (len = 28 × len(flags)), flags : octet 1 de chaque bloc."""
    n = len(flags)
    xs = np.asarray(x, np.int64).reshape(n, 28).tolist()
    out = bytearray(16 * n)
    s1 = s2 = 0
    for k in range(n):
        blk = xs[k]
        bm, bf = None, 0
        for f in range(5):
            f0, f1 = F0[f], F1[f]
            p1, p2, m = s1, s2, 0
            for v in blk:
                e = v - ((p1 * f0 + p2 * f1 + 32) >> 6)
                if e < 0:
                    e = -e
                if e > m:
                    m = e
                p2, p1 = p1, v
            if bm is None or m < bm:
                bm, bf = m, f
        sh = 12
        while sh > 0 and (bm >> (12 - sh)) > 7:
            sh -= 1
        f0, f1 = F0[bf], F1[bf]
        o = 16 * k
        out[o] = (bf << 4) | sh
        out[o + 1] = flags[k]
        q0 = 0
        for i, v in enumerate(blk):
            pred = (s1 * f0 + s2 * f1 + 32) >> 6
            q = (((v - pred) << sh) + 2048) >> 12
            if q > 7:
                q = 7
            elif q < -8:
                q = -8
            s = ((q << 12) >> sh) + pred
            if s > 32767:
                s = 32767
            elif s < -32768:
                s = -32768
            s2, s1 = s1, s
            if i & 1:
                out[o + 2 + (i >> 1)] = q0 | ((q & 15) << 4)
            else:
                q0 = q & 15
    return bytes(out)


# Filtres passe-bas figés (sinc fenêtré de Blackman, coefficients entiers / 16384) : les mêmes
# entiers dans la page web donnent les mêmes octets.
# HALF : 22 050 -> 11 025 Hz (coupure ~5 kHz). TWO_THIRDS : 33 075 -> 22 050 Hz, filtre à 66 150 Hz
# après insertion d'un zéro sur deux (gain 2, coupure ~10,3 kHz).
HALF = (
    0, 0, 0, 0, 0, 1, 1, -2, -3, 2, 6, 0, -10, -4, 14, 12, -15, -24, 11, 38, 0, -52, -21, 61,
    52, -60, -92, 41, 136, 0, -175, -69, 197, 166, -188, -288, 130, 427, 0, -571, -233, 705,
    640, -814, -1481, 885, 5127, 7282, 5127, 885, -1481, -814, 640, 705, -233, -571, 0, 427,
    130, -288, -188, 166, 197, -69, -175, 0, 136, 41, -92, -60, 52, 61, -21, -52, 0, 38, 11,
    -24, -15, 12, 14, -4, -10, 0, 6, 2, -3, -2, 1, 1, 0, 0, 0, 0, 0)

TWO_THIRDS = (
    0, 0, 0, 0, 0, 0, 0, -1, 0, 1, 1, 1, -1, -2, -2, 1, 3, 3, 0, -5, -6, -1, 6, 9, 3, -7, -12,
    -7, 6, 16, 13, -4, -21, -20, 0, 24, 29, 7, -26, -39, -17, 25, 50, 31, -21, -61, -49, 12,
    70, 71, 4, -76, -95, -27, 77, 122, 58, -70, -149, -98, 52, 173, 146, -22, -191, -202, -24,
    201, 265, 88, -196, -333, -174, 172, 403, 286, -120, -473, -430, 32, 540, 617, 113, -599,
    -874, -350, 649, 1266, 781, -687, -2030, -1805, 710, 4823, 8649, 10204, 8649, 4823, 710,
    -1805, -2030, -687, 781, 1266, 649, -350, -874, -599, 113, 617, 540, 32, -430, -473, -120,
    286, 403, 172, -174, -333, -196, 88, 265, 201, -24, -202, -191, -22, 146, 173, 52, -98,
    -149, -70, 58, 122, 77, -27, -95, -76, 4, 71, 70, 12, -49, -61, -21, 31, 50, 25, -17, -39,
    -26, 7, 29, 24, 0, -20, -21, -4, 13, 16, 6, -7, -12, -7, 3, 9, 6, -1, -6, -5, 0, 3, 3, 1,
    -2, -2, -1, 1, 1, 1, 0, -1, 0, 0, 0, 0, 0, 0, 0)


def resample(x, up, down):
    """Rééchantillonnage entier exact : y[m] = arrondi(Σ h[i] · u[down·m + c − i] / 16384), où u est x
    avec up − 1 zéros insérés entre deux échantillons (u[j] = x[j / up] si j multiple de up), c le
    centre du filtre, et 0 hors du signal. (up, down) = (1, 2) -> HALF ; (2, 3) -> TWO_THIRDS.
    Longueur de sortie : (len(x) · up + down − 1) // down."""
    h = np.array(HALF if (up, down) == (1, 2) else TWO_THIRDS, np.int64)
    c = (len(h) - 1) // 2
    x = np.asarray(x, np.int64)
    u = np.zeros(len(x) * up, np.int64)
    u[::up] = x
    z = np.convolve(u, h)                       # z[j] = Σ h[i] · u[j − i]
    m = (len(u) + down - 1) // down
    y = z[c:c + down * m:down]
    y = np.concatenate([y, np.zeros(m - len(y), np.int64)])
    return np.clip((y + 8192) >> 14, -32768, 32767)
