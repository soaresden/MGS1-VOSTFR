#!/usr/bin/env python3
"""
m9.py - Patch optionnel : M9 tranquillisant (et PSG1-T) pour MGS1 PAL France.

Le M9 partage la case du SOCOM : dans le menu des armes (R2), sur le SOCOM, Triangle
passe du SOCOM au M9 (icône bleue, toujours silencieux) et inversement. Même
chose sur le PSG1 (PSG1-T). Les munitions sont communes avec l'arme d'origine. Le choix
est gardé dans la sauvegarde (variable de jeu 83, inutilisée par le jeu d'origine).

Effet d'une fléchette sur un soldat (cible qu'on peut saisir) :
- hors alerte : il s'effondre et dort pour de bon (zzz), sans perdre de vie ;
- en alerte ou en recherche (évasion) : le 1er tir le secoue, il s'endort 8 s plus tard,
  ou tout de suite au 2e tir.
Sur les autres cibles (boss, caméras...) : mêmes dégâts que l'arme d'origine.

Le code ajouté va dans le menu de débogage de l'EXE (écrans mem/pow/ply/obj/tex et
menu_viewer_act, jamais appelés : 0x800447e4-0x80045c08). Le sommeil sans réveil et les zzz
demandent aussi de retoucher le code des soldats dans chaque overlay de STAGE.DIR.
Toutes les retouches vérifient les octets d'origine (motifs) avant d'écrire.

  python m9.py image.bin [image2.bin ...]     patch en place (images VOSTFR ou FR d'origine)
"""

import hashlib, struct, sys

import mips, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000  # adresse de chargement de l'EXE (en-tête PS-X EXE de 0x800 octets)
CAVE, CAVE_END = 0x800447E4, 0x80045C08
OVB = 0x800C47D8   # adresse de chargement des overlays de stage

SYM = dict(
    MODES=0x800B6426,        # linkvar 83 : bit 0 = M9, bit 1 = PSG1-T
    GM_Weapon=0x800B639C,
    GM_AlertMode=0x800ACFE8,
    GV_NewActor=0x800151C8, GV_SetNamedActor=0x80015234, GV_DestroyActor=0x800152B4,
    GV_StrCode=0x80016E4C, GM_InitObjectNoRots=0x800357E4, GM_SeSet2=0x8003370C,
    NewAnime=0x800609BC, DG_GetTexture=0x8001DCE0,
    STR_SOCOM2=0x800ACE28,   # "socom2"
    GET_RPK_NEXT=0x8003EF50, GET_RPK_SOCOM=0x8003EF38, ITEMS_SOCOM2=0x800BEE74,
    INIT_SPRT=0x8003E0F0, GET_RPK=0x8003EF30, NAVIGATE=0x8003E714,
    SOCOM_RES_DONE=0x80066AE0, POWER_NEXT=0x8002E420,
    M9CODE=0x19,             # a_mode des fléchettes (inutilisé par le jeu)
    M9FAINT=-32000,          # faint d'un soldat endormi par fléchette
    MARK=0x4D39AAAA,         # marques dans TARGET.field_18 (inutilisé par les soldats) :
    SLEEP=0x4D395A5A,        #   « secoué » (minuteur en cours) et « endormi »
    TREMBLE=8 * 25,          # 8 s (logique du jeu PAL : 25 images/s)
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
    bne a0, t0, it_no
    li v0, 2
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
    li t0, 2
    la s7, name_m9
    bne v0, t0, cave_name_go
    nop
    la s7, name_psg1t
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

# ---- menu : Triangle sur SOCOM ou PSG1 -> bascule du mode ----------------
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
    bne t4, t5, cave_nav_go
    li t0, 2
cave_nav_toggle:
    lui t1, %hi(MODES)
    lhu t2, %lo(MODES)(t1)
    nop
    xor t2, t2, t0
    sh t2, %lo(MODES)(t1)
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
    bne t0, t1, cave_pickup_ret
    nop
    la t2, str_get_psg1t
cave_pickup_set:
    move v1, t2
    sw v1, 0x118(s1)
cave_pickup_ret:
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
    bne t0, t1, cave_power_orig
    lhu t0, 0(s3)
    nop
    andi t0, t0, 2              # TARGET_CAPTURE : soldat
    bnez t0, cave_power_soldier
    li t1, 1
    sh t1, 0x3E(s2)             # autre cible : balle normale
cave_power_orig:
    lhu v0, -0x26(s0)           # instructions remplacées
    lh v1, -8(s0)
    jr ra
    nop
cave_power_soldier:
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
cave_wake:                      # t8 = décalage de la cible dans le soldat
    addu t0, s0, t8
    lw t0, 0(t0)
    li t1, SLEEP
    lw t0, 0x18(t0)
    nop
    bne t0, t1, cave_wake_ret
    andi t0, s1, 63
    li t1, 1
    bne t0, t1, cave_wake_sleep
    nop
    addiu sp, sp, -0x30
    sw ra, 0x28(sp)
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
    addiu sp, sp, 0x30
cave_wake_sleep:
    move v0, s1                 # jamais de réveil
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

# ---- données ---------------------------------------------------------------
name_m9:
    .word str_m9, 2
name_psg1t:
    .word str_psg1t, 4
str_m9:
    .asciiz "M9"
str_psg1t:
    .asciiz "PSG1-T"
str_get_m9:
    .asciiz "SOCOM + M9"
str_get_psg1t:
    .asciiz "PSG1 + PSG1-T"
timer_name:
    .asciiz "m9.c"
.align 2
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
]


