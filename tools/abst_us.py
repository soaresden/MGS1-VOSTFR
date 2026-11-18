#!/usr/bin/env python3
"""
abst_us.py - Résumés de mission (« Read mission log? ») en français sur la version USA, avec la
case « French texts » (codec_us.py, .psxmod).

Les résumés sont des listes de chaînes GCL (`07 L texte\\0`) dans les deux scripts du stage `abst`
de STAGE.DIR. Le français prend 11 Ko de plus : il ne tient pas à la place de l'anglais. On
fabrique donc un nouveau stage `abst`, posé après RADIO.DAT et les banques déplacées (zone
DUMMY3M.DAT), et on fait pointer dessus l'entrée `abst` du répertoire de STAGE.DIR (secteur relatif
au début de STAGE.DIR, comme les banques VOX/DEMO déplacées) : STAGE.DIR garde sa taille.

Les scripts US et FR ont le même squelette, jeton pour jeton, une fois les suites de chaînes
regroupées. Le nouveau script est le script FR, où chaque valeur qui diffère de l'US reprend la
valeur US (codes 06 xxxx). Les chaînes passent aux accents de la police US (1F xx -> 80 xx ; un
glyphe absent est retiré). La fin du script (police locale) et tout le reste du stage (code de
l'overlay, autres ressources) restent ceux de la version US.

Mise en page : l'overlay US affiche des pages de 7 lignes, 2 pages au plus (nombre de lignes de
l'option -i : 7 ou 14), l'overlay FR des pages de 9 lignes (9 ou 18). Chaque résumé FR est donc
recollé puis recoupé à la largeur des lignes US (en pixels de la police US, plus large que les
lignes FR) ; quatre passages un peu resserrés (REWORD) pour tenir en 14 lignes. La liste de
chaînes change de taille : les tailles des conteneurs GCL qui l'englobent (commande, blocs,
procédure, table des procédures) sont recalculées ; celle de l'option -i est sur 8 bits et déjà
débordée dans la VF (le jeu ne s'en sert pas) : mise à jour modulo 256.
"""

import struct

import gcx
import usfont

NAME = "abst"
US_PAGE = 7               # lignes par page de l'overlay US
FR_PAGES = (9, 18)        # nombres de lignes des résumés FR (pages de 9 lignes)
WIDTH_PX = 360            # largeur d'une ligne (glyphes + 1 pixel) ; lignes US : 370 au plus
# passages resserrés (même sens) pour que les résumés les plus longs tiennent en 14 lignes
REWORD = [
    ("en utilisant une clé d'annulation d'urgence du dit code de mise a feu, et que cette clé est en "
     "la possession de Kenneth Baker", "avec une clé d'annulation d'urgence, détenue par Kenneth Baker"),
    ("Mais soudain, quelques secondes après cette conversation,", "Mais quelques secondes plus tard,"),
    ("Quoi qu'il en soit, quelques secondes après cette conversation,", "Quelques secondes plus tard,"),
    ("Les seuls moyens qui peuvent maintenant empêcher le lancement de l'ogive nucléaire sont",
     "Pour empêcher le lancement de l'ogive nucléaire, il ne reste que"),
    ("Les terroristes sont également en possession du code de mise", "Les terroristes ont aussi le code de mise"),
]


def _be16(b, p):
    return b[p] << 8 | b[p + 1]


def _be32(b, p):
    return struct.unpack_from(">I", b, p)[0]


