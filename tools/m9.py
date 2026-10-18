#!/usr/bin/env python3
"""
m9.py - Patch optionnel : M9 tranquillisant (et PSG1-T, claymores zzz) pour MGS1 PAL France
et PAL Europe anglaise (adresses traduites par pal.py, textes du menu en anglais).

Le M9 partage la case du SOCOM : dans le menu des armes (R2), sur le SOCOM, Triangle
passe du SOCOM au M9 (icône bleue, toujours silencieux) et inversement. Même
chose sur le PSG1 (PSG1-T). Les munitions sont communes avec l'arme d'origine. Le choix
est gardé dans la sauvegarde (variable de jeu 83, inutilisée par le jeu d'origine).

Effet d'une fléchette sur un soldat (cible qu'on peut saisir) :
- hors alerte : il s'effondre et dort pour de bon (zzz), sans perdre de vie ;
- Meryl (meryl7.c, meryl72.c : même code que les soldats) se relève, elle, après 2 s au sol
  (moins de 5 s après la fléchette) : sinon le jeu reste bloqué quand elle doit suivre Snake ;
- le M9 se charge d'une fléchette à la fois (chargeur de 1) ;
- en alerte ou en recherche (évasion) : le 1er tir le secoue, il s'endort 8 s plus tard,
  ou tout de suite au 2e tir.
Chiens-loups (dog.c : s09a, s12b, s12c) : une fléchette les endort pour de bon (animation et zzz
du sommeil des chiens), sans perte de vie.
Sur les autres cibles (boss, caméras...) : mêmes dégâts que l'arme d'origine.

Claymores zzz : même bascule (Triangle) sur la case CLAYMORE (« CLAY.ZZZ »). Le mode est lu à la
pose de la mine ; à l'explosion (souffle et éclats), un soldat s'endort tout de suite, même en
alerte ; les autres cibles (Raven, Snake...) prennent les dégâts normaux. Une claymore zzz est
silencieuse : pas de détonation ni de bruit entendu par les gardes, pas de flash ni de boule de
feu, éclats invisibles ; juste un « pfft » et une bouffée de fumée.

Le code ajouté va dans le menu de débogage de l'EXE (écrans mem/pow/ply/obj/tex et
menu_viewer_act, jamais appelés : 0x800447e4-0x80045900 pour m9 ; la fin sert à carre.py et psg1.py). Le sommeil sans réveil et les zzz
demandent aussi de retoucher le code des soldats dans chaque overlay de STAGE.DIR.
Toutes les retouches vérifient les octets d'origine (motifs) avant d'écrire.

  python m9.py image.bin [image2.bin ...]     patch en place (images VOSTFR, FR ou UK d'origine)
"""

import struct, sys

import mips, pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000  # adresse de chargement de l'EXE (en-tête PS-X EXE de 0x800 octets)
CAVE, CAVE_END = 0x800447E4, 0x80045400  # suite : fps.py (0x80045400), carre.py (0x80045900), psg1.py (0x80045a08)
CAVE2, CAVE2_END = 0x80045980, 0x80045A08  # 2e zone (chiens), fin de celle de carre.py

SYM = dict(
    MODES=0x800B6426,        # linkvar 83 : bit 0 = M9, bit 1 = PSG1-T, bit 2 = claymore zzz
    GM_Weapon=0x800B639C,
    GM_Magazine=0x800ACFD4, GM_MagazineMax=0x800AD014,
    GM_AlertMode=0x800ACFE8,
    GV_NewActor=0x800151C8, GV_SetNamedActor=0x80015234, GV_DestroyActor=0x800152B4,
    GV_StrCode=0x80016E4C, GM_InitObjectNoRots=0x800357E4, GM_SeSet2=0x8003370C,
    NewAnime=0x800609BC, DG_GetTexture=0x8001DCE0,
    STR_SOCOM2=0x800ACE28,   # "socom2"
    GET_RPK_NEXT=0x8003EF50, GET_RPK_SOCOM=0x8003EF38, ITEMS_SOCOM2=0x800BEE74,
    INIT_SPRT=0x8003E0F0, PRINT_DESC=0x800409A4, GET_RPK=0x8003EF30, NAVIGATE=0x8003E714,
    SOCOM_RES_DONE=0x80066AE0, POWER_NEXT=0x8002E420,
    GM_PowerTarget=0x8002E264, NewJirai=0x8006C4F8, NewClaymore=0x80074EB0,
    GM_SeSet=0x800335FC, AN_Puff=0x8005EE40, GV_RandU=0x8001721C, PAL_FLASH=0x8007A680,
    CLAY_BOOM=0x80074F7C, CLAY_LOOP=0x80075008,
    SE_PFFT=0x52,            # SE_SOCOM_SUPPRESSED : le « pfft » du SOCOM silencieux
    M9CODE=0x19,             # a_mode des fléchettes (inutilisé par le jeu)
    CLAYCODE=0x1A,           # a_mode des claymores zzz (inutilisé par le jeu)
    CLAYMARK=0x4D39CCCC,     # marque d'une mine zzz (JiraiWork +0x110)
    M9FAINT=-32000,          # faint d'un soldat endormi par fléchette
    MARK=0x4D39AAAA,         # marques dans TARGET.field_18 (inutilisé par les soldats) :
    SLEEP=0x4D395A5A,        #   « secoué » (minuteur en cours) et « endormi »
    TREMBLE=8 * 25,          # 8 s (logique du jeu PAL : 25 images/s)
    DOG_ZZZ=99,              # sous-état d'un chien endormi (état 8, field_1510 ; le jeu va jusqu'à 37)
    NPC_WAKE=2 * 25,         # Meryl endormie : relevée après 2 s au sol (chute comprise : < 5 s)
    TEX_ZZZ=0xF7BB,          # GV_StrCode("zzz")
    SE_SELECT=0x17,
)

