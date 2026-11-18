#!/usr/bin/env python3
"""
codec_us.py - Codec en français sur la version USA (voix US, textes du Codec FR).

Base : RADIO.DAT US (structure, codes VOICE, mots des TALK : personnage, visage, animation).
Seuls les textes des TALK changent : ceux du fragment FR apparié. Pendant une VOICE, la boucle
du Codec passe au TALK suivant à chaque entrée de sous-titre de la banque VOX US : le nombre
de TALK US est donc gardé, les répliques FR sont regroupées ou coupées (aux fins de phrase)
pour tomber au plus près des répliques US, puis remises en lignes.

Appariement des fragments : les scripts de STAGE.DIR appellent les mêmes fragments dans le
même ordre dans les deux versions (commande radio 0x24E1, options b / o / c). Dans un
fragment, les blocs (TALK directs d'un même bloc : profondeur, commande parente, VOICE) sont
appariés par difflib ; un bloc que seule la VF a en plus est fondu dans le bloc voisin.
Une VOICE dont le texte FR ne tient pas en 4 lignes par réplique US reprend les pages FR, et
sa banque VOX US est recalée (une entrée de sous-titre « . » par page FR, minutage des
répliques US réparti) quand banque et TALK se correspondent des deux côtés.
Accents : usfont.py (police US agrandie, codes 80 xx). Le fragment de Mei Ling (plus de
65 535 octets en FR) passe aux retours à la ligne « | » d'un octet.

Sorties : nouveau RADIO.DAT (plus gros), STAGE.DIR US aux codes radio recalculés et police
agrandie (même taille), banques VOX recalées (même taille). Image de test : RADIO.DAT écrit dans la zone vide DUMMY3M.DAT et son enregistrement
de répertoire ISO pointé dessus (le jeu cherche ses fichiers par nom au démarrage) ; rien
d'autre ne bouge sur le disque.

  python tools/codec_us.py --us work/US1.bin --fr work/FR1.bin --out work/us_codec/US1.bin
"""

import argparse
import copy
import difflib
import re
import shutil
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np

import gcx
import psxiso
import radiotree as rt
import usfont
import vox
import vox_vostfr as vv
from cdsector import fix_form1, write_file_inplace, SECTOR
from isorebuild import dir_records

NL = b"\x80\x23\x80\x4e"          # retour à la ligne d'un TALK (« #N »)
NL_SHORT = b"|"                   # même effet (font.c : « | » sur 1 ou 2 octets = « #N »)
WIDTH, LINES = 36, 4               # textes FR d'origine : 35 caractères, 4 lignes au plus
SPLIT = re.compile(rb"\x80\x23\x80\x4e|\x80\x7c|\||\r| ")
SPLIT_LINES = re.compile(rb"\x80\x23\x80\x4e|\x80\x7c|\||\r")


# --- lecture --------------------------------------------------------------------------

def load(bin_path):
    d = psxiso.Disc(bin_path)
    f = d.files()
    st = bytes(d.read(*f["MGS/STAGE.DIR"]))
    r = bytes(d.read(*f["MGS/RADIO.DAT"]))
    codes = rt.radio_codes(st)
    offs = []
    for o in sorted({v & 0xFFFFFF for _, _, v in codes}):
        if o < len(r):
            try:
                rt.parse_block(r, o + 8)
                offs.append(o)
            except (ValueError, IndexError):
                pass          # valeur qui n'est pas un code (stage s00aa de la version US)
    ends = offs[1:] + [len(r)]
    frags = {o: rt.Fragment(r, o, e) for o, e in zip(offs, ends)}
    seq = defaultdict(list)
    for _, name, v in codes:
        if v & 0xFFFFFF in frags:
            seq[name].append(v & 0xFFFFFF)
    return d, f, st, r, codes, frags, seq


def pair_fragments(seq_us, seq_fr):
    votes = defaultdict(Counter)
    for name, a in seq_us.items():
        b = seq_fr.get(name, [])
        if len(a) == len(b):
            for x, y in zip(a, b):
                votes[x][y] += 1
    return {x: c.most_common(1)[0][0] for x, c in votes.items()}


