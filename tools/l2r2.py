#!/usr/bin/env python3
"""
l2r2.py - Patch optionnel : en vue subjective, L2/R2 penchent Snake (comme dans MGS2).

Dans le jeu d'origine, Triangle maintenu + L1/R1 fait pencher Snake à gauche/droite pour
regarder derrière un coin ; L2/R2 ne font rien dans cette vue. Avec ce patch, L2 penche à
gauche et R2 à droite ; L1/R1 marchent toujours. Même chose dos au mur.

Modifie seulement l'exécutable PAL France (MGS1.EXE = MGS2.EXE), en place : 5 masques de
boutons dans la fonction du penché (sna_80051BA4 de la décompilation, 0x80057294 en PAL).
Bits des boutons : L2 0x1, R2 0x2, L1 0x4, R1 0x8. Octets d'origine vérifiés avant d'écrire.

  python l2r2.py image.bin [image2.bin ...]     patch en place (images VOSTFR ou FR d'origine)
"""

import sys

import psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000

# (adresse, mot d'origine, mot patché) : andi avec L1|R1 -> L1|R1|L2|R2, R1 -> R1|R2, L1 -> L1|L2
PATCHES = [
    (0x80057294, "0c006330", "0f006330"),   # status & (R1|L1)       -> & 0xf
    (0x8005729C, "08008230", "0a008230"),   # press & R1             -> & (R1|R2)
    (0x800572AC, "04008230", "05008230"),   # press & L1             -> & (L1|L2)
    (0x800572BC, "0800a230", "0a00a230"),   # release & R1           -> & (R1|R2)
    (0x800572CC, "0400a230", "0500a230"),   # release & L1           -> & (L1|L2)
]


def patch(exe):
    """EXE PAL France -> EXE patché (None si déjà patché)."""
    out = bytearray(exe)
    o = lambda a: 0x800 + a - LOAD
    if all(exe[o(a):o(a) + 4] == bytes.fromhex(new) for a, _, new in PATCHES):
        return None
    for a, orig, new in PATCHES:
        if exe[o(a):o(a) + 4] != bytes.fromhex(orig):
            raise SystemExit(f"EXE inattendu à {a:08x} (pas la version PAL France ?)")
        out[o(a):o(a) + 4] = bytes.fromhex(new)
    return bytes(out)


def patch_image(path):
    disc = psxiso.Disc(path)
    files = disc.files()
    name = next(p for p in files if p in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
    exe = disc.read(*files[name])
    disc.f.close()
    new = patch(exe)
    if new is not None:
        write_file_inplace(path, files[name][0], new)
    return name, new is not None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        name, done = patch_image(p)
        print(f"{p} : {name} {'patché (L2/R2 penchent la vue subjective)' if done else 'déjà patché'}")


if __name__ == "__main__":
    main()