class _Tokens:
    """Jetons d'un script GCL : [(genre, position, longueur)] ; « S » = chaîne."""

    def __init__(self, b):
        self.b, self.out = b, []
        self.boxes = []          # (position du champ taille, largeur, début, fin)

    def add(self, kind, p, n):
        self.out.append((kind, p, n))

    def block(self, p):
        b = self.b
        while b[p]:
            t = b[p]
            if t == 0x30:
                self.add("E", p, 2)
                self.boxes.append((p + 1, 1, p, p + 1 + b[p + 1]))
                self.expr(p + 2, p + 1 + b[p + 1])
                p += 1 + b[p + 1]
            elif t == 0x60:
                self.add("C", p, 6)
                self.boxes.append((p + 1, 2, p, p + 1 + _be16(b, p + 1)))
                self.values(p + 6, p + 1 + _be16(b, p + 1))
                p += 1 + _be16(b, p + 1)
            elif t == 0x70:
                self.add("K", p, 4)
                self.boxes.append((p + 1, 1, p, p + 1 + b[p + 1]))
                self.values(p + 4, p + 1 + b[p + 1])
                p += 1 + b[p + 1]
            else:
                raise ValueError(f"jeton {t:#x} inattendu en {p:#x}")

    def value(self, p):
        b = self.b
        t = b[p]
        if t & 0xF0 == 0x10:
            n, k = 4, "v"
        elif t in (9, 10):
            n, k = 5, "i"
        elif t in (1, 6, 8):
            n, k = 3, "h"
        elif t in (2, 3, 4, 0x20):
            n, k = 2, "b"
        elif t == 7:
            n, k = 2 + b[p + 1], "S"
        elif t == 0x40:
            self.add("B", p, 3)
            self.boxes.append((p + 1, 2, p, p + 1 + _be16(b, p + 1)))
            self.block(p + 3)
            return p + 1 + _be16(b, p + 1)
        elif t == 0x30:
            self.add("E", p, 2)
            self.boxes.append((p + 1, 1, p, p + 1 + b[p + 1]))
            self.expr(p + 2, p + 1 + b[p + 1])
            return p + 1 + b[p + 1]
        elif t == 0x50:
            n, k = 3, "O"
        else:
            raise ValueError(f"valeur {t:#x} inattendue en {p:#x}")
        self.add(k, p, n)
        return p + n

    def values(self, p, end):
        while p < end and self.b[p]:
            p = self.value(p)

    def expr(self, p, end):
        while p < end and self.b[p]:
            if self.b[p] == 0x31:
                self.add("op", p, 2)
                p += 2
            else:
                p = self.value(p)


def _script(b, g, boxes=False):
    """(jetons, fin du bloc principal) du script qui commence à l'octet g (+ conteneurs)."""
    t = _Tokens(b)
    proclen = _be32(b, g)
    pt = g + 4
    while _be32(b, pt):
        pt += 4
    p = g + 4
    while _be32(b, p):
        q = pt + 4 + _be16(b, p + 2)
        t.add("P", q, 3)
        t.boxes.append((q + 1, 2, q, q + 1 + _be16(b, q + 1)))
        t.block(q + 3)
        p += 4
    m = g + 4 + proclen
    t.add("M", m, 7)
    t.boxes.append((m + 5, 2, m + 4, m + 5 + _be16(b, m + 5)))
    t.block(m + 7)
    if boxes:
        return t.out, m + 4 + _be32(b, m), t.boxes
    return t.out, m + 4 + _be32(b, m)


def _splice(out, g, boxes, edits):
    """Remplace dans out (script seul, relatif à g) les plages edits = [(début, fin, octets)]
    (positions absolues du script en g) et corrige les tailles : conteneurs qui englobent la plage,
    décalages de la table des procédures, longueur des procédures ou du bloc principal."""
    proclen = _be32(out, 0)
    for s0, e0, data in sorted(edits, key=lambda i: -i[0]):
        n, a = len(data) - (e0 - s0), s0 - g
        for f, w, s, e in boxes:
            if not s - g <= a < e - g:
                continue
            f -= g
            v = (_be16(out, f) if w == 2 else out[f]) + n
            if not 0 <= v < 1 << 8 * w:
                raise ValueError("abst : conteneur GCL trop gros")
            out[f:f + w] = v.to_bytes(w, "big")
        pt = 4
        while _be32(out, pt):
            pt += 4
        if a < 4 + proclen:
            p = 4
            while _be32(out, p):
                off = _be16(out, p + 2)
                if pt + 4 + off > a:
                    out[p + 2:p + 4] = (off + n).to_bytes(2, "big")
                p += 4
            proclen += n
            out[0:4] = proclen.to_bytes(4, "big")
        else:
            m = 4 + proclen
            out[m:m + 4] = (_be32(out, m) + n).to_bytes(4, "big")
        out[a:e0 - g] = data
    return out


_WIDTHS = {}


def _px(s, font, n_us):
    """Largeur en pixels d'une ligne aux codes US (80 xx = lettre ajoutée), 1 pixel entre glyphes."""
    w = _WIDTHS.setdefault(id(font), {})
    total, i = 0, 0
    while i < len(s):
        if s[i] == 0x80:
            g = n_us + s[i + 1] - usfont.FIRST if s[i + 1] >= usfont.FIRST else None
            i += 2
        else:
            g = s[i] - 32
            i += 1
        if g is None:
            total += 7
            continue
        if g not in w:
            w[g] = len(usfont.decode(font, g)[1][0])
        total += w[g] + 1
    return total


