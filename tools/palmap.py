#!/usr/bin/env python3
"""
palmap.py - Outil de développement : correspondance d'adresses EXE PAL France -> PAL Europe (UK).

Les deux EXE viennent de la même compilation, seuls les textes changent de longueur : le code
et les données sont décalés par morceaux. On compare les instructions en masquant ce qui dépend
des adresses (cibles de jal/j, immédiats de lui/addiu/lw/sw...) : chaque fenêtre de 8 instructions
masquées présente une seule fois dans les deux EXE donne une ancre. Les données sont retrouvées
par les références du code (paires lui + addiu/lw/sw, accès relatifs à gp).

Écrit tools/pal_uk.py (segments de code et de données, gp, base des overlays, SHA-1 des zones
de code ajouté), utilisé par pal.py. À relancer si un patch utilise une adresse hors des segments.

  python palmap.py work/FR1/MGS/MGS1.EXE work/UK1/MGS/MGS1.EXE
"""

import collections, hashlib, struct, sys
from pathlib import Path

B = 0x80010000
K = 8
GAP = 64   # trou toléré entre deux morceaux de même décalage
CODE_START = 0x80012000   # avant : textes (rdata)
IMM = {0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
       0x28, 0x29, 0x2A, 0x2B, 0x2E, 0x32, 0x3A}
LOADST = {0x09, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x28, 0x29, 0x2A, 0x2B, 0x2E}
# zones de code ajouté (menu de débogage inutilisé) : m9, fps, carre, psg1, l2r2
CAVES = [(0x800447E4, 0x80045400), (0x80045400, 0x80045900), (0x80045900, 0x80045A08),
         (0x80045A08, 0x80045BB8), (0x80045BB8, 0x80045C08)]
OUT = Path(__file__).resolve().parent / "pal_uk.py"


def words(d):
    return list(struct.unpack(f"<{(len(d) - 0x800) // 4}I", d[0x800:]))


def mask(x):
    op = x >> 26
    if op in (2, 3):
        return x & 0xFC000000
    if op in IMM:
        return x & 0xFFFF0000
    return x


def s16(x):
    return x - 0x10000 if x & 0x8000 else x


def find_gp(ws, entry):
    i = (entry - B) // 4
    for k in range(i, i + 64):
        if ws[k] >> 16 == 0x3C1C:
            return ((ws[k] & 0xFFFF) << 16) + s16(ws[k + 1] & 0xFFFF)
    raise SystemExit("gp introuvable")


def segments(pairs):
    """[(a, b)] triés -> [(début, fin, décalage)] en fusionnant les trous courts de même décalage."""
    out = []
    for a, b in pairs:
        d = b - a
        if out and out[-1][2] == d and a - out[-1][1] <= GAP * 4:
            out[-1][1] = a + 4
        else:
            out.append([a, a + 4, d])
    return [tuple(s) for s in out]


def lookup(tab, a, data=False):
    for seg in ([] if data else tab["CODE"]) + tab["DATA"]:
        if seg[0] <= a < seg[1]:
            return a + seg[2]
    raise SystemExit(f"adresse {a:08x} hors des segments")


def same_word(tab, x, y):
    """Mot de données identique, ou pointeur vers le code traduit."""
    if x == y:
        return True
    if B <= x < 0x80200000:
        try:
            return lookup(tab, x) == y
        except SystemExit:
            return False
    return False


def fill(fr, uk, code, data):
    """Comble les trous entre deux morceaux de données de même décalage quand le contenu
    du trou correspond (tables sans référence directe dans le code, comme weapon_actions)."""
    tab = dict(CODE=code, DATA=data)
    out = [list(data[0])]
    for a, b, d in data[1:]:
        pa, pb, pd = out[-1]
        if pd == d and a - pb <= 0x800 and 0x800 + a - B <= len(fr) and 0x800 + a + d - B <= len(uk):
            ok = all(same_word(tab, struct.unpack_from("<I", fr, 0x800 + k - B)[0],
                               struct.unpack_from("<I", uk, 0x800 + k + d - B)[0])
                     for k in range(pb & ~3, a, 4))
            if ok:
                out[-1][1] = b
                continue
        out.append([a, b, d])
    return [tuple(x) for x in out]


