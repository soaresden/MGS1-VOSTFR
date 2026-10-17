#!/usr/bin/env python3
"""
cartes.py - Patch optionnel : les portes à carte s'ouvrent avec la carte dans l'inventaire, et la
carte s'équipe alors toute seule (son icône apparaît dans la case objet : on voit qu'elle a servi).

Dans le jeu d'origine, il faut **équiper** la carte (menu des objets) pour qu'une porte s'ouvre.
La condition est écrite dans les scripts GCL de STAGE.DIR, dans la procédure de la porte :
`0xd86 (niveau >= N && (acteur != Snake || GM_Item == 17)) { voyant ; ouverture } -e { refus }`
(GM_Item = linkvar 15, objet équipé ; 17 = IT_Card ; niveau = linkvar 54 = GM_Items[IT_Card] ;
acteur = argument de la procédure, Snake = 0x21CA ; variantes sans le terme acteur, ou avec un
terme de progression en plus). Le patch réécrit cette commande à taille égale :
- condition : le test `GM_Item == 17` disparaît, avec le terme acteur et ses opérateurs
  (19 octets) ou seulement son `&&` (10 octets) ;
- bloc d'ouverture : on ajoute `GM_Item = 17` (commande d'évaluation, 19 ou 20 octets) ;
- s'il manque de la place (condition sans terme acteur), le test de refus du bloc -e
  `X && GM_Item == 17` devient `X` (10 octets), ou `if (GM_Item == 17) { ... }` est remplacé par
  son bloc : le voyant rouge / le bip de refus viennent alors dès qu'on présente une carte trop
  faible, équipée ou non ; en dernier recours, des nombres 0-255 codés en short passent en octet.
Toutes les longueurs englobantes (taille et décalage des options de la commande, blocs,
expressions, options) sont ajustées ; rien ne bouge hors de la commande. Là où la place manque
encore, repli : `GM_Item == 17` -> `1 == 1` (porte ouverte sans équiper la carte, sans icône).
La carte s'équipe aussi quand un garde ouvre une porte à carte (même procédure), et remplace
l'objet que Snake avait en main.

  python cartes.py image.bin [image2.bin ...]     patch en place (STAGE.DIR)
"""

import struct
import sys

import gcx, psxiso
from cdsector import write_file_inplace

EQUIPPED = bytes.fromhex("1180001e02113109")   # GM_Item == IT_Card
ALWAYS = bytes.fromhex("0100010100013109")     # 1 == 1
LEVEL = bytes.fromhex("1180006c")              # GM_Items[IT_Card] (niveau de la carte)
EQ = EQUIPPED.hex()
WHO = ("20020621ca310a", "20040621ca310a")     # acteur ($2 ou $4) != Snake
REFUS = ("200702003109", "200802003109", "20020621ca3109", "20040621ca3109")   # X de `X && GM_Item == 17`
# GM_Item = 17 : commande d'évaluation (0x64C0), valeur en octet ou en short
EQUIP = {19: bytes.fromhex("60001264c00d" "300b" "1180001e" "0211" "3114" "3100" "00"),
         20: bytes.fromhex("60001364c00e" "300c" "1180001e" "010011" "3114" "3100" "00")}


class _Exprs(gcx._Walker):
    """Relève les expressions (début, fin) d'un script GCX."""

    def __init__(self, b):
        super().__init__(b, lambda *a: None)
        self.spans = []

    def expr(self, p, end, cmd, opt=None):
        self.spans.append((p, end))
        super().expr(p, end, cmd, opt)


def expressions(st, g):
    w = _Exprs(st)
    proclen = gcx._be32(st, g)
    pt = g + 4
    procs = []
    while gcx._be32(st, pt):
        procs.append(gcx._be16(st, pt + 2))
        pt += 4
    for off in procs:
        w.block(pt + 4 + off + 3, None)
    w.block(g + 4 + proclen + 4 + 3, None)
    return w.spans


