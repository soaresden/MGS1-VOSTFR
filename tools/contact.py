#!/usr/bin/env python3
"""
contact.py - Patch optionnel : toucher un garde ne donne plus l'alerte, il faut qu'il voie Snake.

Dans le jeu d'origine, il suffit de frôler un soldat (même de dos, même accroupi) pour qu'il
découvre Snake : alerte immédiate. Chaque soldat a une cible de contact (TARGET_TOUCH,
field_94C) ; à chaque image, sa fonction de capteurs (décompilation : s00a_command_800C98A4,
une copie dans l'overlay de chaque stage) fait :

    if (contact->damaged & 0x80) {                      // Snake le touche
        contact->damaged &= ~0x80;
        if ((GM_PlayerStatus & (MOVE | CB_BOX)) == CB_BOX) return;   // carton immobile : rien
        work->sensors |= 4 | 8;                         // « attaqué » : il se retourne, alerte
    }

Le bit 4 est celui d'un coup reçu (coup de poing, prise) : le soldat passe en mode « attaqué »
(think2 = 4), donc découverte et alerte. Le patch remplace `ori v0, v0, 0xc` par `ori v0, v0, 0` :
le contact est toujours lu et effacé, mais n'allume plus rien. Le soldat reste poussé par Snake
(EnemyPushMove, cible PUSH : il glisse et peut pivoter s'il est debout ou en marche) ; s'il se
retrouve face à Snake, c'est sa vue qui donne l'alerte, comme d'habitude. Les coups (bit 4 posé
par la cible principale, damaged & 6), les bruits et la vue ne changent pas.

Motif cherché dans l'overlay de chaque stage de STAGE.DIR (le champ des capteurs est en 0xBA1,
0xB9E ou 0xBA2 selon le stage) :

    lhu  v0, 0x952(a0)   ; andi v0, v0, 0x80 ; ...
    andi v0, v0, 0x1010  ; beq v0, v1, fin ; nop
    lbu  v0, CAPT(a0)    ; nop ; ori v0, v0, 0xc ; sb v0, CAPT(a0)

US : 36 sites dans 34 stages (VR comprises) ; FR/UK : 34 dans 32 (pas de d00aa ni s00aa). Mêmes octets sur les deux disques.

  python contact.py image.bin [image2.bin ...]     patch en place (STAGE.DIR)
"""

import struct
import sys

import psxiso
from cdsector import write_file_inplace

ORI_C = 0x3442000C      # ori v0, v0, 0xc
ORI_0 = 0x34420000      # ori v0, v0, 0


def overlays(stage):
    """(nom, position, taille) de l'overlay de code de chaque stage."""
    n = struct.unpack_from("<I", stage, 0)[0]
    for i in range(n // 12):
        name = stage[4 + 12 * i:12 + 12 * i].rstrip(bytes(1)).decode("latin1")
        sec = struct.unpack_from("<I", stage, 12 + 12 * i)[0]
        _, mode, ext, size = struct.unpack_from("<HBBi", stage, sec * 2048 + 4)
        if chr(mode) == "s" and chr(ext) == "b" and size > 0:
            yield name, (sec + 1) * 2048, size


def sites(stage):
    """[(stage, position dans STAGE.DIR)] des `ori v0, v0, 0xc` du contact (motif complet vérifié)."""
    out = []
    for name, pos, size in overlays(stage):
        w = struct.unpack_from(f"<{size // 4}I", stage, pos)
        for i in range(12, len(w) - 1):
            if w[i] != ORI_C:
                continue
            lb, sb = w[i - 2], w[i + 1]
            capt = lb & 0xFFFF
            if lb != 0x90820000 | capt or sb != 0xA0820000 | capt or w[i - 1]:   # lbu / sb v0, CAPT(a0)
                continue
            ctx = w[i - 16:i - 2]
            if (0x30421010 in ctx                                              # andi v0, v0, 0x1010
                    and any(x & 0xFFE0FFFF == 0x94800952 for x in ctx)          # lhu r, 0x952(a0)
                    and any(x >> 26 == 0x0C and x & 0xFFFF == 0x80 for x in ctx)   # andi r, r, 0x80
                    and any(x & 0xFFE0FFFF == 0x24001000 for x in ctx)):        # li r, 0x1000
                out.append((name, pos + 4 * i))
    return out


def patch_stage(stage):
    """STAGE.DIR -> (STAGE.DIR patché, nombre de soldats retouchés, stages touchés)."""
    out = bytearray(stage)
    found = sites(stage)
    for _, p in found:
        struct.pack_into("<I", out, p, ORI_0)
    return bytes(out), len(found), sorted({n for n, _ in found})


def patch_image(path):
    d = psxiso.Disc(path)
    lba, size = d.files()["MGS/STAGE.DIR"]
    new, n, names = patch_stage(d.read(lba, size))
    d.f.close()
    write_file_inplace(path, lba, new)
    return n, names


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        n, names = patch_image(p)
        print(p, ":", n, "contacts sans alerte,", len(names), "stages")


if __name__ == "__main__":
    main()