def build(fr, uk):
    F, U = words(fr), words(uk)
    MF, MU = [mask(x) for x in F], [mask(x) for x in U]
    idx = collections.defaultdict(list)
    for i in range(len(MU) - K):
        idx[tuple(MU[i:i + K])].append(i)
    imap = {}
    for i in range(len(MF) - K):
        h = idx.get(tuple(MF[i:i + K]))
        if h and len(h) == 1:
            for k in range(K):
                imap.setdefault(i + k, h[0] + k)
    code = [c for c in segments(sorted((B + 4 * i, B + 4 * j) for i, j in imap.items()))
            if c[1] - c[0] >= 0x80 and c[0] >= CODE_START]   # pas de faux morceaux dans les textes

    data = collections.defaultdict(collections.Counter)
    for i in range(len(F) - 8):
        x = F[i]
        if x >> 26 != 0xF or i not in imap:
            continue
        rt = (x >> 16) & 31
        for k in range(1, 8):
            y = F[i + k]
            if (y >> 26) in LOADST and (y >> 21) & 31 == rt:
                if i + k in imap and imap[i + k] - imap[i] == k:
                    xu, yu = U[imap[i]], U[imap[i + k]]
                    if xu >> 26 == 0xF and yu >> 26 == y >> 26:
                        a = (((x & 0xFFFF) << 16) + s16(y & 0xFFFF)) & 0xFFFFFFFF
                        au = (((xu & 0xFFFF) << 16) + s16(yu & 0xFFFF)) & 0xFFFFFFFF
                        data[a][au] += 1
                break
    gpf = find_gp(F, struct.unpack_from("<I", fr, 0x10)[0])
    gpu = find_gp(U, struct.unpack_from("<I", uk, 0x10)[0])
    for i, x in enumerate(F):
        if (x >> 26) in LOADST and (x >> 21) & 31 == 28 and i in imap:
            y = U[imap[i]]
            if y >> 26 == x >> 26 and (y >> 21) & 31 == 28:
                data[(gpf + s16(x & 0xFFFF)) & 0xFFFFFFFF][(gpu + s16(y & 0xFFFF)) & 0xFFFFFFFF] += 1
    dpairs = sorted((a, c.most_common(1)[0][0]) for a, c in data.items() if B <= a < 0x80200000)
    return code, fill(fr, uk, code, segments(dpairs)), gpf, gpu


def main():
    fr, uk = (open(p, "rb").read() for p in sys.argv[1:3])
    code, data, gpf, gpu = build(fr, uk)
    tab = dict(CODE=code, DATA=data)
    caves = {}
    for lo, hi in CAVES:
        a, b = lookup(tab, lo), lookup(tab, hi - 4) + 4
        if b - a != hi - lo:
            raise SystemExit(f"zone {lo:08x} : taille différente en UK")
        caves[f"{lo:08X}"] = hashlib.sha1(uk[0x800 + a - B:0x800 + b - B]).hexdigest()
    lines = ['"""Table générée par palmap.py : EXE PAL France -> PAL Europe (UK). Ne pas modifier à la main."""',
             "", f"SIG = {hashlib.sha1(uk[0x800:0x1000]).hexdigest()!r}", f"GP = 0x{gpu:08X}",
             f"GP_FR = 0x{gpf:08X}", f"OVB = 0x{lookup(tab, 0x800C47D8, data=True):08X}",
             "CAVE_SHA1 = {"] + [f"    0x{k}: {v!r}," for k, v in caves.items()] + ["}", "CODE = ["]
    lines += [f"    (0x{a:08X}, 0x{b:08X}, {d}),"for a, b, d in code] + ["]", "DATA = ["]
    lines += [f"    (0x{a:08X}, 0x{b:08X}, {d}),"for a, b, d in data] + ["]", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"{OUT.name} : {len(code)} segments de code, {len(data)} de données, gp {gpf:08x} -> {gpu:08x}")


if __name__ == "__main__":
    main()
