#!/usr/bin/env python3
"""
psg1.py - Patch optionnel : PSG1 (et PSG1-T du patch M9) utilisable debout ou accroupi.

Dans le jeu d'origine, sortir le PSG1 fait toujours coucher Snake. Avec ce patch, il
garde sa posture : debout, il épaule le fusil (animation de visée du FAMAS) et la lunette
est à hauteur des yeux ; accroupi, la lunette est à hauteur d'homme accroupi ; couché,
rien ne change. Pour viser couché, se coucher avant de sortir le PSG1 (ou le ranger avec R1,
se coucher, le ressortir). Debout ou accroupi, la visée monte et descend plus loin (±45°,
comme le Stinger) et la lunette ne tremble pas (le tremblement du jeu est une animation
couchée). Dans la lunette, X fait passer de debout à accroupi et inversement.
Le jeu remet aussi Snake à plat ventre après certaines scènes (fin d'une scène scriptée,
reprise après un appel...) quand le PSG1 est en main : ce retour forcé est supprimé.

Modifie seulement l'exécutable (MGS1.EXE = MGS2.EXE ; PAL France ou PAL Europe anglaise,
adresses traduites par pal.py), en place. Le code ajouté va
dans la fin du menu de débogage jamais appelé (0x80045a08-0x80045bb8, à côté du code des
patchs M9 et Carré ; la suite est à l2r2.py) ; les octets d'origine sont vérifiés avant d'écrire. Avec --m9, appliquer m9.py
d'abord (il vérifie tout le menu de débogage).

  python psg1.py image.bin [image2.bin ...]     patch en place (images VOSTFR, FR ou UK d'origine)
"""

import struct, sys

import mips, pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
CAVE, CAVE_END = 0x80045A08, 0x80045BB8   # suite : l2r2.py
CAVE_SHA1 = "134f4693642f6e9da5c80e25ebb8b5bf54ddd1f8"

SYM = dict(
    PSG1_PACK=0x800A04B4,    # weapon_actions[WP_Rifle] (ACTPACK : still, move, trans, damage, attack...)
    FAMAS_MOVE=0x800A02A8,   # FamasMove (le PSG1 n'a pas de table de déplacement)
    CLEAR_FLAG=0x8004F738,   # GM_ClearPlayerStatusFlag
    SET_FLAG=0x8004F718,     # GM_SetPlayerStatusFlag
    SetAction=0x8004F690,    # SetAction_8004E22C(work, action, 4)
    GM_SeSet=0x800335FC,
    SE_STANCE=8,             # SE_CHANGE_STANCE
    SET_FROM=0x80058084,     # sna_anim_psg1 : suite après le choix de l'état de départ
    CAM_SKIP=0x80058224,     # sna_anim_psg1, visée en cours (état >= 4) : après le calcul de la caméra (field_A60)
    CAM_GO=0x800581F0,
    DG_SetPos=0x8001C078,
    TEB_GO=0x80059420, TEB_SKIP=0x80059488,
    AIM_STAND=5,             # set_up_famas : épauler debout
    AIM_SQUAT=15,            # squat_socom : accroupi, arme en main
)

