#!/usr/bin/env python3
"""
bandana.py - Patch optionnel : le bandana (munitions infinies) se voit, avec de très longs pans
qui flottent derrière Snake, comme dans MGS2.

Dans le jeu d'origine, équiper le BANDANA change seulement la texture du visage (sna_face ->
sna_mf1..3) : le bandeau bleu-gris que Snake porte déjà devient presque noir, ce qui ne se voit
pas. Le disque contient pourtant un modèle « bandana » (KMD 0xdb4d, 316 octets, résident :
stages init / init_tux) jamais affiché par le code : une bande plate de 5 quadrilatères, dans
le repère de la tête (os 6), qui pend derrière la tête (36 cm), texturée avec la bande du
bandeau de sna_face. Avec ce patch :
- l'acteur du bandana (equip/bandana.c) crée en plus ce modèle, accroché à la tête comme le
  masque à gaz (gasmask.c), visible / caché avec Snake (vue subjective) ;
- à chaque image, les 12 sommets de la bande sont recalculés : 5 segments de LONG mm
  (1,3 m en tout), qui pendent au repos, se soulèvent vers l'arrière quand Snake court
  (vitesse = déplacement de Snake d'une image à l'autre, lissée) et ondulent (vague qui
  descend le long du pan, battement de côté, la bande vrille un peu).
La texture et les munitions infinies d'origine sont gardées.

Modifie seulement l'exécutable (MGS1.EXE = MGS2.EXE ; PAL France ou PAL Europe anglaise,
adresses traduites par pal.py) : saut au début de NewBandana (0x80062cec) vers le code
ajouté, écrit dans une fonction que rien n'appelle (sub_8007F3F8 de la décompilation,
0x80080b28-0x80081244, 1820 octets ; vérifié : aucun appel ni pointeur dans l'EXE ni dans les
92 overlays des 4 disques). Octets d'origine vérifiés avant d'écrire. Indépendant des autres
options (aucune autre ne touche ces adresses).

  python bandana.py image.bin [image2.bin ...]     patch en place (images VOSTFR, FR ou UK d'origine)
"""

import sys

import mips, pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
CAVE, CAVE_END = 0x80080B28, 0x80081244
CAVE_SHA1 = "a1b465a6b058391d272b32bc301e6fedcd21ce77"

LONG = 260   # longueur d'un des 5 segments du pan (mm)

SYM = dict(
    GV_NewActor=0x800151C8, GV_SetNamedActor=0x80015234,
    GM_InitObjectNoRots=0x800357E4, GM_ConfigObjectRoot=0x80035A98,
    GM_ConfigObjectLight=0x80035A80, GM_FreeObject=0x80035A30,
    BD_SWAP=0x80062BB4,      # bandana.c : échange des textures sna_face <-> sna_mf
    BD_ACT=0x80062C44,       # bandana.c : Act d'origine (munitions infinies)
    BD_DIE=0x80062CC8,       # bandana.c : Die d'origine (textures rendues)
    BD_NAME=0x80012A2C,      # "bandana.c"
    GROUP=0x800ACF50, CURMAP=0x800ACF98,   # comme l'Act de gasmask.c
    KMD=0xDB4D,              # GV_StrCode("bandana")
    WORK_SIZE=0x54, BOX=2000,
    X0=0, Y0=60, Z0=-88,     # nœud du bandana, derrière la tête (repère de l'os 6, z vers l'avant)
    L=LONG, WX=22, W=10,     # longueur d'un segment, demi-largeur de la bande (de côté, dans le plan)
    R0=260, RS=45,           # angle au repos du segment j (4096 = tour) : R0 - RS*j depuis la verticale
    RUN=950,                 # angle en pleine course (~83° : presque à l'horizontale)
    A0=50, A1=180,           # amplitude de la vague : A0 + A1 * vitesse
    LAG=500, OMEGA=120,      # retard de phase par segment, vitesse de la vague (+ vitesse de Snake)
    AX0=12, AX1=50,          # battement de côté par segment (mm)
)

