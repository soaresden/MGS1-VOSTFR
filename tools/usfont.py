#!/usr/bin/env python3
"""
usfont.py - Lettres accentuées pour la version USA (textes FR affichés par l'EXE US).

La version FR écrit les accents « 1F xx » et son EXE les dessine avec les glyphes 96 et plus
de sa police font.res (224 glyphes, ordre Mac Roman : glyphe 95 + xx ; é = 1F 0F = glyphe
110). L'EXE US ignore les codes de contrôle 1F et sa police n'a que 96 glyphes (ASCII).

Mais son moteur (font.c, comme la décompilation FoxdieTeam) dessine déjà un caractère « 80 xx »
avec xx > 0x80 depuis la même table : put_hankaku_4bpp -> get_hantable(xx) = glyphe xx - 66
(largeur proportionnelle lue dans la table, comme l'ASCII). On ajoute donc à la police US les
lettres accentuées utilisées (glyphes 96, 97… = codes 80 A2, 80 A3…), dessinées à partir des
lettres US (accent au-dessus, cédille dessous : la police FR, à empattements, détonnait), et on
réécrit les textes ; aucun code de l'EXE ne change.

font.res : en-tête u32 BE taille de la table 1 (8 + 4 × glyphes), u32 BE début des glyphes
pleine chasse (zendata[0]) ; table 1 : u32 BE = décalage Y << 28 | largeur << 24 | position
dans la table 2 (qui commence après la table 1) ; table 2 : pixels sur 2 bits, 12 lignes.
Il vit dans le pack résident du stage « init » de STAGE.DIR (section 'r' 'd' : entrées
{u16 hash, u8 extension, u8 0, u32 taille, données}, font = 0xCA68 'r') ; la section est
complétée au secteur : la police agrandie doit tenir dans les secteurs d'origine (636 octets
libres en US, 15 glyphes de 7 pixels = 379 octets).
"""

import re
import struct

HASH_FONT = 0xCA68
FIRST = 0xA2          # get_hantable(0xA2) = 0xA2 - 34 - 32 = 96 : premier glyphe ajouté


def used(texts):
    """Codes xx des accents 1F xx présents dans des textes."""
    out = set()
    for t in texts:
        out.update(m.group()[1] for m in re.finditer(rb"\x1f.", t, re.S))
    return out