CAVE_SRC = r"""
# ---- outils -------------------------------------------------------------
# is_tranq(a0 = id d'arme) -> v0 = bit du mode si l'arme est en mode tranquillisant
is_tranq:
    li v0, 1
    beqz a0, it_bit
    li t0, 9
    beq a0, t0, it_bit
    li v0, 2
    li t0, 5                    # claymore -> bit 2
    bne a0, t0, it_no
    li v0, 4
it_bit:
    lui t0, %hi(MODES)
    lhu t0, %lo(MODES)(t0)
    nop
    jr ra
    and v0, v0, t0
it_no:
    jr ra
    move v0, zero

# ---- menu : icône (menu_weapon_get_weapon_rpk_info) ----------------------
cave_rpk:                       # a0 = id, v0 = a0 << 3 (délai)
    bnez a0, cave_rpk_other
    lui t1, %hi(MODES)
    lhu t1, %lo(MODES)(t1)
    nop
    andi t1, t1, 1
    beqz t1, cave_rpk_socom
    nop
    la v0, ITEMS_SOCOM2         # M9 : icône du SOCOM silencieux
    jr ra
    nop
cave_rpk_socom:
    j GET_RPK_SOCOM
    nop
cave_rpk_other:
    j GET_RPK_NEXT
    nop

# ---- menu : nom de l'arme (s7 = &table[id] posé dans le délai) ------------
cave_name:                      # a0 = id
    move t8, ra
    jal is_tranq
    nop
    move ra, t8
    beqz v0, cave_name_go
    li t0, 1
    la s7, name_m9
    beq v0, t0, cave_name_go
    li t0, 2
    la s7, name_psg1t
    beq v0, t0, cave_name_go
    nop
    la s7, name_clay
cave_name_go:
    j GET_RPK
    nop

# ---- menu : couleur du sprite (s6 = panneau, a0 = prim) -------------------
cave_sprt:
    lh t0, 0(s6)
    move t8, ra
    move t9, a0
    move a0, t0
    jal is_tranq
    nop
    move ra, t8
    beqz v0, cave_sprt_go
    move a0, t9
    lbu t0, 4(a0)               # 0x80 = case choisie, 0x40 = autres
    li t2, 0x00C05830
    li t3, 0x00602C18
    li t1, 0x80
    beq t0, t1, cave_sprt_bright
    nop
    move t2, t3
cave_sprt_bright:
    sw t2, 4(a0)
cave_sprt_go:
    j INIT_SPRT
    nop

# ---- menu : Triangle sur SOCOM, PSG1 ou CLAYMORE -> bascule du mode ------
cave_nav:                       # a0 = menu armes, a1 = manette
    lhu t0, 2(a1)
    nop
    andi t0, t0, 0x10           # Triangle (les 4 directions servent à naviguer)
    beqz t0, cave_nav_go
    lw t1, 0xC(a0)
    nop
    lw t2, 4(t1)
    nop
    sll t2, t2, 3
    addu t1, t1, t2
    lh t3, 0x24(t1)             # position : 0 = immobile
    lh t4, 0x20(t1)             # id
    bnez t3, cave_nav_go
    li t0, 1
    beqz t4, cave_nav_toggle
    li t5, 9
    beq t4, t5, cave_nav_toggle
    li t0, 2
    li t5, 5
    bne t4, t5, cave_nav_go
    li t0, 4
cave_nav_toggle:
    lui t1, %hi(MODES)
    lhu t2, %lo(MODES)(t1)
    nop
    xor t2, t2, t0
    sh t2, %lo(MODES)(t1)
    sw zero, 0x2F0(gp)          # description réaffichée (compteur, déjà affichée)
    sw zero, 0x2F4(gp)
    addiu sp, sp, -0x20
    sw ra, 0x10(sp)
    sw a0, 0x14(sp)
    sw a1, 0x18(sp)
    move a0, zero
    li a1, 0x3F
    jal GM_SeSet2
    li a2, SE_SELECT
    lw ra, 0x10(sp)
    lw a0, 0x14(sp)
    lw a1, 0x18(sp)
    addiu sp, sp, 0x20
cave_nav_go:
    j NAVIGATE
    nop

# ---- SOCOM : modèle (GetResources), s1 = &GM_SilencerFlag, s2 = work ------
cave_res:                       # v0 = GM_SilencerFlag (chargé dans le délai)
    lui t0, %hi(MODES)
    lhu t0, %lo(MODES)(t0)
    nop
    andi t0, t0, 1
    bnez t0, cave_res_m9
    nop
    jr ra
    nop
cave_res_m9:                    # M9 : modèle silencieux, sans toucher au silencieux du SOCOM
    la a0, STR_SOCOM2
    jal GV_StrCode
    nop
    addiu s0, s2, 0x20
    move a0, s0
    move a1, v0
    li a2, 0x6D
    jal GM_InitObjectNoRots
    move a3, zero
    li t0, 1
    j SOCOM_RES_DONE
    sh t0, 0x56(s2)

# ---- menu : description de l'arme (remplace jal menu_printDescription, a0 = texte) ---
cave_desc:                      # at = 0x800a0000 + 4 * id (index de la table)
    move t9, a0
    andi a0, at, 0xFF
    srl a0, a0, 2
    move t8, ra
    jal is_tranq
    nop
    move ra, t8
    beqz v0, cave_desc_go
    move a0, t9
    la t1, desc_m9
    li t0, 1
    beq v0, t0, cave_desc_set
    nop
    la t1, desc_psg1t
    li t0, 2
    beq v0, t0, cave_desc_set
    nop
    la t1, desc_clay
cave_desc_set:
    move a0, t1
cave_desc_go:
    j PRINT_DESC
    nop

# ---- ramassage d'une arme (s1 = objet) : « SOCOM + M9 », « PSG1 + PSG1-T » ---
cave_pickup:                    # v0 est posé dans le délai : ne pas y toucher
    lw v1, 0x118(s1)            # instruction remplacée : nom de l'objet
    lbu t0, 0x113(s1)           # type : 1 = arme
    li t1, 1
    bne t0, t1, cave_pickup_ret
    lh t0, 0x114(s1)            # id de l'arme
    la t2, str_get_m9
    beqz t0, cave_pickup_set
    li t1, 9
    la t2, str_get_psg1t
    beq t0, t1, cave_pickup_set
    li t1, 5
    bne t0, t1, cave_pickup_ret
    nop
    la t2, str_get_clay
cave_pickup_set:
    move v1, t2
    sw v1, 0x118(s1)
cave_pickup_ret:
    jr ra
    nop

# ---- M9 : une fléchette à la fois (chargeur de 1) -------------------------
# NewSOCOM : v1 = chargeur max (12/13), a0 = chargeur (min(v1, munitions)) ; v0 à garder
cave_mag:
    lui t0, %hi(MODES)
    lhu t0, %lo(MODES)(t0)
    nop
    andi t0, t0, 1
    beqz t0, cave_mag_set
    slti t1, a0, 2
    li v1, 1
    bnez t1, cave_mag_set
    nop
    li a0, 1
cave_mag_set:
    lui at, %hi(GM_MagazineMax)
    sh v1, %lo(GM_MagazineMax)(at)
    lui at, %hi(GM_Magazine)
    jr ra
    sh a0, %lo(GM_Magazine)(at)

# SOCOM Act, après un tir : a0 = chargeur max (12 d'origine)
cave_magmax:
    lui t0, %hi(MODES)
    lhu t0, %lo(MODES)(t0)
    li a0, 12
    andi t0, t0, 1
    beqz t0, cave_magmax_ret
    nop
    li a0, 1
cave_magmax_ret:
    jr ra
    nop

# ---- balle : marque les fléchettes (s0 = balle, s3 = camp) -----------------
cave_bullet:
    sw s4, 0x134(s0)            # instruction remplacée
    li t0, 1
    bne s3, t0, cave_bullet_ret
    lui t1, %hi(GM_Weapon)
    lh t1, %lo(GM_Weapon)(t1)
    lui t2, %hi(MODES)
    lhu t2, %lo(MODES)(t2)
    beqz t1, cave_bullet_chk    # SOCOM -> bit 0
    li t3, 1
    li t4, 9
    bne t1, t4, cave_bullet_ret
    li t3, 2                    # PSG1 -> bit 1
cave_bullet_chk:
    and t2, t2, t3
    beqz t2, cave_bullet_ret
    li t0, M9CODE
    sh t0, 0x82(s0)             # TARGET.a_mode de la balle
cave_bullet_ret:
    jr ra
    nop

# ---- GM_PowerTarget : s2 = attaquant, s3 = cible touchée, s0 = s3 + 0x2c --
cave_power:
    lh t0, 0x3E(s2)
    li t1, M9CODE
    beq t0, t1, cave_power_tranq
    li t2, 1                    # a_mode normal : balle
    li t1, CLAYCODE
    beq t0, t1, cave_power_tranq
    li t2, 2                    # a_mode normal : claymore
    b cave_power_dart           # pas une fléchette
    move t3, zero
cave_power_tranq:
    lhu t0, 0(s3)
    lhu t1, 2(s3)
    andi t0, t0, 2              # TARGET_CAPTURE...
    beqz t0, cave_power_other
    li t0, 2
    beq t1, t0, cave_power_soldier  # ... et camp ennemi : soldat (Snake aussi est saisissable)
    nop
cave_power_other:
    sh t2, 0x3E(s2)             # autre cible : dégâts normaux (chiens : voir cave_dogdart)
    move t3, s3
cave_power_dart:
    lui t4, %hi(dart_tgt)
    sw t3, %lo(dart_tgt)(t4)    # cible de la dernière fléchette (0 : autre tir)
cave_power_orig:
    lhu v0, -0x26(s0)           # instructions remplacées
    lh v1, -8(s0)
    jr ra
    nop
cave_power_soldier:
    lw t1, 0x18(s3)
    li t2, SLEEP
    bne t1, t2, cave_power_awake
    lh t0, 0x2A(s3)             # faint
    nop
    bltz t0, cave_power_next    # déjà endormi : rien (éclats suivants, fléchette de trop)
    nop
cave_power_awake:
    lh t0, 0x3E(s2)
    li t1, CLAYCODE
    beq t0, t1, cave_power_knock  # claymore : endormi tout de suite, même en alerte
    nop
    lui t0, %hi(GM_AlertMode)
    lw t0, %lo(GM_AlertMode)(t0)
    lw t1, 0x18(s3)
    li t2, MARK
    slti t0, t0, 2
    bnez t0, cave_power_knock   # pas d'alerte : endormi tout de suite
    nop
    beq t1, t2, cave_power_knock  # déjà secoué : endormi
    nop
    lhu t0, 6(s3)               # 1er tir en alerte : secoué (comme un coup de poing)
    li t1, 3
    ori t0, t0, 4
    sh t0, 6(s3)
    sh t1, 0x3E(s3)
    sw t2, 0x18(s3)
    li a0, 5                    # minuteur de 8 s
    jal GV_NewActor
    li a1, 0x28
    beqz v0, cave_power_next
    li t0, TREMBLE
    sw s3, 0x20(v0)             # cible et compte à rebours
    sw t0, 0x24(v0)
    move a0, v0
    la a1, timer_act
    la a3, timer_name
    jal GV_SetNamedActor
    move a2, zero
    b cave_power_next
    nop
cave_power_knock:
    jal knock
    move a0, s3
cave_power_next:
    j POWER_NEXT
    move s1, zero               # la fléchette s'arrête

# knock(a0 = TARGET) : le soldat s'effondre et dort
knock:
    lhu t0, 6(a0)
    li t1, 9
    ori t0, t0, 4
    sh t0, 6(a0)
    sh t1, 0x3E(a0)
    li t1, M9FAINT
    sh t1, 0x2A(a0)
    sw zero, 0x2C(a0)           # pas de poussée
    sw zero, 0x30(a0)
    li t1, SLEEP
    jr ra
    sw t1, 0x18(a0)             # marque « endormi »

# ---- claymores zzz -----------------------------------------------------------
# pose (acteur mine.c) : NewJirai(a0, a1) ; mine zzz si le mode est actif à la pose
cave_mine:
    addiu sp, sp, -0x18
    sw ra, 0x10(sp)
    jal NewJirai
    nop
    beqz v0, cave_mine_ret
    lui t0, %hi(MODES)
    lhu t0, %lo(MODES)(t0)
    nop
    andi t0, t0, 4
    beqz t0, cave_mine_ret
    nop
    li t1, CLAYMARK
    sw t1, 0x110(v0)            # JiraiWork +0x110, inutilisé (mis à zéro par GV_NewActor)
cave_mine_ret:
    lw ra, 0x10(sp)
    addiu sp, sp, 0x18          # délai de chargement : jr ne doit pas suivre le lw
    jr ra
    nop

# explosion (jirai.c, s0 = mine) : souffle sur place, a0 = TARGET local
cave_jblast:
    lw t0, 0x110(s0)
    li t1, CLAYMARK
    bne t0, t1, cave_jblast_go
    li t0, CLAYCODE
    sh t0, 0x3E(a0)
cave_jblast_go:
    j GM_PowerTarget
    nop

# explosion : éclats (NewClaymore), marqués pendant leur création
cave_newclay:
    lw t0, 0x110(s0)
    li t1, CLAYMARK
    xor t0, t0, t1
    sltiu t0, t0, 1
    lui t1, %hi(clay_flag)
    sw t0, %lo(clay_flag)(t1)
    addiu sp, sp, -0x18
    sw ra, 0x10(sp)
    jal NewClaymore
    nop
    lui t1, %hi(clay_flag)
    sw zero, %lo(clay_flag)(t1)
    lw ra, 0x10(sp)
    addiu sp, sp, 0x18
    jr ra
    nop

# éclat (claymore.c, s0 = éclat, TARGET en +0x3c) : weapon = WP_Claymore
cave_claytgt:
    li v0, 5                    # instructions remplacées
    sw v0, 0x80(s0)
    lui t0, %hi(clay_flag)
    lw t0, %lo(clay_flag)(t0)
    nop
    beqz t0, cave_claytgt_ret
    li t0, CLAYCODE
    sh t0, 0x7A(s0)             # TARGET.a_mode
    lw t1, 0x84(s0)             # éclat invisible (DG_InvisiblePrim)
    nop
    lw t2, 0x24(t1)
    nop
    ori t2, t2, 0x100
    sw t2, 0x24(t1)
cave_claytgt_ret:
    jr ra
    nop

# NewClaymore, 1er appel (s0 = 8) : explosion. Claymore zzz : pas de son d'explosion, pas de
# bruit pour les gardes (GM_SetNoise), pas de boule de feu ; un « pfft » et une bouffée de fumée.
cave_clayexp:                   # s0 = param_4, s2 = position
    li v0, 8
    bne s0, v0, cave_clayexp_loop
    lui t0, %hi(clay_flag)
    lw t0, %lo(clay_flag)(t0)
    nop
    bnez t0, cave_clayexp_zzz
    nop
    j CLAY_BOOM
    nop
cave_clayexp_zzz:
    move a0, s2
    jal GM_SeSet
    li a1, SE_PFFT
    jal AN_Puff
    move a0, s2
cave_clayexp_loop:
    j CLAY_LOOP
    nop

# claymore_Act (s1 = éclat) : GV_RandU(32) décide de l'étincelle et du ricochet sur un mur
cave_clayspark:
    lh t0, 0x7A(s1)
    li t1, CLAYCODE
    beq t0, t1, cave_clayspark_zzz
    nop
    j GV_RandU
    nop
cave_clayspark_zzz:
    jr ra
    move v0, zero               # 0 : ni étincelle ni ricochet

# jirai.c (s0 = mine) : flash blanc de l'écran à l'explosion, sauf pour une mine zzz
cave_flash:
    lw t0, 0x110(s0)
    li t1, CLAYMARK
    beq t0, t1, cave_flash_ret
    nop
    j PAL_FLASH
    nop
cave_flash_ret:
    jr ra
    nop

# minuteur : endort le soldat secoué au bout de 8 s
timer_act:                      # a0 = acteur
    addiu sp, sp, -0x18
    sw ra, 0x10(sp)
    sw s0, 0x14(sp)
    move s0, a0
    lw a0, 0x20(s0)
    li t2, MARK
    lw t1, 0x18(a0)
    lhu t0, 0(a0)
    bne t1, t2, timer_kill      # marque effacée (déjà endormi, cible libérée)
    nop
    beqz t0, timer_kill
    lw t0, 0x24(s0)
    nop
    addiu t0, t0, -1
    bgtz t0, timer_ret
    sw t0, 0x24(s0)
    jal knock
    nop
timer_kill:
    jal GV_DestroyActor
    move a0, s0
timer_ret:
    lw ra, 0x10(sp)
    lw s0, 0x14(sp)
    jr ra
    addiu sp, sp, 0x18

# ---- overlays : soldat au sol ---------------------------------------------
# remplace l'appel à AN_Piyopiyo (t9) : pas d'étoiles pour un dormeur
# relais par overlay : t9 = AN_Piyopiyo, t8 = décalage de la cible dans le soldat
cave_piyo:
    addu t0, s0, t8
    lw t0, 0(t0)
    li t1, SLEEP
    lw t0, 0x18(t0)
    nop
    bne t0, t1, cave_piyo_stars
    nop
    jr ra
    nop
cave_piyo_stars:
    jr t9
    nop

# test de réveil : v0 = délai (chargé dans le délai), s1 = temps
# t8 = décalage de la cible dans le soldat, t7 = 1 pour Meryl (réveil au bout de NPC_WAKE images)
cave_wake:
    addu t0, s0, t8
    lw t0, 0(t0)
    li t1, SLEEP
    lw t2, 0x18(t0)
    nop
    bne t2, t1, cave_wake_ret
    andi t3, s1, 63
    beqz t7, wake_zzz           # soldat : jamais de réveil
    slti t4, s1, NPC_WAKE
    bnez t4, wake_zzz           # Meryl : se relève après NPC_WAKE images au sol
    nop
    move v0, zero               # délai 0 : le jeu la relève tout de suite
    jr ra
    sw zero, 0x18(t0)           # réveillée : plus endormie
wake_zzz:
    li t1, 1
    bne t3, t1, cave_wake_sleep
    nop
    addiu sp, sp, -0x30
    sw ra, 0x28(sp)
    sw v0, 0x2C(sp)
    sw t7, 0x24(sp)
    lw t0, 0x9C(s0)             # tête (comme les étoiles)
    nop
    lw t1, 0x284(t0)
    lw t2, 0x288(t0)
    lw t3, 0x28C(t0)
    addiu t2, t2, 250
    sh t1, 0x10(sp)
    sh t2, 0x12(sp)
    jal zzz
    sh t3, 0x14(sp)
    lw ra, 0x28(sp)
    lw v0, 0x2C(sp)
    lw t7, 0x24(sp)
    addiu sp, sp, 0x30
cave_wake_sleep:
    bnez t7, cave_wake_ret      # Meryl : délai d'origine
    nop
    move v0, s1                 # soldat : jamais de réveil
cave_wake_ret:
    jr ra
    nop

# zzz(pos en 0x10(sp) de l'appelant) : copie de AN_Sleep
zzz:
    addiu sp, sp, -0x38
    sw ra, 0x30(sp)
    sw s0, 0x2C(sp)
    jal DG_GetTexture
    li a0, TEX_ZZZ
    beqz v0, zzz_ret            # texture absente de ce stage
    lw t0, 0x48(sp)
    lw t1, 0x4C(sp)
    sw t0, 0x10(sp)             # PRESCRIPT : pos
    sw t1, 0x14(sp)
    sw zero, 0x18(sp)           # vitesse nulle
    sw zero, 0x1C(sp)
    sh zero, 0x22(sp)
    la t2, anm_zzz
    addiu t3, sp, 0x10
    sw t3, 0x14(t2)
    move s0, zero
zzz_loop:
    sh s0, 0x20(sp)
    move a0, zero
    move a1, zero
    la a2, anm_zzz
    jal NewAnime
    nop
    addiu s0, s0, 1
    slti t0, s0, 3
    bnez t0, zzz_loop
    nop
zzz_ret:
    lw ra, 0x30(sp)
    lw s0, 0x2C(sp)
    jr ra
    addiu sp, sp, 0x38

# ---- chiens : état 8 (« blessé »), sous-état DOG_ZZZ = endormi ---------------------
# remplace « lw v1, 0x1510(s0) ; li s4, 1 » au début du gestionnaire de l'état 8 (dog.c) :
# s3 = travail, s1 = n° du chien, s0 = travail + 4 * n°, t9 = (adresse du crochet - OVB) / 4
cave_doghurt:
    lw v1, 0x1510(s0)
    li s4, 1                    # instructions remplacées
    li t0, DOG_ZZZ
    bne v1, t0, doghurt_ret
    sll t9, t9, 2
    lui t0, %hi(OVB)
    addiu t0, t0, %lo(OVB)
    addu t9, t9, t0
    move a0, s3                 # Dog_800CB23C(travail, 13 = dormir, DOG_ZZZ, n°)
    li a1, 13
    li a2, DOG_ZZZ
    move a3, s1
    addiu ra, t9, DOG_EPI       # puis fin du gestionnaire
    addiu t9, t9, DOG_CB
    jr t9
    nop
doghurt_ret:
    jr ra
    nop

# ---- données ---------------------------------------------------------------
name_m9:
    .word str_m9, 2
name_psg1t:
    .word str_psg1t, 4
name_clay:
    .word str_clay, 8
str_m9:
    .asciiz "M9"
str_psg1t:
    .asciiz "PSG1-T"
desc_m9:
DESC_M9
desc_psg1t:
DESC_PSG1T
desc_clay:
DESC_CLAY
str_get_m9:
    .asciiz "SOCOM + M9"
str_get_psg1t:
    .asciiz "PSG1 + PSG1-T"
str_clay:
    .asciiz "CLAY.ZZZ"
str_get_clay:
    .asciiz "CLAYMORE + ZZZ"
timer_name:
    .asciiz "m9.c"
.align 2
dart_tgt:                       # cible touchée par la dernière fléchette (pas un soldat)
    .word 0
clay_flag:                      # 1 pendant la création des éclats d'une claymore zzz
    .word 0
anm_zzz:                        # ANIMATION de AN_Sleep, script recopié de STAGE.DIR
    .half TEX_ZZZ, 1, 1, 1, 1, 0, 1, 2, 2, 0
    .word 0, anm_zzz_script
anm_zzz_script:
"""

