#!/usr/bin/env python3
"""
vox_us.py - Sous-titres FR des voix en jeu sur la version USA (voix US gardées).

Voix en jeu : banques VOX.DAT lancées par les scripts de STAGE.DIR (GM_VoxStream, jetons
« vox » de gcx.codes, hors stage « sound » = test sonore). Le jeu dessine le texte des
entrées de leur bloc 0x03 (jimctrl.c, NewJimakuControl(0)), 2 lignes au plus (« 80 7C »).

Appariement : les scripts US et FR lancent les mêmes voix dans le même ordre, stage par stage
(308 jetons sur le disque 1, 170 sur le disque 2, dans les deux versions) : la k-ième voix
d'un stage US prend la k-ième du même stage FR.

On garde le nombre d'entrées US et leurs horaires : GM_JimakuCounter (entrées passées) sert
aux personnages des scènes (demodoll attend un nombre d'entrées donné par le script US). Le
texte FR est regroupé ou coupé aux fins de phrase sur les entrées US (codec_us.resegment).
Si ça donnerait plus de 2 lignes, on garde les entrées FR, horaires recalés sur la voix US
(vox_vostfr.warp), comme la VOSTFR.

La banque réécrite garde sa place : elle doit tenir dans ses secteurs d'origine.
"""

import re
import struct
from collections import Counter, defaultdict

import codec_us
import gcx
import vox
import vox_vostfr as vv

VOICE = (b"\x80\x7c", (37, 40, 43), 2, "égales")  # sous-titre : retour, largeurs, lignes, lignes égales