# Travail (0x54 octets, mis à zéro par GV_NewActor) : +0x20 parent, +0x24 control (comme
# l'original, dont le Die lit +0x20) ; +0x28 OBJECT_NO_ROTS (0x24) ; +0x4c / +0x4e position
# x / z précédente ; +0x50 vitesse lissée (0..256) ; +0x52 phase de la vague.
# DG_OBJS : +0x24 def, +0x28 flag (0x80 invisible), +0x2c group_id, +0x88 objs[0].model ;
# DG_DEF : boîte +0x08..+0x1c, modèle 0 en +0x20 (boîte +0x28..+0x3c, sommets +0x58).
CAVE_SRC = r"""
# ---- NewBandana(control, parent, num_parent) ---------------------------------
bd_new:
    addiu sp, sp, -32
    sw ra, 28(sp)
    sw s0, 16(sp)
    sw s1, 20(sp)
    sw s2, 24(sp)
    move s2, a0
    move s1, a1
    li a0, 7
    jal GV_NewActor
    li a1, WORK_SIZE
    beqz v0, new_ret
    move s0, v0
    move a0, s0
    la a1, bd_act
    la a2, bd_die
    la a3, BD_NAME
    jal GV_SetNamedActor
    nop
    sw s1, 0x20(s0)
    sw s2, 0x24(s0)
    lh t0, 0(s2)
    lh t1, 4(s2)
    sh t0, 0x4c(s0)
    sh t1, 0x4e(s0)
    jal BD_SWAP
    move a0, s1
    addiu a0, s0, 0x28
    li a1, KMD
    li a2, 0x6d
    jal GM_InitObjectNoRots
    move a3, zero
    lw t0, 0x28(s0)
    addiu a0, s0, 0x28
    beqz t0, new_ok
    move a1, s1
    jal GM_ConfigObjectRoot
    li a2, 6
    lw a1, 8(s1)
    jal GM_ConfigObjectLight
    addiu a0, s0, 0x28
    lw t0, 0x28(s0)
    li t1, -BOX
    lw t0, 0x24(t0)
    li t2, BOX
    sw t1, 0x08(t0)
    sw t1, 0x0c(t0)
    sw t1, 0x10(t0)
    sw t2, 0x14(t0)
    sw t2, 0x18(t0)
    sw t2, 0x1c(t0)
    sw t1, 0x28(t0)
    sw t1, 0x2c(t0)
    sw t1, 0x30(t0)
    sw t2, 0x34(t0)
    sw t2, 0x38(t0)
    sw t2, 0x3c(t0)
new_ok:
    move v0, s0
new_ret:
    lw ra, 28(sp)
    lw s0, 16(sp)
    lw s1, 20(sp)
    lw s2, 24(sp)
    jr ra
    addiu sp, sp, 32

# ---- Die : modèle libéré, puis Die d'origine ---------------------------------
bd_die:
    addiu sp, sp, -24
    sw ra, 16(sp)
    sw s0, 20(sp)
    move s0, a0
    jal GM_FreeObject
    addiu a0, a0, 0x28
    move a0, s0
    lw ra, 16(sp)
    lw s0, 20(sp)
    j BD_DIE
    addiu sp, sp, 24

# ---- Act ----------------------------------------------------------------------
bd_act:
    addiu sp, sp, -56
    sw ra, 48(sp)
    sw s0, 16(sp)
    sw s1, 20(sp)
    sw s2, 24(sp)
    sw s3, 28(sp)
    sw s4, 32(sp)
    sw s5, 36(sp)
    sw s6, 40(sp)
    sw s7, 44(sp)
    jal BD_ACT
    move s0, a0
    lw a0, 0x28(s0)
    lw v0, 0x24(s0)
    beqz a0, act_ret
    lui t0, %hi(GROUP)
    lw v1, 0x2c(v0)
    lw t0, %lo(GROUP)(t0)
    lw v1, 0(v1)
    sh t0, 0x2c(a0)
    lui at, %hi(CURMAP)
    sw v1, %lo(CURMAP)(at)
    # visible / caché comme Snake
    lw t1, 0x20(s0)
    lw t2, 0x28(a0)
    lw t1, 0(t1)
    li t3, -0x81
    and t2, t2, t3
    lw t1, 0x28(t1)
    nop
    andi t1, t1, 0x80
    or t2, t2, t1
    sw t2, 0x28(a0)
    # vitesse de Snake (|dx| + |dz|), lissée
    lh s6, 0x50(s0)
    lw v0, 0x24(s0)
    lh t2, 0x4c(s0)
    lh t0, 0(v0)
    lh t1, 4(v0)
    lh t3, 0x4e(s0)
    sh t0, 0x4c(s0)
    sh t1, 0x4e(s0)
    subu t2, t0, t2
    bgez t2, sp1
    subu t3, t1, t3
    neg t2, t2
sp1:
    bgez t3, sp2
    nop
    neg t3, t3
sp2:
    addu t2, t2, t3
    sll t2, t2, 2
    slti at, t2, 257
    bnez at, sp3
    nop
    li t2, 256
sp3:
    subu t2, t2, s6
    sra t2, t2, 3
    addu s6, s6, t2
    sh s6, 0x50(s0)
    # phase de la vague
    lhu s7, 0x52(s0)
    addiu t0, s6, OMEGA
    addu s7, s7, t0
    andi s7, s7, 0xfff
    sh s7, 0x52(s0)
    # sommets du modèle
    lw t0, 0x88(a0)
    li s3, X0
    lw s1, 0x38(t0)
    li s4, Y0
    li s5, Z0
    move s2, zero
bd_loop:
    li t0, LAG
    mult s2, t0
    mflo t0
    subu a0, s7, t0
    jal bd_sin
    sw a0, 12(sp)
    sw v0, 0(sp)
    lw a0, 12(sp)
    jal bd_cos
    nop
    sw v0, 4(sp)
    # angle du segment : repos -> course, plus la vague
    li t0, RS
    mult s2, t0
    mflo t0
    li t1, R0
    subu t1, t1, t0
    li t2, RUN
    subu t2, t2, t1
    mult t2, s6
    mflo t2
    sra t2, t2, 8
    addu t1, t1, t2
    li t3, A1
    mult t3, s6
    mflo t3
    sra t3, t3, 8
    addiu t3, t3, A0
    lw t4, 0(sp)
    nop
    mult t3, t4
    mflo t3
    sra t3, t3, 12
    addu a0, t1, t3
    jal bd_sin
    sw a0, 12(sp)
    sw v0, 8(sp)
    lw a0, 12(sp)
    jal bd_cos
    nop
    # demi-largeur (WX (1 + sin phase / 2), -W sin a, W cos a) : surtout de côté (bien visible
    # d'au-dessus, la caméra habituelle), la bande vrille un peu
    lw t0, 0(sp)
    lw t1, 8(sp)
    li t3, WX
    mult t0, t3
    mflo t4
    sra t4, t4, 13
    addiu t4, t4, WX
    li t3, W
    mult t1, t3
    mflo t5
    sra t5, t5, 12
    neg t5, t5
    mult v0, t3
    mflo t6
    sra t6, t6, 12
    la t7, bd_tab
    addu t7, t7, s2
    lbu t8, 0(t7)
    lbu t9, 6(t7)
    sll t8, t8, 3
    sll t9, t9, 3
    addu t8, s1, t8
    addu t9, s1, t9
    addu at, s3, t4
    sh at, 0(t8)
    subu at, s3, t4
    sh at, 0(t9)
    addu at, s4, t5
    sh at, 2(t8)
    subu at, s4, t5
    sh at, 2(t9)
    addu at, s5, t6
    sh at, 4(t8)
    subu at, s5, t6
    sh at, 4(t9)
    # nœud suivant : (battement, -L cos a, -L sin a)
    li t3, L
    mult v0, t3
    mflo t4
    sra t4, t4, 12
    subu s4, s4, t4
    mult t1, t3
    mflo t4
    sra t4, t4, 12
    subu s5, s5, t4
    li t3, AX1
    mult t3, s6
    mflo t3
    sra t3, t3, 8
    addiu t3, t3, AX0
    lw t4, 4(sp)
    nop
    mult t3, t4
    mflo t4
    sra t4, t4, 12
    addu s3, s3, t4
    addiu s2, s2, 1
    slti t0, s2, 6
    bnez t0, bd_loop
    nop
act_ret:
    lw ra, 48(sp)
    lw s0, 16(sp)
    lw s1, 20(sp)
    lw s2, 24(sp)
    lw s3, 28(sp)
    lw s4, 32(sp)
    lw s5, 36(sp)
    lw s6, 40(sp)
    lw s7, 44(sp)
    jr ra
    addiu sp, sp, 56

# ---- sinus approché (parabole) : a0 en 4096e de tour -> v0 en 4096e ------------
bd_cos:
    addiu a0, a0, 1024
bd_sin:
    andi a0, a0, 0xfff
    slti v0, a0, 2048
    bnez v0, sn1
    move v1, a0
    addiu a0, a0, -4096
    move v1, a0
sn1:
    bgez v1, sn2
    li t9, 2048
    neg v1, v1
sn2:
    subu t9, t9, v1
    mult a0, t9
    mflo v0
    jr ra
    sra v0, v0, 8

# sommets du modèle d'origine, du nœud vers la pointe : côté A puis côté B
bd_tab:
    .byte 10, 8, 6, 4, 0, 3
    .byte 11, 9, 7, 5, 1, 2
"""