# Retouches de l'EXE : adresse, octets d'origine, source (assemblée à cette adresse)
HOOKS = [
    (0x8003EF30, "07008014", "j cave_rpk"),            # get_weapon_rpk_info
    (0x8003F15C, "ccfb000c", "jal cave_name"),         # dessin d'une case : nom
    (0x8003F1F0, "3cf8000c", "jal cave_sprt"),         # dessin d'une case : couleur
    (0x8003FB04, "c5f9000c", "jal cave_nav"),          # menu ouvert : navigation
    (0x80066A58, "0000228600000000", "jal cave_res\nlh v0, 0(s1)"),   # SOCOM GetResources
    (0x80077B44, "440112ae340114ae", "jal cave_bullet\nsw s2, 0x144(s0)"),  # NewBullet
    (0x8002E2E4, "daff0296f8ff0386", "jal cave_power\nnop"),          # GM_PowerTarget
    (0x80034A7C, "1801238e", "jal cave_pickup"),       # objet ramassé : message
    (0x8003F090, "6902010c", "jal cave_desc"),         # description de l'arme dans le menu
    (0x80068578, "3eb1010c", "jal cave_mine"),         # mine.c : pose d'une claymore
    (0x8006BFC0, "99b8000c", "jal cave_jblast"),       # jirai.c : souffle de l'explosion
    (0x8006C010, "acd3010c", "jal cave_newclay"),      # jirai.c : éclats (NewClaymore)
    (0x80074CEC, "05000224800002ae", "jal cave_claytgt\nnop"),  # claymore.c : cible d'un éclat
    (0x80074F70, "0800022424000216", "j cave_clayexp\nmove s5, zero"),  # NewClaymore : explosion
    (0x80074B0C, "875c000c", "jal cave_clayspark"),    # claymore.c : étincelle et ricochet
    (0x8006BF74, "a0e9010c", "jal cave_flash"),        # jirai.c : flash blanc
    (0x80066DA0, "0b80013c14d023a40b80013cd4cf24a4", "jal cave_mag\nnop\nnop\nnop"),  # NewSOCOM : chargeur
    (0x8006697C, "0c000424", "jal cave_magmax"),       # SOCOM Act : chargeur après un tir
]


