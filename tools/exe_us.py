#!/usr/bin/env python3
"""
exe_us.py - Textes FR des menus de l'EXE US : descriptions des objets et des armes (menus L2 / R2),
messages de la carte mémoire. Les noms courts (RATION, SOCOM…) restent en anglais, comme dans la VF.

Le jeu trouve ces textes par des tables de pointeurs (mêmes tables, même ordre dans les deux
EXE) : les textes FR (accents 1F xx -> 80 xx, usfont.py) vont à la place des textes US, et ce qui
ne tient pas dans deux fonctions jamais appelées (ni par l'EXE ni par les overlays des deux
disques) : la fin de 0x80081f24 (sub_8007F3F8 ; bandana.py en prend le début, 1092 octets) et
0x8008f4d4 (variante de CdControl de libcd, 308 octets ; ses 20 premiers octets : table des descriptions
FR du mod m9, lue par m9.py, pour que les deux cases restent indépendantes). Le texte « mode HARD » du détecteur de
mines est lu par un lui/addiu (0x8003da10) : réécrit aussi. Le chiffre du niveau de la carte PAN
est écrit par le jeu dans le texte, à une position fixe (sb à 0x8003d9e8) : remis sur le « 1 »
du texte FR.

La police US est plus large que la police FR : les descriptions sont remises en lignes de
~200 pixels (3 lignes au plus, le jeu n'en montre pas plus), mots coupés par un tiret recollés.
"""

import re
import struct

import pal
import usfont

BASE = 0x80010000 - 0x800
# (nom, table US, table FR, entrées)
TABLES = [("objets", 0x800A0B38, 0x8009F9FC, 26),
          ("armes", 0x800A0D24, 0x8009FBFC, 10),
          ("carte mémoire", 0x800A12A4, 0x800A017C, 28)]
HARD_US, HARD_FR, HARD_LUI = 0x800A0BA0, 0x8009FA64, 0x8003DA10
HARD_CODE = (0x3C05800A, 0x24A50BA0)            # lui a1, 0x800a ; addiu a1, a1, 0x0ba0
CARD_SB_US, CARD_SB_FR = 0x8003D9E8, 0x8003C5D0   # sb v0, N(a1) : chiffre du niveau de la carte PAN
CARD_SLOT = 17                                  # entrée de la carte PAN dans la table des objets
WMAX, LINES = 198, 3                            # boîte de description : ~200 pixels, 3 lignes
TITLE, NL, MARK = b"\xd0\x15", b"\x80|", b"\x01"  # fin du nom 《…》, retour à la ligne, repère du chiffre
# coquilles de la VF
FIXES = [(b"toutes les porte ", b"toutes les portes "), (b"llerRel", b"ller. Rel"),
         (b"Calmant Arr", b"Calmant. Arr"), (b"tirer Garder", b"tirer. Garder"),
         (b"activer Appuyer", b"activer. Appuyer"), (b"syst\x1f\x0fmes \x1f\x0flect", b"syst\x1f\x10mes \x1f\x0flect")]
# textes qui feraient 4 lignes avec la police US (plus large) : reformulés, même sens.
# {X} = icône du bouton de tir, {N} = chiffre du niveau de la carte (écrit par le jeu)
REWRITES = [
    (b"Ouvre\x80|toutes", "Carte d'identité. Une fois équipée, ouvre les portes de sécurité de niveau {N}."),
    (b"Les mines enterr", "Une fois équipé, les mines enterrées apparaissent sur l'écran radar."),
    (b"Fusil d'assaut", "Fusil d'assaut. Appuyer sur {X} pour tirer. Garder {X} enfoncé : tir automatique."),
    (b"fragmentation", "Grenade à fragmentation. Garder {X} pour dégoupiller, relâcher pour lancer."),
    (b"Paralyse tous les ennemis", "Paralyse tous les ennemis. Garder {X} pour dégoupiller, relâcher pour lancer."),
]


def fr_bytes(s):
    """Texte Unicode -> octets de la VF (accents 1F xx = Mac Roman xx + 0x7F, icône, repère)."""
    out = bytearray()
    for part in re.split(r"(\{X\}|\{N\})", s):
        if part == "{X}":
            out += b"\x80#\x90\x1d"
        elif part == "{N}":
            out += MARK
        else:
            for ch in part:
                b = ch.encode("mac_roman")[0]
                out += bytes([0x1F, b - 0x7F]) if b >= 0x80 else bytes([b])
    return bytes(out)
