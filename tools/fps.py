#!/usr/bin/env python3
"""
fps.py - Patch optionnel : tirer au SOCOM / M9 en vue subjective (comme dans MGS2).

SOCOM ou M9 en main, Triangle maintenu (vue subjective) : l'arme apparaît en bas à droite de
l'écran, dans l'axe de la caméra. Carré maintenu = visée (laser du SOCOM), Carré relâché = tir.
La balle part dans la direction de la vue. Le tir reste celui du jeu (son, bruit, munitions,
fléchette du M9 avec --m9) ; le chargeur se recharge tout seul en vue subjective.

Une seule retouche dans la boucle de l'acteur SOCOM (weapon/socom.c, Act) : juste avant le choix
« Snake invisible -> arme et laser cachés » et la lecture des drapeaux de l'arme (bit 0 = viser,
bit 1 = tirer). En vue subjective, le code ajouté :
- détache l'arme de la main (DG_OBJS.root = NULL, rattachée à nouveau en sortant de la vue) et
  calcule sa matrice à partir de celle de la caméra (DG_Chanls[1].eye) ; le laser et son point
  lumineux (DG_PRIM.root, rattachés à la main d'origine) suivent la matrice de l'arme ;
- la laisse visible (le corps de Snake est caché en vue subjective) ;
- ajoute les bits « viser » (Carré tenu) et « tirer » (Carré relâché).
- rend le laser visible : vu presque de face, le trait d'origine (couleur 16,16,16, presque
  transparent) et son point rouge de 2x2 pixels ne se voyaient pas ; en vue subjective le trait
  passe en couleur LASER_RGB et le point au bout du laser en LASER_DOT x LASER_DOT pixels
  (rendus en sortant de la vue).
Code ajouté à 0x80045400-0x80045900 (menu de débogage inutilisé, voir m9.py).

  python fps.py image.bin [image2.bin ...]     patch en place (VOSTFR ou FR d'origine)
"""

import hashlib, sys

import mips, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
CAVE, CAVE_END = 0x80045400, 0x80045900
CAVE_SHA1 = "6e05336a974efc6b25d1a20da48670942551f4fc"  # octets d'origine de la zone

# Arme dans le repère de la caméra (x droite, y bas, z avant), en unités du jeu
OFFSET = (130, 170, 260)

SYM = dict(
    FIRST_PERSON=0x800B8DE2,   # GM_Camera.first_person
    PLAYER_STATUS=0x800AD038,  # GM_PlayerStatus (bit 0 = PLAYER_WATCH)
    MENU_PAD=0x800BE95C,       # MenuWork + 0x24 : manette (status +0, release +4)
    EYE=0x800B3004,            # DG_Chanls[1].eye : caméra -> monde
    GM_Magazine=0x800ACFD4, GM_MagazineMax=0x800AD014, SOCOM_AMMO=0x800B63A2,
    OX=OFFSET[0], OY=OFFSET[1], OZ=OFFSET[2],
    LASER_RGB=0x60, LASER_RGB0=0x10,   # couleur du trait : vue subjective / d'origine
    LASER_DOT=6, LASER_DOT0=2,          # taille du point rouge : vue subjective / d'origine
)


def world_src():
    """Matrice de l'arme : canon (-Y de l'arme) = avant de la caméra (colonne 2 de EYE)."""
    lines = []
    # colonnes de l'arme : X = -X caméra, Y = -Z caméra, Z = -Y caméra (rotation, dét. +1)
    for i in range(3):
        for col, src in ((0, 0), (1, 2), (2, 1)):
            lines += [f"    lh t0, {2 * (3 * i + src)}(t9)", "    nop", "    neg t0, t0",
                      f"    sh t0, {2 * (3 * i + col)}(t2)"]
    for i in range(3):
        lines += [f"    lh t0, {2 * (3 * i)}(t9)", "    li t1, OX", "    mult t0, t1", "    mflo t3",
                  f"    lh t0, {2 * (3 * i + 1)}(t9)", "    li t1, OY", "    mult t0, t1", "    mflo t4",
                  f"    lh t0, {2 * (3 * i + 2)}(t9)", "    li t1, OZ", "    mult t0, t1", "    mflo t5",
                  "    addu t3, t3, t4", "    addu t3, t3, t5", "    sra t3, t3, 12",
                  f"    lw t0, {0x14 + 4 * i}(t9)", "    nop", "    addu t3, t3, t0",
                  f"    sw t3, {0x14 + 4 * i}(t2)"]
    return "\n".join(lines)