# en-tête de l'ANIMATION des zzz (AN_Sleep) dans les overlays
ZZZ_HDR = struct.pack("<10H", 0xF7BB, 1, 1, 1, 1, 0, 1, 2, 2, 0)


def zzz_script(stage, ovb):
    """Script d'animation des zzz (AN_Sleep), recopié d'un overlay de STAGE.DIR."""
    hdr = ZZZ_HDR
    for name, ovl, _ in overlays(stage):
        k = ovl.find(hdr)
        while k >= 0:
            p = struct.unpack_from("<I", ovl, k + 0x18)[0] - ovb
            if 0 <= p < len(ovl):
                end = p
                for _ in range(3):      # 3 sous-scripts, chacun finit par 0D 0F
                    end = ovl.find(b"\x0d\x0f", end) + 2
                if end > p:
                    return ovl[p:end]
            k = ovl.find(hdr, k + 1)
    raise SystemExit("script zzz introuvable dans STAGE.DIR")


CAVE_SHA1 = "38b1bbb1a550a498f5e9c7615085c0c9bf34f55b"  # menu de débogage d'origine
CAVE2_SHA1 = "a06643c50b4c07555558449ffa9db003a71d83b5"

# 2e zone : fléchette sur un chien (fonction de dégâts de dog.c, avant le choix blessé / mort)
CAVE2_SRC = r"""
# remplace « lh v1, 0x3e(s2) ; li v0, 4 » : s1 = travail, s0 = n° du chien, s2 = sa cible,
# t9 = (adresse du crochet - OVB) / 4
cave_dogdart:
    lh v1, 0x3E(s2)
    lui t0, %hi(dart_tgt)
    lw t1, %lo(dart_tgt)(t0)
    li v0, 4                    # instructions remplacées
    bne t1, s2, dogdart_ret     # pas une fléchette : blessé / mort comme d'habitude
    nop
    sw zero, %lo(dart_tgt)(t0)
    sll t1, s0, 2
    addu t1, t1, s1
    li t2, 8                    # état 8 : ni vue, ni mouchoir (dog.c : « alive » = état < 8 ou > 13)
    sw t2, 0x14F8(t1)
    li t2, DOG_ZZZ
    sw t2, 0x1510(t1)
    li t2, 1
    sw t2, 0x14E0(t1)           # immobile (dog.c, état 8)
    lh t3, 0x26(s2)             # vie
    nop
    bgtz t3, dogdart_clr
    nop
    sh t2, 0x26(s2)             # au moins 1 : pas de mort
dogdart_clr:
    sll t9, t9, 2
    lui t0, %hi(OVB)
    addiu t0, t0, %lo(OVB)
    addu t9, t9, t0
    addiu t9, t9, DOG_CLR       # efface « touché » et sort
    jr t9
    nop
dogdart_ret:
    jr ra
    nop
"""