# table des descriptions FR du mod m9 : repère, puis M9, PSG1-T, -, CLAY.ZZZ (rang = bit du mode), lue par m9.py
FR_DESC, FR_DESC_MAGIC = 0x8008F4D4, b"FRDS"
CAVES = [(0x80081F24 + 1120, 0x80082640),      # après le code du bandana (1092 octets)
         (FR_DESC + 20, 0x8008F608),             # fonction de libcd jamais appelée (après la table)
         (0x80092A1C, 0x80092B28)]               # deux fonctions de la bibliothèque jamais appelées


def _w(b, a):
    return struct.unpack_from("<I", b, a - BASE)[0]


def _s(b, a):
    i = a - BASE
    return b[i:b.index(b"\0", i)]


def slots(exe_us, exe_fr):
    """[(adresse de l'entrée US, texte US, texte FR)] des entrées dont le texte change."""
    if pal.version(exe_us) != "US" or pal.version(exe_fr) != "FR":
        raise ValueError("EXE US (SLUS-00594 Rev 1) et EXE PAL France attendus")
    if (_w(exe_us, HARD_LUI), _w(exe_us, HARD_LUI + 4)) != HARD_CODE:
        raise ValueError("EXE US : lui/addiu du texte HARD inattendus (déjà patché ?)")
    out = []
    for _, tu, tf, n in TABLES:
        for k in range(n):
            su, sf = _s(exe_us, _w(exe_us, tu + 4 * k)), _s(exe_fr, _w(exe_fr, tf + 4 * k))
            if su != sf:
                out.append((tu + 4 * k, su, sf))
    return out


def hard_text(exe_fr):
    """Texte FR du détecteur de mines en HARD / EXTREME, avec le nom de l'objet 19 (la VF dit
    « Minendetektor », resté de la version allemande)."""
    t = _s(exe_fr, HARD_FR)
    name = _s(exe_fr, _w(exe_fr, TABLES[0][2] + 4 * 19))
    return name[:name.index(TITLE)] + t[t.index(TITLE):]


def m9_texts():
    """Descriptions FR du mod m9 (M9, PSG1-T, CLAY.ZZZ), dans l'ordre de la table FR_DESC."""
    import m9
    return [b"\xb0\x14" + name.encode("ascii") + TITLE + NL + fr_bytes(" ".join(lines))
            for name, lines in m9.DESCRIPTIONS["fr"].values()]


def texts(exe_us, exe_fr):
    """Textes FR (avec leurs 1F xx) : pour choisir les accents de la police."""
    return ([sf for _, _, sf in slots(exe_us, exe_fr)] + [hard_text(exe_fr)]
            + [fr_bytes(b) for _, b in REWRITES] + [y for _, y in FIXES] + m9_texts())


def widths(font):
    """Largeur en pixels d'un texte encodé US (police agrandie d'usfont, 1 pixel entre glyphes)."""
    tab = [(e >> 24) & 0xF for e in usfont._glyphs(font)]

    def width(t):
        w, i = 0, 0
        while i < len(t):
            c = t[i]
            if c >= 0x80:                       # code sur 2 octets
                x = t[i + 1]
                if c == 0x80 and x >= usfont.FIRST:
                    w += tab[x - 66] + 1        # accent ajouté (glyphe hankaku xx - 66)
                elif c == 0x90:
                    w += 13                     # icône de bouton
                i += 2
                continue
            w += tab[(c if c >= 0x20 else ord("1")) - 32] + 1   # MARK : le chiffre de la carte
            i += 1
        return w
    return width


def layout(t, width, wmax=WMAX):
    """Description (« 《nom》 » + texte) remise en lignes de wmax pixels ; None si > LINES lignes."""
    if TITLE not in t:
        return t
    head, body = t.split(TITLE, 1)
    body = re.sub(rb"-(?:\x80\||\|)(?=[a-z\x80\x01])", b"", body)     # mots coupés : recollés
    words = re.sub(rb"\x80\||\|", b" ", body).split()
    lines = []
    for wd in words:
        if lines and width(lines[-1] + b" " + wd) <= wmax:
            lines[-1] += b" " + wd
        else:
            lines.append(wd)
    if len(lines) > LINES or any(width(x) > wmax for x in lines):
        return None
    return head + TITLE + NL + NL.join(lines)