def _reword():
    import exe_us
    return [(exe_us.fr_bytes(a), exe_us.fr_bytes(b)) for a, b in REWORD]


def _rewrap(lines, accents, font, used):
    """Lignes FR (1F xx) recollées, resserrées (REWORD) et recoupées à WIDTH_PX (codes US)."""
    n_us = len(usfont._glyphs(font)) - len(accents)
    text = b""
    for line in lines:
        line = line.strip(b" ")
        if line:
            text += (b" " if text and not text.endswith(b"-") else b"") + line
    for k, (a, b) in enumerate(_reword()):
        if a in text:
            used.add(k)
            text = text.replace(a, b)
    out, cur = [], b""
    for word in text.split(b" "):
        if not word:
            continue
        t = cur + b" " + word if cur else word
        if cur and _px(usfont.convert(t, accents), font, n_us) > WIDTH_PX:
            out.append(cur)
            t = word
        cur = t
    out.append(cur)
    return [usfont.convert(x, accents) for x in out]


def _runs(toks):
    """Jetons avec les suites de chaînes regroupées : ("SS", [chaînes])."""
    out = []
    for x in toks:
        if x[0] == "S":
            if out and out[-1][0] == "SS":
                out[-1][1].append(x)
            else:
                out.append(("SS", [x]))
        else:
            out.append(x)
    return out


def _stage(st):
    a = next((a, e) for n, a, e in gcx.stage_table(st) if n == NAME)
    return a


def _tags(st, a):
    tags, i = [], a + 4
    while st[i + 2]:
        tags.append(list(struct.unpack_from("<HBBi", st, i)))
        i += 8
    return tags


def strings(st_fr):
    """Chaînes FR du stage abst (1F xx) : pour choisir les accents de la police."""
    a, _ = _stage(st_fr)
    out = []
    for g in gcx.scripts(st_fr, a):
        toks, _ = _script(st_fr, g)
        out += [bytes(st_fr[p + 2:p + n]).split(b"\0")[0] for k, p, n in toks if k == "S"]
    return out + [b for _, b in _reword()]