def _fields(b, p):
    """Champs de longueur de la commande 0x60 en p : [(position, largeur, début de l'étendue, valeur)]."""
    out = []

    def block(p):
        while b[p]:
            p = instr(p)

    def instr(p):
        t = b[p]
        if t == 0x30:
            out.append((p + 1, 1, p + 1, b[p + 1]))
            return p + 1 + b[p + 1]
        if t == 0x60:
            size = gcx._be16(b, p + 1)
            out.append((p + 1, 2, p + 1, size))
            out.append((p + 5, 1, p + 5, b[p + 5]))
            values(p + 6, p + 1 + size)
            return p + 1 + size
        if t == 0x70:
            out.append((p + 1, 1, p + 1, b[p + 1]))
            values(p + 4, p + 1 + b[p + 1])
            return p + 1 + b[p + 1]
        raise ValueError(f"GCX : instruction {t:#x} en {p:#x}")

    def values(p, end):
        while p < end and b[p]:
            t = b[p]
            if t & 0xF0 == 0x10:
                p += 4
            elif t in (9, 10):
                p += 5
            elif t in (1, 6, 8):
                p += 3
            elif t in (2, 3, 4, 0x20):
                p += 2
            elif t == 7:
                p += 2 + b[p + 1]
            elif t == 0x40:
                n = gcx._be16(b, p + 1)
                out.append((p + 1, 2, p + 1, n))
                block(p + 3)
                p += 1 + n
            elif t == 0x30:
                out.append((p + 1, 1, p + 1, b[p + 1]))
                p += 1 + b[p + 1]
            elif t == 0x50:
                out.append((p + 2, 1, p + 2, b[p + 2]))
                p += 3
            else:
                raise ValueError(f"GCX : valeur {t:#x} en {p:#x}")

    instr(p)
    return out


def _splice(b, cmd, mods):
    """Applique mods [(position, longueur remplacée, octets)] dans la commande en cmd et ajuste les
    longueurs qui les contiennent. -> octets de la commande (même taille exigée)."""
    flds = _fields(b, cmd)
    end = cmd + 1 + gcx._be16(b, cmd + 1)
    out = bytearray(b[cmd:end])
    for fpos, w, s, v in flds:
        d = sum(len(new) - n for pos, n, new in mods if s <= pos and pos + n <= s + v and (n or pos < s + v))
        if d:
            v += d
            assert 0 <= v < (1 << (8 * w))
            out[fpos - cmd:fpos - cmd + w] = v.to_bytes(w, "big")
    for pos, n, new in sorted(mods, reverse=True):
        out[pos - cmd:pos - cmd + n] = new
    assert len(out) == end - cmd
    return bytes(out)


def _new_cond(h):
    """Condition sans le test de carte équipée (hex), ou None si forme inconnue."""
    for who in WHO:
        k = h.find(who + EQ + "31123113")
        if k >= 0 and k % 2 == 0:
            return h[:k] + h[k + len(who + EQ + "31123113"):]
    if h.endswith(EQ + "31133100") and h.count(EQ) == 1:
        return h[:-len(EQ + "31133100")] + "3100"
    if h.startswith(EQ) and h.endswith("31133100") and h.count(EQ) == 1:
        return h[len(EQ):-len("31133100")] + "3100"
    return None


def _indicator(st, cmd, p, q):
    """Réécrit la commande 0xd86 en cmd (condition = expression [p, q)). -> octets ou None."""
    old = st[p:q].hex()
    new = _new_cond(old)
    if new is None:
        return None
    mods = [(p, q - p, bytes.fromhex(new))]
    room = (q - p) - len(new) // 2
    o = q                                          # bloc d'ouverture
    if st[o] != 0x40:
        return None
    blk_end = o + gcx._be16(st, o + 1)             # octet 00 de fin du bloc
    end = cmd + 1 + gcx._be16(st, cmd + 1)
    if room < 19:                                  # place prise sur le test de refus (bloc -e)
        for x, y in _all_exprs(st, blk_end + 1, end):
            h = st[x:y].hex()
            for r in REFUS:
                if h == r + EQ + "31133100":
                    mods.append((x, y - x, bytes.fromhex(r + "3100")))
                    room += 10
                    break
            if room >= 19:
                break
    if room < 19:                                  # refus `if (GM_Item == 17) { ... }` : on garde le bloc
        for x, y in _all_exprs(st, blk_end + 1, end):
            c = x - 8
            if (st[x:y].hex() == EQ + "3100" and st[c] == 0x60 and st[c + 3:c + 5] == bytes.fromhex("0d86")
                    and st[y] == 0x40):
                csize = gcx._be16(st, c + 1)
                body = st[y + 3:y + gcx._be16(st, y + 1)]           # instructions du bloc, sans le 00 final
                if c + 1 + csize == y + 1 + gcx._be16(st, y + 1) + 1 and st[c + csize] == 0:   # ni -e ni -i
                    mods.append((c, 1 + csize, body))
                    room += 1 + csize - len(body)
                    break
    if room < 19:                                  # nombres 0-255 en short -> octet
        for x in _shorts(st, cmd + 6, end):
            if room >= 19:
                break
            if not any(m <= x < m + n for m, n, _ in mods):
                mods.append((x, 3, bytes([2, st[x + 2]])))
                room += 1
    if room < 19:
        return None
    k = 20 if room >= 20 else 19
    mods.append((blk_end, 0, EQUIP[k] + bytes(room - k)))
    return _splice(st, cmd, mods)