# Travail de Snake (s0) : +0x9b0 actpack, +0xa22 posture (0 debout, 1 accroupi, 2 couché),
# +0xa36 état de la visée, +0xa1c field_A20, +0x9d2 limite de visée verticale.
CAVE_SRC = r"""
# ---- sna_anim_psg1, image 0 : garder la posture, actpack selon la posture ----
cave_t0:                        # v0 = 1, v1 = posture
    sh v0, 0xa1c(s0)
    li v0, 3
    sh v0, 0xa36(s0)            # état 3 tout de suite (au lieu de s'accroupir puis se coucher)
    la t0, PSG1_PACK
    li v0, 2
    beq v1, v0, t0_set
    nop
    la t0, pack_stand
    beqz v1, t0_set
    nop
    la t0, pack_squat
t0_set:
    j SET_FROM
    sw t0, 0x9b0(s0)

# ---- état 3 : accroupi, garder le drapeau PLAYER_SQUAT (0x20) ---------------
cave_clr:                       # a0 = 0x8020
    lh v0, 0xa22(s0)
    li v1, 1
    bne v0, v1, clr_go
    nop
    li a0, 0x8000
clr_go:
    j CLEAR_FLAG
    nop

# ---- visée en cours : caméra de la lunette sur la main seulement couché -------------
cave_cam:                       # v0 = posture
    li v1, 2
    beq v0, v1, cam_ground
    nop
    j CAM_SKIP                  # debout / accroupi : caméra = tête (comme la vue Triangle)
    lh v0, 0xa60(s0)            # rangé tel quel par le délai de CAM_SKIP
cam_ground:
    lw a0, 0x9c(s0)
    jal DG_SetPos
    addiu a0, a0, 0x1b8
    j CAM_GO
    nop

# ---- visée verticale : ±0x78 couché, ±0x200 debout ou accroupi -------------
cave_lim:
    lh v0, 0xa22(s0)
    li v1, 2
    beq v0, v1, lim_go
    li v0, 0x78
    li v0, 0x200
lim_go:
    jr ra
    sh v0, 0x9d2(s0)

# ---- visée (chaque image) : X = debout <-> accroupi --------------------------
cave_x:
    lw t0, 0x9ac(s0)            # manette
    addiu sp, sp, -24
    lhu t0, 2(t0)               # press
    sw ra, 16(sp)
    andi t0, t0, 0x40           # X
    beqz t0, x_done
    lh t1, 0xa22(s0)
    li t2, 2
    beq t1, t2, x_done          # couché : rien
    xori t1, t1, 1
    sh t1, 0xa22(s0)
    la t3, pack_stand
    beqz t1, x_pack
    li a0, 0x20                 # PLAYER_SQUAT
    la t3, pack_squat
x_pack:
    sw t3, 0x9b0(s0)
    la t9, SET_FLAG             # accroupi : PLAYER_SQUAT posé
    bnez t1, x_flag
    nop
    la t9, CLEAR_FLAG           # debout : effacé
x_flag:
    jalr t9
    nop
    lw t0, 0x9b0(s0)
    nop
    lw t0, 0x10(t0)             # attack
    li a2, 4
    lbu a1, 0(t0)               # aim
    jal SetAction
    move a0, s0
    addiu a0, s0, 0x20          # control.mov
    jal GM_SeSet
    li a1, SE_STANCE
x_done:
    lw ra, 16(sp)
    lbu v0, 0xa30(s0)           # instruction remplacée
    addiu sp, sp, 24
    jr ra
    nop

# ---- tremblement (animation 122, couchée) seulement couché ------------------
cave_teb:
    lh v0, 0xa22(s0)
    li v1, 2
    bne v0, v1, TEB_SKIP
    nop
    j TEB_GO
    lui v0, 0x800b

.align 2
pack_stand:
    .word STILL, FAMAS_MOVE, TRANS, DAMAGE, att_stand, SPECIAL, SPECIAL2
pack_squat:
    .word STILL, FAMAS_MOVE, TRANS, DAMAGE, att_squat, SPECIAL, SPECIAL2
att_stand:
    .byte AIM_STAND, ATT1, ATT2, ATT3, ATT4, ATT5, ATT6, ATT7, ATT8
.align 2
att_squat:
    .byte AIM_SQUAT, ATT1, ATT2, ATT3, ATT4, ATT5, ATT6, ATT7, ATT8
.align 2
"""

HOOKS = [
    (0x80058014, "0100022418006210", "j cave_t0\nli v0, 1"),          # sna_anim_psg1 : départ
    (0x800581A8, "ce3d010c", "jal cave_clr"),                         # état 3 : drapeaux
    (0x800581E4, "9c00048e1e70000c", "j cave_cam\nlh v0, 0xa22(s0)"),  # visée : caméra
    (0x800592A4, "78000224d20902a6", "jal cave_lim\nnop"),            # visée : limites
    (0x80059418, "340a00a60b80023c", "j cave_teb\nsh zero, 0xa34(s0)"),  # visée : tremblement
    (0x80059108, "300a029200000000", "jal cave_x\nnop"),             # visée : X
    # « si l'arme est le PSG1, posture = couché » après une scène : supprimé
    (0x80055F50, "220a02a6", "nop"),
    (0x800562B0, "220a42a6", "nop"),
    (0x80056B8C, "220a02a6", "nop"),
]


def rd(exe, addr, n):
    o = 0x800 + addr - LOAD
    return exe[o:o + n]


def build_cave(exe, v="FR"):
    sym = pal.syms(v, SYM)
    pack = struct.unpack("<7I", rd(exe, sym["PSG1_PACK"], 28))
    if pack[1] != 0:
        raise SystemExit("EXE inattendu : table d'actions du PSG1")
    sym.update(STILL=pack[0], TRANS=pack[2], DAMAGE=pack[3], SPECIAL=pack[5], SPECIAL2=pack[6])
    att = rd(exe, pack[4], 9)
    if att[0] != 44:            # visée couchée du PSG1
        raise SystemExit("EXE inattendu : animations du PSG1")
    sym.update({f"ATT{i}": att[i] for i in range(1, 9)})
    code, sym = mips.assemble(CAVE_SRC, pal.addr(v, CAVE), sym)
    if CAVE + len(code) > CAVE_END:
        raise SystemExit(f"code PSG1 trop gros ({len(code)} octets)")
    return code, sym


def patch(exe):
    """EXE PAL France ou Europe -> EXE patché (None si déjà patché)."""
    v = pal.version(exe)
    addr, orig, _ = HOOKS[0]
    if not pal.same(v, rd(exe, pal.addr(v, addr), 4), orig[:8]):
        return None
    if not pal.cave_ok(v, exe, CAVE, CAVE_END, CAVE_SHA1):
        raise SystemExit("EXE inattendu : fin du menu de débogage déjà utilisée ?")
    code, sym = build_cave(exe, v)
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
        print(f"{p} : {name} {'patché (PSG1 debout / accroupi)' if done else 'déjà patché'}")


if __name__ == "__main__":
    main()
