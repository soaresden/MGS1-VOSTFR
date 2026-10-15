#!/usr/bin/env python3
"""
demo_vostfr.py - Cinématiques en VOSTFR : DEMO.DAT français + audio anglais.

Dans les deux versions PAL, chaque banque de DEMO.DAT contient exactement la même suite
de blocs son (même nombre, même taille) : le doublage FR a été calé sur la durée des
scènes. On garde donc le DEMO.DAT FR (sous-titres, animations, textures traduites) et on
recopie dedans, bloc par bloc, l'audio du DEMO.DAT UK. Le fichier garde la même taille.

  python demo_vostfr.py DEMO_FR.DAT DEMO_UK.DAT DEMO_SORTIE.DAT
"""

import sys
import vox


def patch(fr, uk):
    out = bytearray(fr)
    bf, bu = vox.banks(fr), vox.banks(uk)
    if len(bf) != len(bu):
        raise SystemExit(f"nombre de banques différent : FR {len(bf)}, UK {len(bu)}")
    swapped = 0
    for n, ((sf, _), (su, _)) in enumerate(zip(bf, bu)):
        sons_fr = [(o, s) for c, o, s in vox.blocks(fr, sf) if c == vox.SOUND]
        sons_uk = [(o, s) for c, o, s in vox.blocks(uk, su) if c == vox.SOUND]
        if [s for _, s in sons_fr] != [s for _, s in sons_uk]:
            raise SystemExit(f"banque {n} : blocs son incompatibles")
        for (of, s), (ou, _) in zip(sons_fr, sons_uk):
            if out[of + 4:of + s] != uk[ou + 4:ou + s]:
                out[of + 4:of + s] = uk[ou + 4:ou + s]
                swapped += 1
    return bytes(out), len(bf), swapped


def main():
    fr, uk = open(sys.argv[1], "rb").read(), open(sys.argv[2], "rb").read()
    out, nb, swapped = patch(fr, uk)
    open(sys.argv[3], "wb").write(out)
    print(f"{nb} cinématiques, {swapped} blocs son remplacés -> {sys.argv[3]}")


if __name__ == "__main__":
    main()