# Textes de description (police du menu : 《 》 = B0 14 / D0 15, retour à la ligne 80 7C,
# accents 1F xx). Au plus 29 caractères par ligne, comme les textes d'origine ; la police est
# proportionnelle : une ligne trop large (« Fusil tranquillisant : endort ») passe à la ligne.
DESCRIPTIONS = {
    "fr": {
        "DESC_M9": ("M9", ["Pistolet tranquillisant :", "endort les gardes sans bruit.",
                           "Triangle : retour au SOCOM."]),
        "DESC_PSG1T": ("PSG1-T", ["Fusil tranquillisant :", "endort les gardes de loin.",
                                  "Triangle : retour au PSG1."]),
        "DESC_CLAY": ("Claymore ZZZ", ["Mine silencieuse : endort les", "gardes qui passent devant.",
                                       "Triangle : claymore normale."]),
    },
    "en": {   # même style que les textes anglais d'origine (« Socom Pistol », « Sniper rifle. »)
        "DESC_M9": ("M9", ["Tranquilizer pistol.", "Puts guards to sleep quietly.",
                           "Triangle: back to Socom."]),
        "DESC_PSG1T": ("PSG1-T", ["Tranquilizer sniper rifle.", "Puts guards to sleep.",
                                  "Triangle: back to PSG1."]),
        "DESC_CLAY": ("Claymore ZZZ", ["Silent mine: puts guards", "to sleep when they pass.",
                                       "Triangle: normal claymore."]),
    },
}
ACCENTS = {"à": 0x09, "â": 0x0A, "ç": 0x0E, "é": 0x0F, "è": 0x10, "ê": 0x11, "î": 0x15}