def merge(su, gu, sf, gf, accents, font, used):
    """Script FR aux valeurs US, chaînes aux accents US, résumés recoupés en pages US, fin US."""
    tu, end_u = _script(su, gu)
    tf, end_f, boxes = _script(sf, gf, boxes=True)
    U, F = _runs(tu), _runs(tf)
    if len(U) != len(F) or any(x[0] != y[0] for x, y in zip(U, F)):
        raise ValueError("abst : squelettes US et FR différents")
    out = bytearray(sf[gf:end_f])
    stats = {"valeurs US": 0, "chaînes": 0, "glyphes retirés": 0, "résumés": 0, "pages": 0}
    edits = []
    for k, (x, y) in enumerate(zip(U, F)):
        if x[0] == "SS":
            # résumé (option -i : nombre de lignes, puis une chaîne vide et les lignes) : recoupé
            # en pages US de 7 lignes, nombre de lignes = 7 ou 14
            h = F[k - 1] if k else None
            if (h and h[0] == "h" and sf[h[1]] == 1 and _be16(sf, h[1] + 1) in FR_PAGES
                    and F[k - 2][0] == "O" and sf[F[k - 2][1] + 1] == ord("i")):
                ss = [bytes(sf[p + 2:p + n]).split(b"\0")[0] for _, p, n in y[1]]
                lines = _rewrap(ss[1:], accents, font, used)
                pages = -(-len(lines) // US_PAGE)
                if pages > 2:
                    raise ValueError(f"abst : résumé de {len(lines)} lignes : « {lines[0][:40]!r} »")
                lines = [b""] + lines + [b""] * (pages * US_PAGE - len(lines))
                data = b"".join(bytes([7, len(s) + 1]) + s + b"\0" for s in lines)
                s0, e0 = y[1][0][1], y[1][-1][1] + y[1][-1][2]
                out[h[1] + 1 - gf:h[1] + 3 - gf] = (pages * US_PAGE).to_bytes(2, "big")
                o = F[k - 2][1] + 2 - gf                       # taille de l'option -i, 8 bits
                out[o] = (out[o] + len(data) - (e0 - s0)) & 0xFF
                edits.append((s0, e0, data))
                stats["chaînes"] += len(lines)
                stats["résumés"] += 1
                stats["pages"] += pages
                continue
            for _, p, n in y[1]:                # jeton 07 L texte : n = 2 + L
                c = usfont.convert(bytes(sf[p + 2:p + n]), accents)
                stats["glyphes retirés"] += (n - 2 - len(c)) // 2
                out[p + 2 - gf:p + n - gf] = c.ljust(n - 2, b"\0")
                stats["chaînes"] += 1
            continue
        kind, pu, nu = x
        _, pf, nf = y
        a, b = su[pu:pu + nu], sf[pf:pf + nf]
        if kind in ("C", "K", "O"):         # commande, appel, lettre d'option : identiques
            i = {"C": (3, 5), "K": (2, 4), "O": (1, 2)}[kind]
            if a[i[0]:i[1]] != b[i[0]:i[1]]:
                raise ValueError(f"abst : {kind} différent en {pu:#x} / {pf:#x}")
            continue
        if kind not in ("v", "i", "h", "b") or a == b:
            continue
        if nu != nf:
            raise ValueError(f"abst : valeur de taille différente en {pu:#x}")
        if k + 1 < len(F) and F[k + 1][0] == "SS":      # nombre de lignes du résumé : FR
            continue
        out[pf - gf:pf - gf + nf] = a
        stats["valeurs US"] += 1
    out = _splice(out, gf, boxes, edits)
    out += su[end_u:end_u + 4 + _be32(su, end_u)]       # police locale US
    out += bytes(-len(out) % 4)
    return bytes(out), stats


def build(su, sf, accents, font):
    """Nouveau stage abst (US + résumés FR). Renvoie (octets du stage, stats).
    font : police US avec les lettres accentuées (usfont.extend), pour les largeurs."""
    au, eu = _stage(su)
    af, _ = _stage(sf)
    gus, gfs = gcx.scripts(su, au), gcx.scripts(sf, af)
    if len(gus) != len(gfs):
        raise ValueError("abst : nombre de scripts différent")
    tags = _tags(su, au)
    stats, used = {}, set()
    new = [merge(su, gu, sf, gf, accents, font, used) for gu, gf in zip(gus, gfs)]
    if len(used) != len(REWORD):
        raise ValueError(f"abst : passages REWORD introuvables : {sorted(set(range(len(REWORD))) - used)}")
    for _, s in new:
        for k, v in s.items():
            stats[k] = stats.get(k, 0) + v
    body, pos, k, gi = bytearray(), au + 2048, 0, 0
    while k < len(tags):
        if chr(tags[k][1]) != "c":
            n = (tags[k][3] + 2047) // 2048 * 2048
            body += su[pos:pos + n]
            pos += n
            k += 1
            continue
        j = k
        while j < len(tags) and chr(tags[j][1]) == "c":
            j += 1
        grp = tags[k:j]
        gs = [t for t in grp[:-1] if chr(t[2]) == "g"]
        first = gs[0][3]
        if [t[3] for t in gs] != [g - pos for g in gus[gi:gi + len(gs)]]:
            raise ValueError("abst : scripts du groupe inattendus")
        data = bytearray(su[pos:pos + first])
        for t, (b, _) in zip(gs, new[gi:gi + len(gs)]):
            t[3] = len(data)
            data += b
        gi += len(gs)
        old = grp[-1][3]
        grp[-1][3] = len(data)
        n = (len(data) + 2047) // 2048 * 2048
        body += data + bytes(n - len(data))
        pos += (old + 2047) // 2048 * 2048
        k = j
    if pos != eu and any(su[pos:eu]):
        raise ValueError("abst : données après les ressources")
    head = bytearray(su[au:au + 2048])
    struct.pack_into("<H", head, 2, 1 + len(body) // 2048)
    for i, t in enumerate(tags):
        struct.pack_into("<HBBi", head, 4 + 8 * i, *t)
    stats["secteurs"] = (struct.unpack_from("<H", su, au + 2)[0], 1 + len(body) // 2048)
    return bytes(head + body), stats


def repoint(st, sector):
    """STAGE.DIR avec l'entrée abst sur le secteur donné (relatif au début de STAGE.DIR)."""
    st = bytearray(st)
    n = struct.unpack_from("<I", st, 0)[0] // 12
    k = next(k for k in range(n) if st[4 + 12 * k:12 + 12 * k].rstrip(b"\0") == NAME.encode())
    struct.pack_into("<I", st, 12 + 12 * k, sector)
    return bytes(st)
