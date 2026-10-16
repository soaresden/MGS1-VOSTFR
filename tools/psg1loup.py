#!/usr/bin/env python3
"""
psg1loup.py - Patch optionnel : le PSG1 à côté de la porte de la grotte, juste avant Sniper Wolf.

Dans le jeu d'origine, Sniper Wolf blesse Meryl dans le passage souterrain (s10a) et repousse
Snake tant qu'il n'a pas de fusil : il faut retourner chercher le PSG1 à l'armurerie (s04a),
puis revenir (en ressortant du passage, la progression avance : au retour, Meryl n'est plus là,
cinématique, puis combat). Avec ce patch, le PSG1 attend dans la grotte (s09a, celle du
chien-loup), à côté de la porte du passage et de la ration, dès que Meryl a été touchée.

Une boîte de munitions PSG1 de la grotte (objet « seebe », en 1000, 0, -11500, qui n'apparaît
d'origine que si l'on a déjà le PSG1) est retouchée dans le script GCL, sans changer de taille :
- condition `GM_Weapons[PSG1] >= 0` (`11 80 00 34 02 00 31 0E`) -> progression `>= 0x91`
  (`11 00 00 0A 02 91 31 0E` : après la cinématique du tir sur Meryl, comme pour l'armurerie) ;
- position `-p 1000 0 -11500` -> `7000 0 -8500` (près de la porte du passage, 9000 0 -10625,
  et de la ration en 6500 0 -7500) ;
- `-b b2` (munitions) -> `-b b0` (l'arme) ; message « PSG1/BULLET * 5 » -> « PSG1 ».
Une fois ramassée, la boîte ne revient plus (drapeau d'origine de l'objet).

  python psg1loup.py image.bin [image2.bin ...]     patch en place (STAGE.DIR)
"""

import sys

import gcx, psxiso
from cdsector import write_file_inplace

STAGE = "s09a"
# condition + début de l'objet « seebe », tels quels dans les versions FR et UK
BOX = bytes.fromhex("300b118000340200310e3100" "4000" "5d600059" "9906" "07" "068767" "06eebe"
                    "50700a" "0103e8" "010000" "01d314" "5062030202" "5069030209" "506e04010005"
                    "506d130710") + b"PSG1/BULLET * 5" + bytes(1)
NEW_COND = bytes.fromhex("1100000a0291310e")      # progression (var 0x0a) >= 0x91
NEW_POS = bytes.fromhex("011b58" "010000" "01decc")  # 7000, 0, -8500


def patch_stage(st):
    """STAGE.DIR -> (STAGE.DIR patché, nombre de boîtes retouchées)."""
    out = bytearray(st)
    a, e = next((a, e) for n, a, e in gcx.stage_table(st) if n == STAGE)
    i = st.find(BOX, a, e)
    if i == -1:
        raise SystemExit(f"{STAGE} : boîte de munitions PSG1 introuvable (déjà patchée ?)")
    assert st.find(BOX, i + 1, e) == -1
    out[i + 2:i + 10] = NEW_COND
    p = i + BOX.index(bytes.fromhex("50700a")) + 3
    out[p:p + 9] = NEW_POS
    b = i + BOX.index(bytes.fromhex("5062030202"))
    out[b + 4] = 0x00                                    # -b b2 -> -b b0
    m = i + len(BOX) - 16
    out[m:m + 5] = b"PSG1" + bytes(1)
    return bytes(out), 1


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
        patch_image(p)
        print(p, ": PSG1 près de la porte de la grotte (après le tir sur Meryl)")


if __name__ == "__main__":
    main()