def encode_desc(name, lines):
    out = bytearray(b"\xb0\x14" + name.encode("ascii") + b"\xd0\x15")
    for line in lines:
        assert len(line) <= 29, line
        out += b"\x80\x7c"
        for c in line:
            out += bytes([0x1F, ACCENTS[c]]) if c in ACCENTS else c.encode("ascii")
    return bytes(out) + b"\0"


def build_cave(stage, sites, v="FR"):
    """Assemble le code ajouté, avec un relais par variante de soldat (voir scan_overlay)."""
    stubs = []
    for t in sorted({s["target"] for ss in sites.values() for s in ss}):
        stubs += [f"wake_{t:x}:", "    li t7, 0", "    j cave_wake", f"    li t8, {t}"]
    for t in sorted({s["target"] for ss in sites.values() for s in ss if s["npc"]}):
        stubs += [f"wake_{t:x}_npc:", "    li t7, 1", "    j cave_wake", f"    li t8, {t}"]
    for x, t in sorted({(s["piyo"], s["target"]) for ss in sites.values() for s in ss if s["piyo"]}):
        stubs += [f"piyo_{x:x}_{t:x}:", f"    lui t9, %hi({x})", f"    addiu t9, t9, %lo({x})",
                  "    j cave_piyo", f"    li t8, {t}"]
    script = zzz_script(stage, pal.ovb(v))
    cave_src = CAVE_SRC
    # gp+0x2f0/0x2f4 (description du menu) : mêmes décalages dans les deux versions
    assert pal.gp(v, 0x2F0) == 0x2F0 and pal.gp(v, 0x2F4) == 0x2F4
    for key, (name, lines) in DESCRIPTIONS[pal.lang(v)].items():
        cave_src = cave_src.replace(key, "    .byte " + ", ".join(str(b) for b in encode_desc(name, lines)))
    src = "\n".join([cave_src + "    .byte " + ", ".join(str(b) for b in script), ".align 2"] + stubs) + "\n"
    sym = pal.syms(v, SYM)
    sym.update(OVB=pal.ovb(v), **dog_offsets(stage, v))
    code, sym = mips.assemble(src, pal.addr(v, CAVE), sym)
    if CAVE + len(code) > CAVE_END:
        raise SystemExit(f"code M9 trop gros ({len(code)} octets)")
    code2, sym = mips.assemble(CAVE2_SRC, pal.addr(v, CAVE2), sym)
    if CAVE2 + len(code2) > CAVE2_END:
        raise SystemExit(f"code M9 (2e zone) trop gros ({len(code2)} octets)")
    return code, code2, sym