def prepare(exe_us, exe_fr, accents, font):
    """{texte US encodé : [entrées US (None = texte HARD, entier k = description m9 n° k)]},
    nombre de descriptions remises en lignes."""
    width = widths(font)
    card_slot = TABLES[0][1] + 4 * CARD_SLOT
    k = _w(exe_fr, CARD_SB_FR) & 0xFFFF
    want, wide = {}, 0
    extra = [(None, None, hard_text(exe_fr))] + [(k, None, x) for k, x in zip((1, 2, 4), m9_texts())]
    for a, _, sf in slots(exe_us, exe_fr) + extra:
        t = sf
        if a == card_slot:
            if t[k:k + 1] != b"1":
                raise ValueError("carte PAN : pas de « 1 » à la place du niveau dans le texte FR")
            t = t[:k] + MARK + t[k + 1:]
        for x, y in FIXES:
            t = t.replace(x, y)
        for key, body in REWRITES:
            if key in sf and TITLE in t:
                t = t[:t.index(TITLE) + 2] + NL + fr_bytes(body)
        if a == card_slot and MARK not in t:
            raise ValueError("carte PAN : repère du niveau perdu")
        t = usfont.convert(t, accents)
        lt = layout(t, width)
        if lt is None:
            raise ValueError(f"description trop longue pour {LINES} lignes : {sf[:40]!r}")
        wide += lt != t
        want.setdefault(lt, []).append(a)
    return want, wide


def patch(exe_us, exe_fr, accents, font):
    """EXE US avec les textes FR (accents de la police agrandie, usfont.extend). Renvoie (EXE, stats)."""
    out = bytearray(exe_us)
    sl = slots(exe_us, exe_fr)
    card_us = _w(exe_us, CARD_SB_US)
    if card_us >> 16 != 0xA0A2 or _w(exe_fr, CARD_SB_FR) >> 16 != 0xA0A2:
        raise ValueError("sb du niveau de la carte inattendu")
    empty = next(_w(exe_us, t[1] + 4 * k) for t in TABLES for k in range(t[3])
                 if not _s(exe_us, _w(exe_us, t[1] + 4 * k)))
    # place libre : les textes US remplacés (référencés seulement par ces tables), puis les grottes
    old = {_w(exe_us, a): su for a, su, _ in sl if su}
    old[HARD_US] = _s(exe_us, HARD_US)
    free = []
    for a, s in sorted(old.items()):
        e = a + len(s) + 1
        if free and free[-1][1] == a:
            free[-1][1] = e
        else:
            free.append([a, e])
    free += [list(c) for c in CAVES]
    want, wide = prepare(exe_us, exe_fr, accents, font)

    def place(compact):
        spans, where = [list(f) for f in free], {}
        for t in sorted(want, key=len, reverse=True):
            if not t:
                where[t] = (empty, b"")
                continue
            b = t.replace(NL, b"|") if compact else t   # retour à la ligne sur 1 octet (font.c)
            f = next((f for f in spans if f[1] - f[0] > len(b)), None)
            if f is None:
                return None
            where[t] = (f[0], b)
            f[0] += len(b) + 1
        return where, compact

    res = place(False) or place(True)
    if res is None:
        raise ValueError("textes FR des menus : pas assez de place dans l'EXE")
    where, compact = res
    for a, e in free:
        out[a - BASE:e - BASE] = bytes(e - a)
    out[FR_DESC - BASE:FR_DESC + 4 - BASE] = FR_DESC_MAGIC
    used = 0
    for t, slots_ in want.items():
        a, b = where[t]
        if b:
            if MARK in b:                       # chiffre du niveau de la carte : le sb vise sa place
                struct.pack_into("<I", out, CARD_SB_US - BASE, card_us & 0xFFFF0000 | b.index(MARK))
                b = b.replace(MARK, b"1")
            out[a - BASE:a - BASE + len(b)] = b
            if any(lo <= a < hi for lo, hi in CAVES):
                used += len(b) + 1
        for slot in slots_:
            if slot is not None and slot < 8:       # description du mod m9 : table FR_DESC
                struct.pack_into("<I", out, FR_DESC + 4 * slot - BASE, a)
            elif slot is None:
                struct.pack_into("<I", out, HARD_LUI - BASE, 0x3C050000 | (a + 0x8000) >> 16)
                struct.pack_into("<I", out, HARD_LUI + 4 - BASE, 0x24A50000 | a & 0xFFFF)
            else:
                struct.pack_into("<I", out, slot - BASE, a)
    return bytes(out), {"entrées": len(sl) + 4, "textes": len(want), "grottes": used,
                        "retour court": compact, "remises en lignes": wide}
