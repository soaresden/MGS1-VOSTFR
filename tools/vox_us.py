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

VOICE = (b"\x80\x7c", (37, 40, 43), 2)   # sous-titre en jeu : retour à la ligne, largeurs, lignes


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


def caps_of(v, code):
    return [x for c, o, _ in vox.blocks(v, code * 2048) if c == vox.CAPS1 for x in vv.caption_block(v, o)["caps"]]


def plan(vu, vf, mapping, skip=()):
    """Nouveaux sous-titres (textes FR encore en 1F xx) : {code US: [[(t, durée, texte)] par bloc]}."""
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


def encode(vu, code, per, accents):
    """Banque US réécrite (sous-titres FR, accents en 80 xx), à la taille de ses secteurs ; si
    elle déborde, textes compactés pas à pas (COMPACT). None si elle ne tient toujours pas."""
    for k in range(len(COMPACT) + 1):
        b = _encode(vu, code, [[(t, d, _compact(x, k)) for t, d, x in blk] for blk in per], accents)
        if b is not None:
            return b
    return None


def _compact(x, k):
    for f in COMPACT[:k]:
        x = f(x)
    return x


def _encode(vu, code, per, accents):
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
            out += vu[o:o + size]
    end = lst[-1][1] + lst[-1][2]
    room = (end - s + 2047) // 2048 * 2048
    if len(out) > room:
        return None
    return bytes(out).ljust(room, b"\0")