# --- suites de TALK -------------------------------------------------------------------

def blocks(frag):
    """Blocs dans l'ordre de l'arbre : [(clé, TALK directement dans le bloc)]. Les commandes
    simples (ANIM, SOUND…) intercalées ne comptent pas : les deux versions ne les placent pas
    aux mêmes endroits ; les blocs (VOICE, IF, SWITCH…) suivent le même arbre."""
    out = []

    def rec(block, depth, owner, voice):
        talks = []
        out.append(((depth, owner, voice), talks))
        for c in block.items:
            if c.code == rt.TALK:
                talks.append(c)
            for p in c.parts:
                if isinstance(p, rt.Block):
                    rec(p, depth + 1, c.code, voice or c.code == rt.VOICE)

    rec(frag.script, 0, 0, False)
    return out


def voice_blocks(frag):
    """{id du 1er TALK : (VOICE, bloc)} des VOICE dont le bloc n'a que des commandes simples."""
    out = {}

    def rec(block):
        for c in block.items:
            for p in c.parts:
                if isinstance(p, rt.Block):
                    talks = [x for x in p.items if x.code == rt.TALK]
                    flat = not any(isinstance(q, rt.Block) for x in p.items for q in x.parts)
                    if c.code == rt.VOICE and talks and flat:
                        out[id(talks[0])] = (c, p)
                    rec(p)

    rec(frag.script)
    return out


def voice_code(cmd):
    return struct.unpack_from(">I", cmd.parts[0], 0)[0]


def bank_caps(v, code):
    """Blocs de sous-titres (0x03) de la banque VOX au secteur code : [(offset, bloc décodé)]."""
    return [(o, vv.caption_block(v, o)) for c, o, _ in vox.blocks(v, code * 2048) if c == vox.CAPS1]


def _plain(t):
    return re.sub(rb"[^A-Za-z0-9]", b"", re.sub(rb"\x1f.|\x80.", b"", t, flags=re.S))


def same_bank(v, code, talks):
    """La banque VOX au secteur code a-t-elle pour sous-titres les textes de ces TALK ? Le
    RADIO.DAT est le même sur les deux disques, pas le VOX.DAT : sur le disque 2, le code d'une
    VOICE du disque 1 tombe sur une autre banque (ou au milieu d'une)."""
    if code * 2048 >= len(v) or v[code * 2048] != vox.INIT:
        return False
    try:
        caps = [c for _, b in bank_caps(v, code) for c in b["caps"]]
    except (ValueError, struct.error, IndexError):
        return False
    def close(x, t):     # sous-titre parfois tronqué ou avec une coquille par rapport au TALK
        x, t = _plain(x), _plain(t)
        k = min(len(x), len(t))
        return k > 0 and difflib.SequenceMatcher(None, x[:k], t[:k]).ratio() >= 0.85

    return len(caps) == len(talks) and all(close(x, t) for (_, _, x), t in zip(caps, talks))


def retime_bank(vu, us_code, vf, fr_code):
    """Banque US (audio, lèvres) avec autant d'entrées de sous-titres que la banque FR, horaires
    recalés sur la voix US (vox_vostfr.warp). Le Codec ne dessine pas ces textes (le texte vient
    des TALK) : un « . » par entrée, la banque ne grossit pas. Renvoie les octets à écrire."""
    fr_caps = [c for _, b in bank_caps(vf, fr_code) for c in b["caps"]]
    start = us_code * 2048
    lst = list(vox.blocks(vu, start))
    ub = bank_caps(vu, us_code)
    uk_caps = [(c, n) for n, (_, b) in enumerate(ub) for c in b["caps"]]
    times = vv.warp(fr_caps, [c for c, _ in uk_caps])
    per = [[] for _ in ub]
    for k, (t, d) in enumerate(times):
        n = next((n for n, (_, b) in enumerate(ub) if t < b["end"]), len(ub) - 1)
        b = ub[n][1]
        t = max(t, b["start"])
        per[n].append((t, max(1, min(d, b["end"] - t)), b"."))
    new = {o: vv.encode_block(b["start"], b["end"], b["lips"], per[n], b["font"])
           for n, (o, b) in enumerate(ub)}
    out = b"".join(new.get(o, vu[o:o + size]) for _, o, size in lst)
    end = lst[-1][1] + lst[-1][2]
    room = (end + 2047) // 2048 * 2048 - start
    if len(out) > room:
        raise ValueError(f"banque {us_code:#x} : {len(out)} octets pour {room}")
    return out.ljust(room, b"\0")