# en-tête de l'ANIMATION des zzz (AN_Sleep) dans les overlays
ZZZ_HDR = struct.pack("<10H", 0xF7BB, 1, 1, 1, 1, 0, 1, 2, 2, 0)


def zzz_script(stage):
    """Script d'animation des zzz (AN_Sleep), recopié d'un overlay de STAGE.DIR."""
    hdr = ZZZ_HDR
    for name, ovl, _ in overlays(stage):
        k = ovl.find(hdr)
        while k >= 0:
            p = struct.unpack_from("<I", ovl, k + 0x18)[0] - OVB
            if 0 <= p < len(ovl):
                end = p
                for _ in range(3):      # 3 sous-scripts, chacun finit par 0D 0F
                    end = ovl.find(b"\x0d\x0f", end) + 2
                if end > p:
                    return ovl[p:end]
            k = ovl.find(hdr, k + 1)
    raise SystemExit("script zzz introuvable dans STAGE.DIR")


CAVE_SHA1 = "c25c35d567e32e9ae9acd5088f88c6a7e9ebf33f"  # menu de débogage d'origine


def build_cave(stage, sites):
    """Assemble le code ajouté, avec un relais par variante de soldat (voir scan_overlay)."""
    stubs = []
    for t in sorted({s["target"] for ss in sites.values() for s in ss}):
        stubs += [f"wake_{t:x}:", "    j cave_wake", f"    li t8, {t}"]
    for x, t in sorted({(s["piyo"], s["target"]) for ss in sites.values() for s in ss if s["piyo"]}):
        stubs += [f"piyo_{x:x}_{t:x}:", f"    lui t9, %hi({x})", f"    addiu t9, t9, %lo({x})",
                  "    j cave_piyo", f"    li t8, {t}"]
    script = zzz_script(stage)
    src = "\n".join([CAVE_SRC + "    .byte " + ", ".join(str(b) for b in script), ".align 2"] + stubs) + "\n"
    code, sym = mips.assemble(src, CAVE, SYM)
    if CAVE + len(code) > CAVE_END:
        raise SystemExit(f"code M9 trop gros ({len(code)} octets)")
    return code, sym


def patch_exe(exe, code, sym):
    out = bytearray(exe)
    off = 0x800 + CAVE - LOAD
    if hashlib.sha1(exe[off:off + CAVE_END - CAVE]).hexdigest() != CAVE_SHA1:
        raise SystemExit("EXE inattendu (pas la version PAL France, ou déjà patché ?)")
    out[off:off + len(code)] = code
    for addr, orig, src in HOOKS:
        new, _ = mips.assemble(src, addr, sym)
        o = 0x800 + addr - LOAD
        if bytes(out[o:o + len(new)]) != bytes.fromhex(orig):
            raise SystemExit(f"EXE inattendu à {addr:08x} (pas la version PAL France ?)")
        out[o:o + len(new)] = new
    return bytes(out)


def is_patched_exe(exe):
    addr, orig, _ = HOOKS[0]
    o = 0x800 + addr - LOAD
    return exe[o:o + 4] != bytes.fromhex(orig)


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


def is_piyo(w, addr):
    """Vrai si la fonction à addr est AN_Piyopiyo (animation de texture GV_StrCode 0xCAFE)."""
    i = (addr - OVB) // 4
    if not 0 <= i < len(w):
        return False  # fonction de l'EXE
    for k in range(i, min(i + 40, len(w) - 1)):
        if w[k] >> 16 == 0x3C10 and w[k + 1] >> 16 == 0x2610:  # lui s0 / addiu s0 : ANIMATION
            p = ((w[k] & 0xFFFF) << 16) + ((w[k + 1] & 0xFFFF) ^ 0x8000) - 0x8000 - OVB
            return 0 <= p < 4 * len(w) and w[p // 4] & 0xFFFF == 0xCAFE
    return False


def scan_overlay(ovl):
    """Repère chaque mode « soldat au sol » : test de réveil, appel des étoiles, décalages."""
    w = words(ovl)
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
        piyo = [k for k in body if jal_target(w[k]) and is_piyo(w, jal_target(w[k]))]
        sites.append(dict(wake=i, delay=w[i] & 0xFFFF, target=w[i + 5] & 0xFFFF,
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


def patch_overlay(ovl, sites, sym):
    out = bytearray(ovl)

    def put(k, src):
        new, _ = mips.assemble(src, OVB + 4 * k, sym)
        out[4 * k:4 * k + len(new)] = new

    for s in sites:
        put(s["wake"], f"jal wake_{s['target']:x}\nlh v0, {s['delay']}(s0)")
        if s["piyo"]:
            put(s["piyo_at"], f"jal piyo_{s['piyo']:x}_{s['target']:x}")
    k = old_switch(ovl)
    if k is not None:  # coup 9 (fléchette) -> traité comme le coup 3 (K.O. au poing)
        default = 0x80000000 | (words(ovl)[k] & 0x3FFFFFF) << 2
        put(k, f"addiu v0, v0, 5\nbne a3, v0, {default}")
    return bytes(out)


def patch_files(exe, stage):
    """EXE et STAGE.DIR d'un disque -> versions patchées (ou None si déjà patché)."""
    if is_patched_exe(exe):
        return None
    sites = {name: scan_overlay(ovl) for name, ovl, _ in overlays(stage)}
    sites = {k: v for k, v in sites.items() if v}
    code, sym = build_cave(stage, sites)
    new_exe = patch_exe(exe, code, sym)
    out = bytearray(stage)
    for name, ovl, pos in overlays(stage):
        if name in sites:
            out[pos:pos + len(ovl)] = patch_overlay(ovl, sites[name], sym)
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