def _glyphs(font):
    a = struct.unpack_from(">I", font, 0)[0]
    return [struct.unpack_from(">I", font, 8 + 4 * i)[0] for i in range((a - 8) // 4)]


def decode(font, i):
    """Glyphe i : (décalage Y, lignes de pixels 0-3)."""
    a = struct.unpack_from(">I", font, 0)[0]
    e = struct.unpack_from(">I", font, 8 + 4 * i)[0]
    w, pos, px = (e >> 24) & 0xF, a + (e & 0xFFFFFF), []
    while len(px) < w * 12:
        px += [(font[pos] >> s) & 3 for s in (6, 4, 2, 0)]
        pos += 1
    return e >> 28, [px[r * w:(r + 1) * w] for r in range(12)]


def encode(rows):
    px = [v for r in rows for v in r]
    px += [0] * (-len(px) % 4)
    return bytes(px[i] << 6 | px[i + 1] << 4 | px[i + 2] << 2 | px[i + 3] for i in range(0, len(px), 4))


# Accents dessinés dans le style de la police US (linéale) : la police FR a des empattements et
# ses accents, recopiés tels quels, paraissaient petits et décalés à côté des lettres US.
MARKS = {
    "́": [[0, 1, 3], [1, 3, 0]],      # aigu
    "̀": [[3, 1, 0], [0, 3, 1]],      # grave
    "̂": [[0, 3, 0], [3, 0, 3]],      # circonflexe
    "̈": [[3, 0, 3]],                 # tréma
}
GUILL = [[0, 0, 3, 0, 0, 3], [0, 3, 0, 0, 3, 0], [3, 0, 0, 3, 0, 0], [0, 3, 0, 0, 3, 0], [0, 0, 3, 0, 0, 3]]


def synth(us_font, xx):
    """Glyphe US du caractère FR 1F xx (Mac Roman xx + 0x7F), ou None."""
    import unicodedata
    if xx + 0x7F > 0xFF:
        return None
    ch = bytes([xx + 0x7F]).decode("mac_roman")
    if ch in "«»":
        rows = [[0] * 7 for _ in range(12)]
        for r, line in enumerate(GUILL):
            for x, v in enumerate(line if ch == "«" else line[::-1]):
                rows[5 + r][x] = v
        return 0, rows
    if ch in "œŒ":                         # o + e (O + E) collés, trait commun fusionné
        _, o = decode(us_font, ord(ch == "œ" and "o" or "O") - 32)
        _, e = decode(us_font, ord(ch == "œ" and "e" or "E") - 32)
        lo = max(i for i in range(len(o[0])) if any(r[i] for r in o)) + 1
        fe = min(i for i in range(len(e[0])) if any(r[i] for r in e))
        rows = [ro[:lo - 1] + [max(ro[lo - 1], re_[fe])] + re_[fe + 1:] for ro, re_ in zip(o, e)]
        return 0, rows
    nfd = unicodedata.normalize("NFD", ch)
    base, marks = nfd[0], nfd[1:]
    if not base.isascii() or len(marks) != 1 or marks not in MARKS and marks != "̧":
        return None
    yo, rows = decode(us_font, ord(base) - 32)
    rows = [list(r) for r in rows]
    ink = [i for i in range(len(rows[0])) if any(r[i] for r in rows)]
    top = min(r for r in range(12) if any(rows[r]))
    if base in "ij":                       # î, ï : sans le point
        for r in range(top, top + 2):
            rows[r] = [0] * len(rows[r])
        top = min(r for r in range(12) if any(rows[r]))
    cx = (ink[0] + ink[-1]) // 2
    if marks == "̧":                  # cédille sous la lettre (dernière ligne)
        for x, v in zip(range(cx - 1, cx + 1), (1, 3)):
            rows[11][x] = v
        return yo, rows
    m = MARKS[marks]
    y0 = max(0, top - 1 - len(m)) if top >= 5 else 0
    for r, line in enumerate(m):
        for x, v in enumerate(line):
            if v and 0 <= cx - 1 + x < len(rows[0]):
                rows[y0 + r][cx - 1 + x] = v
    return yo, rows


def extend(us_font, codes):
    """Police US + lettres accentuées des codes 1F xx. Renvoie (police, {xx: octet après 80})."""
    a, b = struct.unpack_from(">II", us_font, 0)
    us_tab = _glyphs(us_font)
    t2 = bytearray(us_font[a:b])
    zen = us_font[b:]
    new, mapping = [], {}
    for xx in sorted(codes):
        g = synth(us_font, xx)
        if g is None:
            continue                      # 1F 96 (une seule fois en VF, glyphe vide) : retiré
        yo, rows = g
        w = len(rows[0])
        if w > 15:
            raise ValueError(f"glyphe 1F {xx:02x} trop large")
        new.append(yo << 28 | w << 24 | len(t2))
        t2 += encode(rows)
        mapping[xx] = FIRST + len(mapping)
    if FIRST + len(mapping) > 0xFE:
        raise ValueError("trop de glyphes")
    tab = us_tab + new
    na = 8 + 4 * len(tab)
    while (na + len(t2)) % 4:
        t2 += b"\0"
    out = struct.pack(">II", na, na + len(t2)) + b"".join(struct.pack(">I", e) for e in tab)
    return bytes(out + t2 + zen), mapping


def convert(text, mapping):
    """1F xx -> 80 code (accent ajouté), ou rien si le glyphe n'existe pas."""
    return re.sub(rb"\x1f(.)", lambda m: b"\x80" + bytes([mapping[m.group(1)[0]]])
                  if m.group(1)[0] in mapping else b"", text, flags=re.S)


def _init_pack(st):
    """(position de l'en-tête 8 octets de la section, position des données, taille)."""
    import gcx
    a = next(x[1] for x in gcx.stage_table(st) if x[0] == "init")
    i, pos = a + 4, a + 2048
    while True:
        tid, mode, ext, sz = struct.unpack_from("<HBBi", st, i)
        if mode == 0:
            raise ValueError("pack résident introuvable")
        if (chr(mode), chr(ext)) == ("r", "d"):
            return i, pos, sz
        pos += (sz + 2047) // 2048 * 2048
        i += 8


def read_font(st):
    _, pos, sz = _init_pack(st)
    pack = st[pos:pos + sz]
    p = 0
    while p < len(pack):
        h, e, _, n = struct.unpack_from("<HBBI", pack, p)
        if h == HASH_FONT and e == ord("r"):
            return bytes(pack[p + 8:p + 8 + n])
        p += 8 + n
    raise ValueError("font.res introuvable")


def patch_stage(st, font):
    """STAGE.DIR avec font.res remplacée (même nombre de secteurs pour la section)."""
    st = bytearray(st)
    tag, pos, sz = _init_pack(st)
    pack = st[pos:pos + sz]
    out, p = bytearray(), 0
    while p < len(pack):
        h, e, z, n = struct.unpack_from("<HBBI", pack, p)
        data = pack[p + 8:p + 8 + n]
        if h == HASH_FONT and e == ord("r"):
            data = font
        out += struct.pack("<HBBI", h, e, z, len(data)) + data
        p += 8 + n
    room = (sz + 2047) // 2048 * 2048
    if len(out) > room:
        raise ValueError(f"pack résident : {len(out)} octets pour {room}")
    if any(st[pos + sz:pos + room]):
        raise ValueError("fin de section non vide")
    st[pos:pos + room] = bytes(out).ljust(room, b"\0")
    struct.pack_into("<i", st, tag + 4, len(out))
    return bytes(st), len(out), room