CAVE_SRC = r"""
# remplace « lw s2, 0(v1) ; andi v0, v0, 0x80 » dans l'Act du SOCOM (s1 = acteur)
fps:
    lw s2, 0(v1)                # drapeaux de l'arme
    andi v0, v0, 0x80           # Snake invisible ?
    lui t0, %hi(FIRST_PERSON)
    lh t0, %lo(FIRST_PERSON)(t0)
    lui t1, %hi(PLAYER_STATUS)
    lw t1, %lo(PLAYER_STATUS)(t1)
    beqz t0, fps_off
    andi t1, t1, 1
    beqz t1, fps_off
    nop
    lw t2, 0x20(s1)             # DG_OBJS de l'arme
    nop
    beqz t2, fps_ret
    nop
    move v0, zero               # arme et laser visibles
    lw t3, 0x20(t2)             # objs->root (main de Snake)
    la t4, fps_root
    beqz t3, fps_world          # déjà détachée
    nop
    sw t3, 0(t4)
    sw t2, 4(t4)
    sw zero, 0x20(t2)
    lw t5, 0x58(s1)             # laser et son point : rattachés à l'arme
    lw t6, 0x10C(s1)
    beqz t5, fps_nolaser
    nop
    sw t2, 0x20(t5)
fps_nolaser:
    beqz t6, fps_world
    nop
    sw t2, 0x20(t6)
fps_world:
    la t9, EYE
WORLD
    move t8, ra
    li a0, LASER_RGB
    jal laser_look
    li a1, LASER_DOT
    move ra, t8
    lui t0, %hi(MENU_PAD)       # manette
    lw t0, %lo(MENU_PAD)(t0)
    nop
    lhu t5, 0(t0)               # touches tenues
    lhu t6, 4(t0)               # touches relâchées
    andi t7, t5, 0x80           # Carré tenu : viser
    beqz t7, fps_norel
    nop
    ori s2, s2, 1
fps_norel:
    andi t7, t6, 0x80           # Carré relâché : tirer
    beqz t7, fps_reload
    nop
    ori s2, s2, 3
fps_reload:                     # chargeur vide hors visée : rechargé tout de suite
    andi t7, t5, 0x80
    bnez t7, fps_ret
    lui t0, %hi(GM_Magazine)
    lh t1, %lo(GM_Magazine)(t0)
    lui t3, %hi(SOCOM_AMMO)
    lh t3, %lo(SOCOM_AMMO)(t3)
    bnez t1, fps_ret
    lui t4, %hi(GM_MagazineMax)
    lh t4, %lo(GM_MagazineMax)(t4)
    blez t3, fps_ret
    slt t5, t4, t3
    beqz t5, fps_setmag
    nop
    move t3, t4
fps_setmag:
    sh t3, %lo(GM_Magazine)(t0)
fps_ret:
    jr ra
    nop

fps_off:                        # hors vue subjective : arme rattachée à la main
    la t4, fps_root
    lw t3, 0(t4)
    lw t5, 4(t4)
    beqz t3, fps_ret
    lw t2, 0x20(s1)
    nop
    bne t2, t5, fps_clear       # acteur recréé entre-temps
    nop
    sw t3, 0x20(t2)
    lw t5, 0x58(s1)             # laser et son point : de nouveau à la main
    lw t6, 0x10C(s1)
    beqz t5, fps_nolaser2
    nop
    sw t3, 0x20(t5)
fps_nolaser2:
    beqz t6, fps_clear
    nop
    sw t3, 0x20(t6)
fps_clear:
    sw zero, 0(t4)
    sw zero, 4(t4)
    li a0, LASER_RGB0           # laser d'origine
    j laser_look
    li a1, LASER_DOT0

# laser_look(a0 = couleur du trait, a1 = taille du point) ; s1 = acteur SOCOM
laser_look:
    lw t0, 0x58(s1)             # trait : 10 POLY_FT4 (0x28 octets) par tampon
    li t3, 2
    beqz t0, laser_dot
    addiu t0, t0, 0x40          # packs[0], packs[1]
laser_pack:
    lw t1, 0(t0)
    li t2, 10
    beqz t1, laser_next
    nop
laser_poly:
    sb a0, 4(t1)
    sb a0, 5(t1)
    sb a0, 6(t1)
    addiu t2, t2, -1
    bnez t2, laser_poly
    addiu t1, t1, 0x28
laser_next:
    addiu t3, t3, -1
    bnez t3, laser_pack
    addiu t0, t0, 4
laser_dot:
    lw t0, 0x10C(s1)            # point : 2 TILE (0x10 octets) par tampon, le 2e au bout
    li t3, 2
    beqz t0, laser_ret
    addiu t0, t0, 0x40
laser_dotpack:
    lw t1, 0(t0)
    nop
    beqz t1, laser_dotnext
    nop
    sh a1, 0x1C(t1)             # w, h du 2e TILE
    sh a1, 0x1E(t1)
laser_dotnext:
    addiu t3, t3, -1
    bnez t3, laser_dotpack
    addiu t0, t0, 4
laser_ret:
    jr ra
    nop

.align 2
fps_root:
    .word 0, 0
"""

HOOKS = [(0x80066574, "0000728c80004230", "jal fps\nnop")]   # lw s2,0(v1) ; andi v0,v0,0x80


def cave():
    code, sym = mips.assemble(CAVE_SRC.replace("WORLD", world_src()), CAVE, SYM)
    if CAVE + len(code) > CAVE_END:
        raise SystemExit(f"code fps trop gros ({len(code)} octets)")
    return code, sym


def patch(exe):
    out = bytearray(exe)
    code, sym = cave()
    off = 0x800 + CAVE - LOAD
    cur = bytes(out[off:off + CAVE_END - CAVE])
    if cur[:len(code)] != code:
        if hashlib.sha1(cur).hexdigest() != CAVE_SHA1:
            raise SystemExit(f"EXE inattendu à {CAVE:08x} (pas la version PAL France ?)")
        out[off:off + len(code)] = code
    for addr, orig, src in HOOKS:
        new, _ = mips.assemble(src, addr, sym)
        o = 0x800 + addr - LOAD
        cur = bytes(out[o:o + len(new)])
        if cur == new:
            continue
        if cur != bytes.fromhex(orig):
            raise SystemExit(f"EXE inattendu à {addr:08x} (pas la version PAL France ?)")
        out[o:o + len(new)] = new
    return bytes(out)


def patch_image(path):
    disc = psxiso.Disc(path)
    files = disc.files()
    name = next(p for p in files if p in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
    lba, size = files[name]
    exe = disc.read(lba, size)
    disc.f.close()
    new = patch(exe)
    if new != exe:
        write_file_inplace(path, lba, new)
    return name


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        print(f"{p} : {patch_image(p)} patché (tir en vue subjective)")


if __name__ == "__main__":
    main()