def _shorts(b, a, end):
    """Jetons short (0x01) de valeur 0-255 entre a et end, expressions et blocs compris."""
    out = []

    def values(p, end):
        while p < end and b[p]:
            t = b[p]
            if t == 0x31:
                p += 2
            elif t == 1:
                if b[p + 1] == 0:
                    out.append(p)
                p += 3
            elif t & 0xF0 == 0x10:
                p += 4
            elif t in (9, 10):
                p += 5
            elif t in (6, 8):
                p += 3
            elif t in (2, 3, 4, 0x20):
                p += 2
            elif t == 7:
                p += 2 + b[p + 1]
            elif t == 0x40:
                q = p + 3
                while b[q]:
                    if b[q] == 0x60:
                        values(q + 6, q + 1 + gcx._be16(b, q + 1))
                        q += 1 + gcx._be16(b, q + 1)
                    elif b[q] in (0x30, 0x70):
                        values(q + (2 if b[q] == 0x30 else 4), q + 1 + b[q + 1])
                        q += 1 + b[q + 1]
                    else:
                        raise ValueError(f"GCX : instruction {b[q]:#x} en {q:#x}")
                p += 1 + gcx._be16(b, p + 1)
            elif t == 0x30:
                values(p + 2, p + 1 + b[p + 1])
                p += 1 + b[p + 1]
            elif t == 0x50:
                p += 3
            else:
                raise ValueError(f"GCX : valeur {t:#x} en {p:#x}")

    values(a, end)
    return out


def _all_exprs(st, a, end):
    """Expressions (début, fin) des valeurs entre a et end (options d'une commande)."""
    w = _Exprs(st)
    w.values(a, end, None)
    return w.spans


def patch_stage(st):
    """STAGE.DIR -> (STAGE.DIR patché, nombre de portes retouchées). Portes avec icône : patch_stage.icons."""
    out = bytearray(st)
    n = icons = 0
    for name, a, e in gcx.stage_table(st):
        for g in gcx.scripts(st, a):
            for p, q in expressions(st, g):
                ex = st[p:q]
                if LEVEL not in ex or EQUIPPED not in ex:
                    continue
                cmd = p - 8
                new = None
                if st[cmd] == 0x60 and st[cmd + 3:cmd + 5] == bytes.fromhex("0d86") and st[cmd + 6] == 0x30:
                    new = _indicator(st, cmd, p, q)
                if new is not None:
                    out[cmd:cmd + len(new)] = new
                    n += 1
                    icons += 1
                    continue
                k = ex.find(EQUIPPED)
                while k != -1:
                    out[p + k:p + k + 8] = ALWAYS
                    n += 1
                    k = ex.find(EQUIPPED, k + 8)
    patch_stage.icons = icons
    return bytes(out), n


def patch_image(path):
    d = psxiso.Disc(path)
    lba, size = d.files()["MGS/STAGE.DIR"]
    new, n = patch_stage(d.read(lba, size))
    d.f.close()
    write_file_inplace(path, lba, new)
    return n


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        n = patch_image(p)
        print(p, ":", n, "portes à carte sans équiper la carte, dont", patch_stage.icons, "qui l'équipent")


if __name__ == "__main__":
    main()