HOOKS = [
    (0x80062CEC, "e0ffbd271400b1af", "j bd_new\nnop"),   # NewBandana
]


def rd(exe, addr, n):
    o = 0x800 + addr - LOAD
    return exe[o:o + n]


def patch(exe):
    """EXE PAL France ou Europe -> EXE patché (None si déjà patché)."""
    v = pal.version(exe)
    addr, orig, _ = HOOKS[0]
    if not pal.same(v, rd(exe, pal.addr(v, addr), 8), orig):
        return None
    if not pal.cave_ok(v, exe, CAVE, CAVE_END, CAVE_SHA1):
        raise SystemExit("EXE inattendu : la fonction inutilisée 0x80080b28 a déjà été modifiée ?")
    code, sym = mips.assemble(CAVE_SRC, pal.addr(v, CAVE), pal.syms(v, SYM))
    if CAVE + len(code) > CAVE_END:
        raise SystemExit(f"code du bandana trop gros ({len(code)} octets)")
    out = bytearray(exe)
    o = 0x800 + pal.addr(v, CAVE) - LOAD
    out[o:o + len(code)] = code
    for addr, orig, src in HOOKS:
        a = pal.addr(v, addr)
        new, _ = mips.assemble(src, a, sym)
        o = 0x800 + a - LOAD
        if not pal.same(v, bytes(out[o:o + len(new)]), orig):
            raise SystemExit(f"EXE inattendu à {a:08x} ({v})")
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
        print(f"{p} : {name} {'patché (bandana visible, pans très longs)' if done else 'déjà patché'}")


if __name__ == "__main__":
    main()
