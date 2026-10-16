#!/usr/bin/env python3
"""
psg1loup.py - Patch optionnel : le PSG1 à la place de Meryl, dans le passage de Sniper Wolf.

Dans le jeu d'origine, Sniper Wolf blesse Meryl dans le passage souterrain (s10a) et repousse
Snake tant qu'il n'a pas de fusil : il faut retourner chercher le PSG1 à l'armurerie (s04a),
puis revenir. En ressortant du passage, la progression P (var GCL 0x0a) passe à 0x92 ; au
retour, Meryl n'est plus là (il reste du sang), cinématique, puis combat. Avec ce patch, il
suffit de ressortir et de revenir : le PSG1 attend à la place de Meryl, à côté du sang.

Une boîte de munitions PSG1 du passage (objet « sa89c », en -3500, -30000, 9000, qui n'apparaît
d'origine que si l'on a déjà le PSG1) est retouchée dans les scripts GCL de s10a (2 scripts) et
s10ar, sans changer de taille :
- condition `GM_Weapons[PSG1] >= 0` (`11 80 00 34 02 00 31 0E`) -> `P >= 0x92`
  (`11 00 00 0A 02 92 31 0E` : Meryl partie ; pas avant, quand Wolf repousse Snake) ;
- position -> (-800, -30000, 19250), à côté du sang de Meryl (objet sadc9 en -1226, -30000, 19243) ;
- `-b b2` (munitions) -> `-b b0` (l'arme, comme à l'armurerie) ; message « PSG1 ».
Une fois ramassée, la boîte ne revient plus (drapeau d'origine de l'objet). Comme tous les objets
du jeu, elle n'existe pas en mode Extreme (proc p3353) : le chemin par l'armurerie reste.

  python psg1loup.py image.bin [image2.bin ...]     patch en place (STAGE.DIR)
"""

import sys

import gcx, psxiso
from cdsector import write_file_inplace

STAGES = ("s10a", "s10ar")
# condition + début de l'objet « sa89c », tels quels dans les versions FR et UK
BOX = bytes.fromhex("300b118000340200310e3100" "4000" "5d600059" "9906" "07" "068767" "06a89c"
                    "50700a" "01f254" "018ad0" "012328" "5062030202" "5069030209" "506e04010005"
                    "506d130710") + b"PSG1/BULLET * 5" + bytes(1)
NEW_COND = bytes.fromhex("1100000a0292310e")       # progression (var 0x0a) >= 0x92
NEW_POS = bytes.fromhex("01fce0" "018ad0" "014b32")   # -800, -30000, 19250


def patch_stage(st):
    """STAGE.DIR -> (STAGE.DIR patché, nombre de boîtes retouchées)."""
    out = bytearray(st)
    n = 0
    for name, a, e in gcx.stage_table(st):
        if name not in STAGES:
            continue
        i = st.find(BOX, a, e)
        if i == -1:
            raise SystemExit(f"{name} : boîte de munitions PSG1 introuvable (déjà patchée ?)")
        while i != -1:
            out[i + 2:i + 10] = NEW_COND
            p = i + BOX.index(bytes.fromhex("50700a")) + 3
            out[p:p + 9] = NEW_POS
            b = i + BOX.index(bytes.fromhex("5062030202"))
            out[b + 4] = 0x00                            # -b b2 -> -b b0
            m = i + len(BOX) - 16
            out[m:m + 5] = b"PSG1" + bytes(1)
            n += 1
            i = st.find(BOX, i + 1, e)
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
        print(p, ":", patch_image(p), "boîtes (PSG1 à la place de Meryl)")


if __name__ == "__main__":
    main()