def patch_exe(exe, code, code2, sym, v="FR"):
    out = bytearray(exe)
    if not (pal.cave_ok(v, exe, CAVE, CAVE_END, CAVE_SHA1)
            and pal.cave_ok(v, exe, CAVE2, CAVE2_END, CAVE2_SHA1)):
        raise SystemExit(f"EXE inattendu ({v}) : menu de débogage déjà utilisé ?")
    for zone, c in ((CAVE, code), (CAVE2, code2)):
        off = 0x800 + pal.addr(v, zone) - LOAD
        out[off:off + len(c)] = c
    for addr, orig, src in HOOKS:
        a = pal.addr(v, addr)
        new, _ = mips.assemble(src, a, sym)
        o = 0x800 + a - LOAD
        if not pal.same(v, bytes(out[o:o + len(new)]), orig):
            raise SystemExit(f"EXE inattendu à {a:08x} ({v})")
        out[o:o + len(new)] = new
    return bytes(out)


def is_patched_exe(exe, v="FR"):
    addr, orig, _ = HOOKS[0]
    o = 0x800 + pal.addr(v, addr) - LOAD
    return not pal.same(v, exe[o:o + 4], orig)


# ---- STAGE.DIR ----------------------------------------------------------------

def overlays(stage):
    """(nom, octets, position) de l'overlay de chaque stage."""
    n = struct.unpack_from("<I", stage, 0)[0]
    for i in range(n // 12):
        name = stage[4 + 12 * i:12 + 12 * i].rstrip(bytes(1)).decode("latin1")
        sec = struct.unpack_from("<I", stage, 12 + 12 * i)[0]
        _, mode, ext, size = struct.unpack_from("<HBBi", stage, sec * 2048 + 4)
        if chr(mode) == "s" and chr(ext) == "b" and size > 0:
            pos = (sec + 1) * 2048
            yield name, stage[pos:pos + size], pos


def words(b):
    return list(struct.unpack(f"<{len(b) // 4}I", b[:len(b) // 4 * 4]))


def jal_target(x):
    return 0x80000000 | (x & 0x3FFFFFF) << 2 if x >> 26 == 3 else None


def is_piyo(w, addr, ovb):
    """Vrai si la fonction à addr est AN_Piyopiyo (animation de texture GV_StrCode 0xCAFE)."""
    i = (addr - ovb) // 4
    if not 0 <= i < len(w):
        return False  # fonction de l'EXE
    for k in range(i, min(i + 40, len(w) - 1)):
        if w[k] >> 16 == 0x3C10 and w[k + 1] >> 16 == 0x2610:  # lui s0 / addiu s0 : ANIMATION
            p = ((w[k] & 0xFFFF) << 16) + ((w[k + 1] & 0xFFFF) ^ 0x8000) - 0x8000 - ovb
            return 0 <= p < 4 * len(w) and w[p // 4] & 0xFFFF == 0xCAFE
    return False


NPC_FILES = ("meryl",)   # acteurs de l'histoire au code de soldat : réveil normal


def actor_files(ovl, w, ovb, set_named):
    """(fonction act, nom du fichier source) de chaque GV_SetNamedActor(acteur, act, die, "x.c")
    de l'overlay (a1 et a3 posés par lui + addiu juste avant l'appel)."""
    out = []
    jal = 3 << 26 | (set_named >> 2) & 0x3FFFFFF
    for i, x in enumerate(w):
        if x != jal:
            continue
        r = {}
        for k in range(max(0, i - 12), min(len(w), i + 2)):
            y = w[k]
            if y >> 26 == 0xF:
                r[(y >> 16) & 31] = (y & 0xFFFF) << 16
            elif y >> 26 == 9 and (y >> 21) & 31 in r and (y >> 21) & 31 == (y >> 16) & 31:
                r[(y >> 16) & 31] = (r[(y >> 21) & 31] + ((y & 0xFFFF) ^ 0x8000) - 0x8000) & 0xFFFFFFFF
        o = r.get(7, ovb - 1) - ovb
        e = ovl.find(b"\0", o) if 5 in r and 0 <= o < len(ovl) else -1
        if e > 0:
            out.append((r[5], ovl[o:e].decode("latin1")))
    return sorted(out)


def site_owner(acts, addr):
    """Fichier de l'acteur (soldat, zako, Meryl) dont la fonction act précède le site."""
    own = [(a, n) for a, n in acts if a <= addr and n.startswith(("watcher", "zako", "meryl"))]
    return max(own)[1] if own else None


def scan_overlay(ovl, ovb, set_named=None):
    """Repère chaque mode « soldat au sol » : test de réveil, appel des étoiles, décalages."""
    w = words(ovl)
    acts = actor_files(ovl, w, ovb, set_named) if set_named else []
    sites = []
    for i in range(len(w) - 6):
        # lh v0,DELAI(s0); nop; slt v0,v0,s1; beqz v0,..; nop; lw v1,CIBLE(s0)
        if not (w[i] >> 16 == 0x8602 and w[i + 1] == 0 and w[i + 2] == 0x0051102A
                and w[i + 3] >> 16 == 0x1040 and w[i + 4] == 0 and w[i + 5] >> 16 == 0x8E03):
            continue
        f = i
        while not (w[f] >> 16 == 0x27BD and w[f] & 0x8000):  # début de la fonction
            f -= 1
        body = range(f, i)
        if not {0x8E02009C, 0x2604009C} & {w[k] for k in body}:  # modèle du soldat en 0x9c
            continue
        piyo = [k for k in body if jal_target(w[k]) and is_piyo(w, jal_target(w[k]), ovb)]
        owner = site_owner(acts, ovb + 4 * i) if acts else None
        sites.append(dict(wake=i, owner=owner, npc=bool(owner and owner.startswith(NPC_FILES)), delay=w[i] & 0xFFFF, target=w[i + 5] & 0xFFFF,
                          piyo=jal_target(w[piyo[0]]) if len(piyo) == 1 else None,
                          piyo_at=piyo[0] if len(piyo) == 1 else None))
    return sites


def old_switch(ovl):
    """Ancienne variante de soldat (coups 1 à 4 seulement) : position du « j défaut »."""
    w = words(ovl)
    for i in range(len(w) - 7):
        # li v0,3; beq a3,v0,+5; li v0,4; beq a3,v0,..; nop; j DEFAUT; nop
        if (w[i] == 0x24020003 and w[i + 1] == 0x10E20005 and w[i + 2] == 0x24020004
                and w[i + 3] >> 16 == 0x10E2 and w[i + 4] == 0 and w[i + 5] >> 26 == 2 and w[i + 6] == 0):
            return i + 5
    return None


def scan_dogs(ovl):
    """Chiens-loups (dog.c) : index de mot du test de a_mode dans la fonction de dégâts
    (« lh v1,0x3e(s2); li v0,4; bne; li v0,3 »), du bloc qui efface « touché » et sort,
    du début du gestionnaire de l'état 8 (« lw v1,0x1510(s0); li s4,1 »), de sa sortie, et
    de Dog_800CB23C (changement d'animation). None si l'overlay n'a pas de chiens."""
    w = words(ovl)
    dmg = [i for i in range(len(w) - 4)
           if w[i] == 0x8643003E and w[i + 1] == 0x24020004 and w[i + 3] == 0x24020003]
    hurt = [i for i in range(len(w) - 2) if w[i] == 0x8E031510 and w[i + 1] == 0x24140001]
    if len(dmg) != 1 or len(hurt) != 1:
        return None
    d, h = dmg[0], hurt[0]
    clr = next(i for i in range(d, d + 80) if w[i] == 0x96420006 and w[i + 2] == 0x3042FFFB)
    j = next(i for i in range(h, h + 16) if w[i] >> 26 == 2)
    cb = [s for c in range(len(w)) if w[c] == 0x8E641494      # lw a0, 0x1494(s3)
          for s in [next((i for i in range(c, max(c - 20, 0), -1) if w[i] == 0x27BDFFD8), None)]
          if s is not None and w[s + 1] == 0xAFB20018 and w[s + 2] == 0x00809021]
    assert len(cb) == 1, "dog.c : Dog_800CB23C introuvable"
    return dict(dmg=d, clr=clr, hurt=h, epi=(w[j] & 0x3FFFFFF) << 2, cb=cb[0])


def dog_offsets(stage, v):
    """Écarts (octets) depuis les crochets, identiques dans tous les overlays d'une version."""
    ovb = pal.ovb(v)
    offs = set()
    for _, ovl, _ in overlays(stage):
        dog = scan_dogs(ovl)
        if dog:
            epi = (ovb & 0xF0000000 | dog["epi"]) - ovb
            offs.add((4 * (dog["clr"] - dog["dmg"]), epi - 4 * dog["hurt"], 4 * (dog["cb"] - dog["hurt"])))
    assert len(offs) == 1, f"dog.c : écarts différents selon les overlays ({offs})"
    clr, epi, cb = offs.pop()
    return dict(DOG_CLR=clr, DOG_EPI=epi, DOG_CB=cb)


def patch_overlay(ovl, sites, sym, ovb):
    out = bytearray(ovl)

    def put(k, src):
        new, _ = mips.assemble(src, ovb + 4 * k, sym)
        out[4 * k:4 * k + len(new)] = new

    for s in sites:
        npc = "_npc" if s["npc"] else ""
        put(s["wake"], f"jal wake_{s['target']:x}{npc}\nlh v0, {s['delay']}(s0)")
        if s["piyo"]:
            put(s["piyo_at"], f"jal piyo_{s['piyo']:x}_{s['target']:x}")
    dog = scan_dogs(ovl)
    if dog:   # adresse du crochet passée dans le délai (index de mot dans l'overlay)
        put(dog["dmg"], f"jal cave_dogdart\nori t9, zero, {dog['dmg']}")
        put(dog["hurt"], f"jal cave_doghurt\nori t9, zero, {dog['hurt']}")
    k = old_switch(ovl)
    if k is not None:  # coup 9 (fléchette) -> traité comme le coup 3 (K.O. au poing)
        default = 0x80000000 | (words(ovl)[k] & 0x3FFFFFF) << 2
        put(k, f"addiu v0, v0, 5\nbne a3, v0, {default}")
    return bytes(out)


def patch_files(exe, stage):
    """EXE et STAGE.DIR d'un disque (PAL France ou Europe) -> versions patchées (ou None si
    déjà patché)."""
    v = pal.version(exe)
    if is_patched_exe(exe, v):
        return None
    ovb = pal.ovb(v)
    set_named = pal.addr(v, SYM["GV_SetNamedActor"])
    sites = {name: scan_overlay(ovl, ovb, set_named) for name, ovl, _ in overlays(stage)}
    sites = {k: s for k, s in sites.items() if s}
    code, code2, sym = build_cave(stage, sites, v)
    new_exe = patch_exe(exe, code, code2, sym, v)
    out = bytearray(stage)
    for name, ovl, pos in overlays(stage):
        if name in sites or scan_dogs(ovl):
            out[pos:pos + len(ovl)] = patch_overlay(ovl, sites.get(name, []), sym, ovb)
    zzz = [n for n, o, _ in overlays(stage) if ZZZ_HDR in o]
    skipped = [n for n in zzz if n not in sites]
    return new_exe, bytes(out), sorted(sites), skipped


def patch_image(path):
    disc = psxiso.Disc(path)
    files = disc.files()
    name = next(p for p in files if p in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
    exe = disc.read(*files[name])
    stage = disc.read(*files["MGS/STAGE.DIR"])
    disc.f.close()
    res = patch_files(exe, stage)
    if res is None:
        return name, None, None
    new_exe, new_stage, done, skipped = res
    write_file_inplace(path, files[name][0], new_exe)
    write_file_inplace(path, files["MGS/STAGE.DIR"][0], new_stage)
    return name, done, skipped


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        name, done, skipped = patch_image(p)
        if done is None:
            print(f"{p} : déjà patché")
            continue
        print(f"{p} : {name} patché (M9 / PSG1-T), soldats endormis dans {len(done)} stages")
        if skipped:
            print(f"  motif non reconnu (sommeil = assommé normal) : {', '.join(skipped)}")


if __name__ == "__main__":
    main()
