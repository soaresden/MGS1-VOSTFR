#!/usr/bin/env python3
"""
l2r2.py - Patch optionnel : en vue subjective, L2/R2 penchent Snake (comme dans MGS2).

Dans le jeu d'origine, Triangle maintenu + L1/R1 fait pencher Snake à gauche/droite pour
regarder derrière un coin ; L2/R2 ne font rien dans cette vue, et on ne peut plus tourner
la tête pendant qu'on est penché. Avec ce patch :
- L2 penche à gauche, R2 à droite (L1/R1 marchent toujours), même dos au mur ;
- penché, les flèches tournent toujours la vue ;
- L2 + R2 ensemble (ou un bouton de chaque côté) : Snake se hisse sur la pointe des pieds,
  la vue monte de 20 cm (pour regarder par-dessus un obstacle).

Modifie seulement l'exécutable PAL France (MGS1.EXE = MGS2.EXE), en place : masques de
boutons de la fonction du penché (sna_80051BA4 de la décompilation, 0x8005726c en PAL), plus
un peu de code dans la toute fin du menu de débogage jamais appelé (0x80045bb8-0x80045c08,
après le code de psg1.py). Octets d'origine vérifiés avant d'écrire.
Bits des boutons : L2 0x1, R2 0x2, L1 0x4, R1 0x8.

  python l2r2.py image.bin [image2.bin ...]     patch en place (images VOSTFR ou FR d'origine)
"""

import hashlib, sys

import mips, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
CAVE, CAVE_END = 0x80045BB8, 0x80045C08
CAVE_SHA1 = "a0446d2832828d95792e242f13cdd7b1005de54f"

SYM = dict(
    TIPTOE=200,              # hauteur gagnée sur la pointe des pieds (mm)
    LEAN_RET=0x80057454,     # sna_80051BA4 : sortie (v0 = valeur rendue)
    LEAN_SIDE=0x800573B4,    # sna_80051BA4 : choix du côté (v1 = field_A56)
    WATCH_PITCH=0x8005746C,  # sna_80051DA0 : regarder en haut / en bas
    WATCH_TURN=0x800576A0,   # sna_80051FD0 : tourner à gauche / à droite
    FP_RETURN=0x80057984,    # vue subjective (sna_fn_80052120) : sortie
)

# s1 = travail de Snake dans sna_80051BA4, s0 dans la vue subjective ;
# +0x9ac manette, +0xa5c field_A60 (position de la caméra : x, y, z).
CAVE_SRC = r"""
# ---- penché : un bouton de chaque côté = pointe des pieds --------------------
cave_tip:                       # v1 = field_A56 (chargé dans le délai)
    lw t0, 0x9ac(s1)
    lh t2, 0xa5e(s1)            # caméra : hauteur
    lhu t0, 0(t0)               # boutons tenus
    addiu t2, t2, TIPTOE
    andi t1, t0, 5              # L1 ou L2
    beqz t1, tip_no
    andi t1, t0, 0xa            # R1 ou R2
    beqz t1, tip_no
    nop
    sh t2, 0xa5e(s1)
    j LEAN_RET
    li v0, 1
tip_no:
    j LEAN_SIDE
    nop

# ---- vue subjective : penché, la vue tourne quand même ------------------------
cave_turn:
    jal WATCH_PITCH
    move a0, s0
    jal WATCH_TURN
    move a0, s0
    j FP_RETURN
    nop
"""

# (adresse, octets d'origine, source) : andi L1|R1 -> L1|R1|L2|R2, R1 -> R1|R2, L1 -> L1|L2
HOOKS = [
    (0x80057294, "0c006330", "andi v1, v1, 0xf"),     # status & (R1|L1)
    (0x8005729C, "08008230", "andi v0, a0, 0xa"),     # press & R1
    (0x800572AC, "04008230", "andi v0, a0, 5"),       # press & L1
    (0x800572BC, "0800a230", "andi v0, a1, 0xa"),     # release & R1
    (0x800572CC, "0400a230", "andi v0, a1, 5"),       # release & L1
    (0x800573AC, "520a239600000000", "j cave_tip\nlhu v1, 0xa52(s1)"),  # choix du côté
    (0x800578B0, "3400401400000000", "bnez v0, cave_turn\nnop"),       # vue subjective
]


def rd(exe, addr, n):
    o = 0x800 + addr - LOAD
    return exe[o:o + n]


def patch(exe):
    """EXE PAL France -> EXE patché (None si déjà patché)."""
    addr, orig, _ = HOOKS[-1]
    if rd(exe, addr, 4) != bytes.fromhex(orig)[:4]:
        return None
    if hashlib.sha1(rd(exe, CAVE, CAVE_END - CAVE)).hexdigest() != CAVE_SHA1:
        raise SystemExit("EXE inattendu (pas la version PAL France ?) : fin du menu de débogage")
    code, sym = mips.assemble(CAVE_SRC, CAVE, SYM)
    if CAVE + len(code) > CAVE_END:
        raise SystemExit(f"code L2/R2 trop gros ({len(code)} octets)")
    out = bytearray(exe)
    o = 0x800 + CAVE - LOAD
    out[o:o + len(code)] = code
    for addr, orig, src in HOOKS:
        new, _ = mips.assemble(src, addr, sym)
        o = 0x800 + addr - LOAD
        if bytes(out[o:o + len(new)]) != bytes.fromhex(orig):
            raise SystemExit(f"EXE inattendu à {addr:08x} (pas la version PAL France ?)")
        out[o:o + len(new)] = new
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
        print(f"{p} : {name} {'patché (L2/R2 : penché et pointe des pieds)' if done else 'déjà patché'}")


if __name__ == "__main__":
    main()