def pair_blocks(fu, ff):
    a, b = blocks(fu), blocks(ff)
    pairs, lost, pending = [], 0, []
    sm = difflib.SequenceMatcher(None, [k for k, _ in a], [k for k, _ in b], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal" or i2 - i1 == j2 - j1:
            for (_, x), (_, y) in zip(a[i1:i2], b[j1:j2]):
                if x and y:
                    # blocs FR en plus juste avant (la VF coupe parfois une VOICE en deux :
                    # fin du jeu, 23 + 1 répliques pour 24 en US) : recollés s'ils comblent l'écart
                    if pending and abs(len(pending) + len(y) - len(x)) < abs(len(y) - len(x)):
                        y = pending + y
                    pairs.append((x, y))
                else:
                    lost += len(x)
                pending = []
        else:
            lost += sum(len(x) for _, x in a[i1:i2])
            pending = [t for _, y in b[j1:j2] for t in y] if op == "insert" else []
    return pairs, lost


# --- texte ----------------------------------------------------------------------------

def width(word):
    """Largeur en caractères : accent 1F xx = 1, code 80 xx = 0."""
    return len(re.sub(rb"\x80.", b"", re.sub(rb"\x1f.", b"x", word, flags=re.S), flags=re.S))


def words(text):
    return [w for w in SPLIT.split(text) if w]


def wrap(ws, w=WIDTH):
    lines, cur = [], []
    for x in ws:
        if cur and width(b" ".join(cur + [x])) > w:
            lines.append(b" ".join(cur))
            cur = []
        cur.append(x)
    if cur:
        lines.append(b" ".join(cur))
    return lines


CODEC = (NL, (WIDTH, 40), LINES)  # format d'un TALK : retour à la ligne, largeurs essayées, lignes


def layout(ws, fmt=CODEC):
    """Lignes de la première largeur, d'une suivante si ça évite des lignes de trop.
    Format à 4 éléments (sous-titres) : le moins de lignes possible à la 2e largeur, coupées
    là où les lignes sont le plus égales (pas de mot seul sur la 2e ligne)."""
    nl, widths, nmax = fmt[:3]
    if len(fmt) > 3:
        n = len(wrap(ws, widths[1]))
        if n > 1:
            lines = balanced(ws, n, widths[-1]) or wrap(ws, widths[1])
        else:
            lines = [b" ".join(ws)]
        return nl.join(lines), len(lines)
    lines = wrap(ws, widths[0])
    if len(lines) > nmax:
        lines = min((wrap(ws, w) for w in widths), key=len)
    return nl.join(lines), len(lines)


def balanced(ws, n, wmax):
    """ws en n lignes de wmax au plus, la plus longue la plus courte possible (coupe après une
    ponctuation un peu favorisée). None si impossible."""
    import functools

    @functools.lru_cache(None)
    def best(i, k):
        if k == 1:
            w = width(b" ".join(ws[i:]))
            return (w, ()) if w <= wmax and i < len(ws) else None
        out = None
        for j in range(i + 1, len(ws)):
            w = width(b" ".join(ws[i:j]))
            if w > wmax:
                break
            r = best(j, k - 1)
            if r is None:
                continue
            score = max(w, r[0]) - (3 if re.search(rb"[.,!?;:]$", ws[j - 1]) else 0)
            if out is None or score < out[0]:
                out = (score, (j,) + r[1])
        return out

    r = best(0, n)
    if r is None:
        return None
    cuts = (0,) + r[1] + (len(ws),)
    return [b" ".join(ws[a:b]) for a, b in zip(cuts, cuts[1:])]


def units(talks):
    """Mots FR avec, avant chaque mot, le coût d'une coupe à cet endroit."""
    ws, cost = [], []
    for t in talks:
        for i, x in enumerate(words(t)):
            if not ws:
                c = None
            elif i == 0:
                c = 0                                    # entre deux TALK FR
            elif re.search(rb"[.!?]$|\.\.\.$|\x80\x22$", ws[-1]):
                c = 2                                    # fin de phrase
            elif re.search(rb"[,;:]$", ws[-1]):
                c = 6
            else:
                c = 15
            ws.append(x)
            cost.append(c)
    return ws, cost


def resegment(fr, us, fmt=CODEC):
    """Textes FR (m TALK) -> n textes, n = nombre de TALK US. Renvoie (textes, nb de lignes max)."""
    n, m = len(us), len(fr)
    if n == m:
        return list(fr), 0
    ws, cost = units(fr)
    if len(ws) < n:
        return None, 0
    if n == 1:
        txt, nl = layout(ws, fmt)
        return [txt], nl
    wl = [width(x) + 1 for x in ws]
    tot = sum(wl)
    cum = [0]
    for x in wl:
        cum.append(cum[-1] + x)
    ul = [max(1, width(u)) for u in us]
    ut = sum(ul)
    target = []
    acc = 0
    for x in ul[:-1]:
        acc += x
        target.append(acc / ut)
    cand = [i for i in range(1, len(ws)) if cost[i] is not None]
    INF = float("inf")
    # best[k][i] : meilleur coût avec la k-ième coupe avant le mot cand[i]
    best = [[INF] * len(cand) for _ in range(n - 1)]
    back = [[-1] * len(cand) for _ in range(n - 1)]

    cap = fmt[1][0] * fmt[2]
    window = max(3 * cap, 3 * tot / n)

    def seg_cost(a, b):
        # estimation rapide (les lignes coupées aux mots perdent ~10 %)
        x = cum[b] - cum[a]
        return 0 if x <= cap * 0.9 else 40 * (x / (cap * 0.9) - 1) * fmt[2]

    for k in range(n - 1):
        lo = 0
        for i, c in enumerate(cand):
            here = abs(cum[c] / tot - target[k]) * 60 + cost[c]
            if k == 0:
                v, j0 = here + seg_cost(0, c), -1
            else:
                v, j0 = INF, -1
                while cum[c] - cum[cand[lo]] > window:
                    lo += 1
                for j in range(lo, i):
                    if best[k - 1][j] < INF:
                        x = best[k - 1][j] + seg_cost(cand[j], c)
                        if x < v:
                            v, j0 = x, j
                v += here
            best[k][i], back[k][i] = v, j0
    k = n - 2
    last = min(range(len(cand)), key=lambda i: best[k][i] + seg_cost(cand[i], len(ws)))
    cuts = []
    i = last
    for k in range(n - 2, -1, -1):
        cuts.append(cand[i])
        i = back[k][i]
    cuts = [0] + cuts[::-1] + [len(ws)]
    out, worst = [], 0
    # une coupe qui retombe exactement sur un TALK FR d'origine le garde tel quel
    starts, pos = {}, 0
    for t in fr:
        starts[pos] = t
        pos += len(words(t))
    ends = {s + len(words(t)): s for s, t in starts.items()}
    for a, b in zip(cuts, cuts[1:]):
        if a in starts and ends.get(b) == a:
            out.append(starts[a])
        else:
            txt, nl = layout(ws[a:b], fmt)
            out.append(txt)
            worst = max(worst, nl)
    return out, worst


# --- RADIO.DAT et STAGE.DIR -----------------------------------------------------------

def needed(frag, top):
    """Octets que le jeu doit lire : en-tête + script + police (queue gardée si l'octet haut
    d'origine la couvrait, sinon c'est un fragment mort collé derrière)."""
    s = 8 + len(frag.script.bytes())
    return s, s + len(frag.tail)


def build(us_bin, fr_bin, log=print, force=(), voices=True):
    """Renvoie {"radio": RADIO.DAT, "stage": STAGE.DIR, "vox": {offset dans VOX.DAT: banque},
    "demo": {offset dans DEMO.DAT: banque}, "tail": banques déplacées (après RADIO.DAT, au
    secteur suivant, dans la zone DUMMY3M.DAT)}.
    voices : sous-titres FR des voix en jeu et des cinématiques aussi (vox_us.py), et textes des
    menus de l'EXE (exe_us.py) : "exe" = EXE US patché (None sans voices)."""
    du, fus, st_us, r_us, codes_us, fu, sq_us = load(us_bin)
    df, ffs, _, _, _, ff, sq_fr = load(fr_bin)
    vu = bytes(du.read(*fus["MGS/VOX.DAT"]))
    vf = bytes(df.read(*ffs["MGS/VOX.DAT"]))
    m = pair_fragments(sq_us, sq_fr)
    exe_name = us_exe_names(fus)[0]
    exe_u = bytes(du.read(*fus[exe_name]))
    exe_f = bytes(df.read(*ffs[next(k for k in ffs if re.fullmatch(r"MGS/MGS\d\.EXE", k))]))
    log(f"  fragments : {len(fu)} US, {len(ff)} FR, {len(m)} appariés"
        f" (US seuls : {', '.join(hex(o) for o in fu if o not in m) or 'aucun'})")
    old_top = defaultdict(set)
    for _, _, v in codes_us:
        if v & 0xFFFFFF in fu:
            old_top[v & 0xFFFFFF].add(v >> 24)
    # longueur lue d'origine : queue comprise si l'octet haut la couvrait
    keep_tail = {}
    for o, F in fu.items():
        s, full = needed(F, 0)
        cap = (max(old_top[o]) + 1) * 2048 - o % 2048
        keep_tail[o] = full <= cap
    stats = Counter()
    worst = Counter()
    # 1) blocs appariés ; mémoire : textes anglais d'un bloc -> textes FR, et réplique -> réplique
    #    Une VOICE dont les répliques FR regroupées dépasseraient 4 lignes (la boîte du Codec :
    #    76 pixels, 18 par ligne) prend les pages FR telles quelles, et sa banque VOX US autant
    #    d'entrées de sous-titres (fr_pages : code VOX US -> (code FR, bloc FR, nb de TALK US)).
    todo, memo, memo1, fr_pages = {}, {}, {}, {}
    for o, F in fu.items():
        if o not in m:
            continue
        vb_u, vb_f = voice_blocks(F), voice_blocks(ff[m[o]])
        for ru, rf in pair_blocks(F, ff[m[o]])[0]:
            us = tuple(c.text for c in ru)
            new, nl = resegment([c.text for c in rf], list(us))
            if new is None:
                continue
            if (id(ru[0]) in vb_u and id(rf[0]) in vb_f
                    and (nl > LINES or voice_code(vb_u[id(ru[0])][0]) in force)):
                (cu_, _), (cf, bf) = vb_u[id(ru[0])], vb_f[id(rf[0])]
                ucode, fcode = voice_code(cu_), voice_code(cf)
                if same_bank(vu, ucode, us) and same_bank(vf, fcode, [c.text for c in rf]):
                    fr_pages.setdefault(ucode, (fcode, bf, len(ru)))
            stats["blocs 1-1" if len(us) == len(rf) else
                  ("blocs FR regroupés" if len(rf) > len(us) else "blocs FR coupés")] += 1
            worst[nl] += 1
            todo[id(ru[0])] = new   # Cmd de l'arbre US : identifiant stable (pas la liste)
            memo.setdefault(us, new)
            if len(us) == len(rf):
                for u, t in zip(us, new):
                    memo1.setdefault(u, t)
    # 2) tous les blocs US : appariés, sinon mêmes textes anglais déjà traduits ailleurs
    #    (la sauvegarde de Mei Ling répète ses conseils dans plusieurs branches, la VF une fois)
    for o, F in fu.items():
        for _, ru in blocks(F):
            if not ru:
                continue
            us = tuple(c.text for c in ru)
            new = todo.get(id(ru[0])) or memo.get(us)
            if new is None:
                new = [memo1.get(u) for u in us]
            for c, t in zip(ru, new):
                if t is None:
                    stats["TALK restés en anglais"] += 1
                else:
                    c.set_text(t)
                    stats["TALK traduits"] += 1
    # 3) pages FR : le bloc de la VOICE reprend les commandes FR (TALK, animations), la banque
    #    US est recalée ; toutes les VOICE US de cette banque (même nombre de TALK) le prennent
    banks = {}
    for o, F in fu.items():
        for c, b in voice_blocks(F).values():
            code = voice_code(c)
            if code not in fr_pages:
                continue
            fcode, bf, n = fr_pages[code]
            if sum(x.code == rt.TALK for x in b.items) != n:
                continue
            if code not in banks:
                banks[code] = retime_bank(vu, code, vf, fcode)
            b.items = copy.deepcopy(bf.items)
            stats["VOICE en pages FR"] += 1
    log(f"  {len(banks)} banques VOX recalées sur les pages FR")
    # taille d'un bloc sur 16 bits : un fragment trop gros (la sauvegarde de Mei Ling, déjà à
    # 64731 octets en US) prend le retour à la ligne court « | » (1 octet ; les sous-titres ont
    # sa forme 80 7C ; font.c le traite comme « #N »), puis au besoin des lignes de 40 caractères
    for o, F in fu.items():
        n0 = F.script.size()
        if n0 <= 0xFFFF - 3:
            continue
        talks = []
        rt.walk(F.script, lambda c, v: talks.append(c) if c.code == rt.TALK else None)
        for c in talks:
            c.set_text(c.text.replace(NL, NL_SHORT))
        n1 = F.script.size()
        if n1 > 0xFFFF - 3:
            for c in talks:
                lines = wrap(words(c.text), 40)
                if len(lines) <= c.text.count(NL_SHORT):
                    c.set_text(NL_SHORT.join(lines))
        n = F.script.size()
        log(f"  fragment {o:#x} : script de {n0} octets, {n1} avec « | »" +
            (f", {n} en lignes de 40" if n != n1 else ""))
        if n > 0xFFFF - 3:
            raise ValueError(f"fragment {o:#x} : script de {n} octets (limite 65532)")
    # accents : lettres accentuées ajoutées à la police US (usfont.py), 1F xx -> 80 xx (même taille)
    talks = []
    for F in fu.values():
        rt.walk(F.script, lambda c, v: talks.append(c) if c.code == rt.TALK else None)
    vplan = {}
    if voices:
        import abst_us
        import change_us
        import exe_us
        import vox_us
        st_fr = bytes(df.read(*ffs["MGS/STAGE.DIR"]))
        vmap = vox_us.pair(st_us, vu, st_fr, vf)
        vplan, vstats = vox_us.plan(vu, vf, vmap, skip=banks)
        log(f"  voix en jeu : {len(vmap)} banques appariées ; " + ", ".join(f"{k} {v}" for k, v in sorted(vstats.items())))
        dm_u = bytes(du.read(*fus["MGS/DEMO.DAT"]))
        dm_f = bytes(df.read(*ffs["MGS/DEMO.DAT"]))
        dplan, dstats = vox_us.plan(dm_u, dm_f, vox_us.pair_demos(dm_u, dm_f))
        log(f"  cinématiques : " + ", ".join(f"{k} {v}" for k, v in sorted(dstats.items())))
    else:
        dplan = {}
    font, accents = usfont.extend(usfont.read_font(st_us), usfont.used(
        [c.text for c in talks] + (vox_us.texts(vplan) + vox_us.texts(dplan) + exe_us.texts(exe_u, exe_f)
                                   + change_us.texts() + abst_us.strings(st_fr)
                                   if voices else [])))
    for c in talks:
        if b"\x1f" in c.text:
            c.set_text(usfont.convert(c.text, accents))
    # nouvelle disposition ; le jeu alloue (octet haut + 1) secteurs pour lire un fragment :
    # s'il en faut plus qu'en US et qu'un début de secteur en évite un, on y aligne le fragment
    out, new_code = bytearray(), {}
    for o in sorted(fu):
        F = fu[o]
        b = F.bytes()
        s = 8 + F.script.size()
        need = s + len(F.tail) if keep_tail[o] else s
        top = (len(out) % 2048 + need - 1) // 2048
        if top > max(old_top[o]) and (need - 1) // 2048 < top:
            out += bytes(-len(out) % 2048)
            top = (need - 1) // 2048
        new_code[o] = len(out) | top << 24
        out += b
    st = bytearray(st_us)
    n = 0
    for p, _, v in codes_us:
        o = v & 0xFFFFFF
        if o in new_code:
            struct.pack_into(">I", st, p + 1, new_code[o])
            n += 1
    # banques réécrites à leur place ; trop grosses : déplacées après RADIO.DAT (zone DUMMY3M),
    # leurs codes (secteur relatif au début de VOX.DAT / DEMO.DAT) réécrits dans STAGE.DIR
    lba = {k: fus[f"MGS/{k}.DAT"][0] for k in ("VOX", "DEMO")}
    dlba = fus["DUMMY3M.DAT"][0]
    base = dlba + (len(out) + 2047) // 2048
    demo, tail, moved = {}, bytearray(), {}
    for kind, data, p_, dest in (("VOX", vu, vplan, banks), ("DEMO", dm_u if voices else b"", dplan, demo)):
        for code, per in p_.items():
            b = vox_us.encode(data, code, per, accents, grow=True)
            if len(b) <= vox_us.room(data, code):
                dest[code] = b
                continue
            moved[(kind.lower(), code)] = base + len(tail) // 2048 - lba[kind]
            tail += b
    if moved:
        secs = {k: {s_ // 2048 for s_, _ in vox.banks(d_)} for k, d_ in (("vox", vu), ("demo", dm_u))}
        nm = 0
        for p, kind, _ in gcx.codes(st_us, secs["vox"], secs["demo"]):
            v = struct.unpack_from(">I", st_us, p + 1)[0]
            if (kind, v) in moved:
                struct.pack_into(">I", st, p + 1, moved[(kind, v)])
                nm += 1
        log(f"  banques déplacées dans DUMMY3M : " + ", ".join(f"{k} {c:#x}" for k, c in moved)
            + f" ({len(tail)} octets, {nm} codes réécrits)")
    if voices:
        st, nl, nc = change_us.patch(st, accents)
        log(f"  écrans de changement de disque : {nl} listes, {nc} textes FR")
        # résumés de mission : nouveau stage abst après les banques déplacées (secteur relatif à
        # STAGE.DIR dans son entrée du répertoire)
        ab, ast = abst_us.build(st_us, st_fr, accents, font)
        tail += bytes(-len(tail) % 2048)
        sec = base + len(tail) // 2048 - fus["MGS/STAGE.DIR"][0]
        tail += ab
        st = abst_us.repoint(st, sec)
        log(f"  résumés de mission : {ast['résumés']} en {ast['pages']} pages, {ast['chaînes']} chaînes FR, {ast['valeurs US']} valeurs US gardées,"
            f" {ast['glyphes retirés']} glyphes retirés ; stage abst dans DUMMY3M (secteur {sec} de STAGE.DIR,"
            f" {ast['secteurs'][0]} -> {ast['secteurs'][1]} secteurs)")
    if (base - dlba) * 2048 + len(tail) > fus["DUMMY3M.DAT"][1]:
        raise ValueError("RADIO.DAT + banques déplacées : trop gros pour DUMMY3M.DAT")
    st, pack, room = usfont.patch_stage(st, font)
    log(f"  police : {len(accents)} lettres accentuées ajoutées (pack résident {pack}/{room} octets)")
    tops = [c >> 24 for c in new_code.values()]
    log(f"  RADIO.DAT : {len(r_us)} -> {len(out)} octets ; {n} codes radio réécrits ;"
        f" octet haut max {max(tops)} (US {max(max(t) for t in old_top.values())})")
    log("  " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items())))
    lines = Counter(len(SPLIT_LINES.split(c.text)) for c in talks)
    log(f"  lignes par TALK : {dict(sorted(lines.items()))}")
    exe = None
    if voices:
        log(f"  voix en jeu : {len(vplan)} banques en FR ; cinématiques : {len(dplan)}")
        exe, es = exe_us.patch(exe_u, exe_f, accents, font)
        log(f"  menus de l'EXE : {es['entrées']} entrées, {es['textes']} textes FR, {es['grottes']} octets"
            f" dans les fonctions mortes, {es['remises en lignes']} descriptions remises en lignes"
            f"{' (retours à la ligne courts)' if es['retour court'] else ''}")
    return {"radio": bytes(out), "stage": bytes(st), "tail": bytes(tail), "exe": exe,
            "vox": {code * 2048: b for code, b in sorted(banks.items())},
            "demo": {code * 2048: b for code, b in sorted(demo.items())}}


def us_exe_names(files):
    """Copies de l'EXE US sur le disque : à la racine (démarrée) puis dans MGS/."""
    names = [k for k in files if re.fullmatch(r"(MGS/)?SLUS_\d{3}\.\d{2}", k)]
    return sorted(names, key=len)


def dummy_area(r):
    """Ce qui va au début de DUMMY3M.DAT : RADIO.DAT, puis les banques déplacées."""
    return r["radio"] + bytes(-len(r["radio"]) % 2048) + r["tail"]


def write_image(us_bin, out_bin, r, log=print):
    shutil.copyfile(us_bin, out_bin)
    d = psxiso.Disc(out_bin)
    f = d.files()
    dlba, dsize = f["DUMMY3M.DAT"]
    radio = r["radio"]
    write_file_inplace(out_bin, f["MGS/STAGE.DIR"][0], r["stage"])
    write_file_inplace(out_bin, dlba, dummy_area(r))
    for k in ("VOX", "DEMO"):
        flba = f[f"MGS/{k}.DAT"][0]
        for off, data in r[k.lower()].items():
            write_file_inplace(out_bin, flba + off // 2048, data)
    if r.get("exe"):
        for name in us_exe_names(f):
            write_file_inplace(out_bin, f[name][0], r["exe"])
    slba, off = radio_record(d)
    d.f.close()
    with open(out_bin, "r+b") as fh:
        fh.seek(slba * SECTOR)
        sec = np.frombuffer(fh.read(SECTOR), np.uint8).reshape(1, SECTOR).copy()
        data = bytearray(sec[0, 24:24 + 2048].tobytes())
        data[off + 2:off + 18] = record_extent(dlba, len(radio))
        sec[0, 24:24 + 2048] = np.frombuffer(bytes(data), np.uint8)
        sec = fix_form1(sec)
        fh.seek(slba * SECTOR)
        fh.write(sec.tobytes())
    log(f"  image : RADIO.DAT au LBA {dlba} (zone DUMMY3M.DAT), enregistrement secteur {slba} + {off}")


def radio_record(d):
    """(secteur, octet) de l'enregistrement de répertoire ISO de MGS/RADIO.DAT."""
    mgs = next(rec for rec in dir_records(d, *_root(d)) if rec[2] == "MGS")
    rec = next(rec for rec in dir_records(d, mgs[3], mgs[4]) if rec[2] == "RADIO.DAT")
    return rec[0], rec[1]


def record_extent(lba, size):
    """Octets 2 à 17 d'un enregistrement ISO : LBA et taille, petit puis gros boutiste."""
    return struct.pack("<I", lba) + struct.pack(">I", lba) + struct.pack("<I", size) + struct.pack(">I", size)


def _root(d):
    pvd = d.sector(16)
    root = pvd[156:156 + 34]
    return struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--us", required=True)
    ap.add_argument("--fr", required=True)
    ap.add_argument("--out")
    ap.add_argument("--pages-fr", default="", help="test : codes VOX US (hex, virgules) forcés en pages FR")
    a = ap.parse_args()
    force = {int(x, 16) for x in a.pages_fr.split(",") if x}
    r = build(a.us, a.fr, force=force)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        write_image(a.us, a.out, r)
        cue = Path(a.out).with_suffix(".cue")
        cue.write_text(f'FILE "{Path(a.out).name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n')


if __name__ == "__main__":
    main()