def stage_voices(st, v):
    """{stage: [codes VOX dans l'ordre des scripts]} (hors test sonore)."""
    secs = {s // 2048 for s, _ in vox.banks(v)}
    out = defaultdict(list)
    for p, kind, name in gcx.codes(st, secs, set()):
        if kind == "vox" and name != "sound":
            out[name].append(struct.unpack_from(">I", st, p + 1)[0])
    return out


def pair(st_us, vu, st_fr, vf):
    """{code US: code FR} par l'ordre des scripts, stage par stage (vote si répété)."""
    su, sf = stage_voices(st_us, vu), stage_voices(st_fr, vf)
    votes = defaultdict(Counter)
    for name, cu in su.items():
        cf = sf.get(name, [])
        if len(cf) != len(cu):
            continue
        for a, b in zip(cu, cf):
            votes[a][b] += 1
    return {a: c.most_common(1)[0][0] for a, c in votes.items()}


def pair_demos(du, df):
    """{secteur US: secteur FR} des cinématiques de DEMO.DAT : mêmes banques, même ordre (les
    blocs son sont identiques, sauf la banque 28 du disque 2, « Snaaaake !!! » plus long en VF ;
    les données de scène diffèrent, NTSC 60 Hz contre PAL 50 Hz)."""
    bu, bf = vox.banks(du), vox.banks(df)
    if len(bu) != len(bf):
        raise ValueError(f"DEMO.DAT : {len(bu)} banques US, {len(bf)} FR")
    return {su // 2048: sf // 2048 for (su, _), (sf, _) in zip(bu, bf)}


def caps_of(v, code):
    return [x for c, o, _ in vox.blocks(v, code * 2048) if c == vox.CAPS1 for x in vv.caption_block(v, o)["caps"]]


def anchors(fr, us, tol=30):
    """Paires (i, j) croissantes d'entrées FR / US qui commencent au même moment (à tol près :
    mêmes unités d'horaire dans les deux versions), le plus de paires possible."""
    n, m = len(fr), len(us)
    best = [[(0, 0)] * (m + 1) for _ in range(n + 1)]   # (paires, -écart total)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            v = max(best[i - 1][j], best[i][j - 1])
            dt = abs(fr[i - 1][0] - us[j - 1][0])
            if dt <= tol:
                p, e = best[i - 1][j - 1]
                v = max(v, (p + 1, e - dt))
            best[i][j] = v
    out, i, j = [], n, m
    while i and j:
        if best[i][j] == best[i - 1][j]:
            i -= 1
        elif best[i][j] == best[i][j - 1]:
            j -= 1
        else:
            out.append((i - 1, j - 1))
            i, j = i - 1, j - 1
    return out[::-1]


def split_timed(fr, us, fmt=VOICE):
    """Textes FR (entrées (t, d, texte)) répartis sur les entrées US : groupes entre deux
    entrées qui commencent ensemble, chacun redécoupé (codec_us.resegment). (textes, lignes max)."""
    cuts = [(0, 0)] + [a for a in anchors(fr, us) if a != (0, 0)] + [(len(fr), len(us))]
    groups = []
    for (i0, j0), (i1, j1) in zip(cuts, cuts[1:]):
        if groups and (i0 == i1 or j0 == j1):   # un côté vide : fondu dans le groupe d'avant
            groups[-1] = (groups[-1][0], i1, groups[-1][2], j1)
        else:
            groups.append((i0, i1, j0, j1))
    if groups and (groups[0][0] == groups[0][1] or groups[0][2] == groups[0][3]):
        if len(groups) == 1:
            return None, 0
        (a, _, c, _), (_, b, _, d) = groups[0], groups[1]
        groups[:2] = [(a, b, c, d)]
    out, worst = [], 0
    for i0, i1, j0, j1 in groups:
        new, nl = codec_us.resegment([x for _, _, x in fr[i0:i1]], [x for _, _, x in us[j0:j1]], fmt)
        if new is None:
            return None, 0
        out += new
        worst = max(worst, nl)
    return out, worst


def plan(vu, vf, mapping, skip=()):
    """Nouveaux sous-titres (textes FR encore en 1F xx) : {code US: [[(t, durée, texte)] par bloc]}.
    Sert aussi pour DEMO.DAT (même format de banque ; code = secteur dans DEMO.DAT)."""
    out, stats = {}, Counter()
    for cu, cf in sorted(mapping.items()):
        if cu in skip:
            continue
        blocks = [(o, vv.caption_block(vu, o)) for c, o, _ in vox.blocks(vu, cu * 2048) if c == vox.CAPS1]
        us = [(t, d, x, n) for n, (_, b) in enumerate(blocks) for t, d, x in b["caps"]]
        fr = caps_of(vf, cf)
        if not us or not fr:
            stats["sans sous-titres"] += 1
            continue
        new, nl = split_timed(fr, [(t, d, x) for t, d, x, _ in us])
        if new is None or nl > VOICE[2]:
            new, nl = codec_us.resegment([x for _, _, x in fr], [x for _, _, x, _ in us], VOICE)
        per = [[] for _ in blocks]
        if new is not None and nl <= VOICE[2]:
            for (t, d, _, n), x in zip(us, new):
                per[n].append((t, d, x))
            stats["entrées US" if len(fr) == len(us) else "FR redécoupé sur les entrées US"] += 1
        else:  # trop de lignes : entrées FR, horaires recalés sur la voix US (comme la VOSTFR)
            for (_, _, x), (t, d) in zip(fr, vv.warp(fr, [(t, d, x) for t, d, x, _ in us])):
                n = next((n for n, (_, b) in enumerate(blocks) if t < b["end"]), len(blocks) - 1)
                b = blocks[n][1]
                t = max(t, b["start"])
                per[n].append((t, max(1, min(d, b["end"] - t)), x))
            stats["entrées FR (trop de lignes)"] += 1
        out[cu] = per
    return out, stats


def texts(p):
    return [x for per in p.values() for blk in per for _, _, x in blk]


COMPACT = [
    lambda x: x.strip(b" "),                               # espaces en bord d'entrée
    lambda x: re.sub(rb" ?\x80\x7c ?", b"\x80\x7c", x),    # et autour des retours à la ligne
    lambda x: re.sub(rb" ([?!:;])", rb"\1", x),            # espace avant ? ! : ; (typographie FR)
    lambda x: x.replace(b"\x80\x7c", b"|"),                # retour à la ligne sur 1 octet (font.c)
]


def encode(vu, code, per, accents, grow=False):
    """Banque US réécrite (sous-titres FR, accents en 80 xx), à la taille de ses secteurs ; si
    elle déborde, textes compactés pas à pas (COMPACT). Sinon : None, ou avec grow, la banque
    entière non compactée (complétée au secteur), à poser ailleurs (relocate)."""
    for k in range(len(COMPACT) + 1):
        b = _encode(vu, code, [[(t, d, _compact(x, k)) for t, d, x in blk] for blk in per], accents)
        if b is not None:
            return b
    if grow:
        b = _encode(vu, code, per, accents, fit=False)
        return b.ljust((len(b) + 2047) // 2048 * 2048, b"\0")
    return None


def room(v, code):
    """Place d'origine d'une banque : sa taille arrondie au secteur."""
    lst = list(vox.blocks(v, code * 2048))
    end = lst[-1][1] + lst[-1][2]
    return (end - code * 2048 + 2047) // 2048 * 2048


def _compact(x, k):
    for f in COMPACT[:k]:
        x = f(x)
    return x


def _encode(vu, code, per, accents, fit=True):
    s = code * 2048
    lst = list(vox.blocks(vu, s))
    caps = [o for c, o, _ in lst if c == vox.CAPS1]
    out = bytearray()
    for c, o, size in lst:
        if c == vox.CAPS1:
            b = vv.caption_block(vu, o)
            ents = [(t, d, codec_us.usfont.convert(x, accents)) for t, d, x in per[caps.index(o)]]
            blk = vv.encode_block(b["start"], b["end"], b["lips"], ents, b["font"])
            if len(blk) - 4 > vv.JIMAKU_MAX:
                raise ValueError(f"banque {code:#x} : bloc de sous-titres de {len(blk)} octets")
            out += blk
        else:
            if vu[o + 3]:
                raise ValueError(f"banque {code:#x} : bloc {c:#x} de plus de 64 Ko")
            out += vu[o:o + size]
    end = lst[-1][1] + lst[-1][2]
    room = (end - s + 2047) // 2048 * 2048
    if not fit:
        return bytes(out)
    if len(out) > room:
        return None
    return bytes(out).ljust(room, b"\0")
