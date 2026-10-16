#!/usr/bin/env python3
"""
cartes.py - Patch optionnel : les portes à carte s'ouvrent avec la carte dans l'inventaire.

Dans le jeu d'origine, il faut **équiper** la carte (menu des objets) pour qu'une porte s'ouvre.
La condition est écrite dans les scripts GCL de STAGE.DIR, sous la forme
`niveau de carte >= N && GM_Item == 17` (GM_Item = linkvar 15, objet équipé ; 17 = IT_Card ;
niveau = linkvar 54 = GM_Items[IT_Card]), parfois avec un terme en plus (porte à deux côtés).
Le patch remplace, dans les seules expressions qui testent aussi le niveau de carte, le test
`GM_Item == 17` (jetons `11 80 00 1E 02 11 31 09`, variable / octet / opérateur ==) par
`1 == 1` (`01 00 01 01 00 01 31 09`, même longueur : aucun script ne change de taille).
Les autres tests de `GM_Item == 17` (« bip » quand on présente une carte trop faible) ne
changent pas : ils ne se déclenchent toujours que carte équipée.

  python cartes.py image.bin [image2.bin ...]     patch en place (STAGE.DIR)
"""

import sys

import gcx, psxiso
from cdsector import write_file_inplace

EQUIPPED = bytes.fromhex("1180001e02113109")   # GM_Item == IT_Card
ALWAYS = bytes.fromhex("0100010100013109")     # 1 == 1
LEVEL = bytes.fromhex("1180006c")              # GM_Items[IT_Card] (niveau de la carte)


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


def patch_stage(st):
    """STAGE.DIR -> (STAGE.DIR patché, nombre de tests remplacés)."""
    out = bytearray(st)
    n = 0
    for name, a, e in gcx.stage_table(st):
        for g in gcx.scripts(st, a):
            for p, end in expressions(st, g):
                ex = bytes(out[p:end])
                if LEVEL not in ex or EQUIPPED not in ex:
                    continue
                k = ex.find(EQUIPPED)
                while k != -1:
                    out[p + k:p + k + 8] = ALWAYS
                    n += 1
                    k = ex.find(EQUIPPED, k + 8)
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
        print(p, ":", patch_image(p), "portes à carte sans équiper la carte")


if __name__ == "__main__":
    main()
