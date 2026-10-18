#!/usr/bin/env python3
"""
freeze.py - Patch optionnel : braquer un garde de dos (« Freeze ! », comme dans MGS2).

Snake vise (Carré tenu) avec le SOCOM, le M9 ou le FAMAS un garde qui lui tourne le dos, de près
et sans alerte : le garde se fige, les bras devant la tête (animation « se protège les yeux »
du jeu, il n'y a pas de « mains en l'air » dans MGS1). Il reste figé 5 s, quoi que fasse Snake :
s'il n'a été ni assommé ni endormi entre-temps, il donne l'alerte. S'il est touché
pendant le braquage (balle, fléchette, coup, prise), le jeu reprend la main comme d'habitude.

Gardes concernés : le code watcher.c (la plupart des zones). Les variantes zako*.c (disque 2 et
quelques zones) ne sont pas encore gérées.

Retouches :
- EXE : code ajouté dans deux plages de chaînes de printf (printf ne fait rien dans la version
  commerciale, ces chaînes ne servent à rien) ; octets d'origine vérifiés.
- STAGE.DIR : dans WatcherAct de chaque overlay à gardes watcher, l'appel à EnemyActionMain
  (perception, réflexion, mode courant) passe par frz_main, qui le saute pendant le braquage.
  EnemyActionMain est toujours 24140 octets après l'appel (même code dans tous les overlays) :
  frz_main le retrouve depuis son adresse de retour.

Garde (WatcherWork, décomp FoxdieTeam/mgs_reversing source/enemy) : control +0x20 (mov +0,
step +0x44), body (OBJECT) +0x9c (DG_OBJS : matrice du monde, colonne 2 = avant), target +0x900
(marque +0x18, comme m9.py : FROZEN pendant le braquage), pad.sound +0xb4a, alert_level +0xb98.

  python freeze.py image.bin [image2.bin ...]     patch en place (FR ou UK, VOSTFR comprise)
"""

import hashlib, struct, sys

import mips, pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
# Plages de chaînes de printf (mortes) : adresse par version, taille, SHA-1 d'origine (identique FR / UK)
ZONES = {
    "FR": [(0x80013BC0, 440, "242a5ad27b090099a4a28ed8d47a7da4d2cf30e0"),
           (0x80013E9C, 320, "7f18c0d2112ae6caa65969149658837d67160e05")],
    "UK": [(0x80013924, 440, "242a5ad27b090099a4a28ed8d47a7da4d2cf30e0"),
           (0x80013C00, 320, "7f18c0d2112ae6caa65969149658837d67160e05")],
}
EAM_OFF = 24140          # EnemyActionMain - appel (watcher.c, tous les overlays)
ANIM_FREEZE = 39         # ActTable[ACTION32] (« se protège les yeux ») des overlays watcher

SYM = dict(
    PLAYER_STATUS=0x800AD038,   # GM_PlayerStatus (0x800 = PLAYER_ATTACK : Snake vise)
    ALERT=0x800ACFE8,           # GM_AlertMode
    PPOS=0x800ACFF8,            # GM_PlayerPosition (SVECTOR)
    PCTRL=0x800ACFDC,           # GM_PlayerControl (CONTROL de Snake = travail + 0x20)
    WEAPON=0x800B639C,          # GM_Weapon
    CFG_ACTION=0x80035B10,      # GM_ConfigObjectAction(objet, animation, image, interpolation)
    FROZEN=0x4D39F000,          # marque de la cible (+0x18) pendant le braquage (+ images écoulées)
    FREEZE_T=5 * 25,            # 5 s (logique PAL : 25 images/s), puis alerte
    R2_START=1800 * 1800,       # distance de braquage (au carré)
    ANIM=ANIM_FREEZE,
    EAM=EAM_OFF - 8,
)


def mul(a, b, dst):
    """Produit 32 bits (mult / mflo) suivi des 2 instructions de garde du R3000."""
    return [f"    mult {a}, {b}", f"    mflo {dst}", "    nop", "    nop"]


# zone 2 : frz_main (appelé à la place de EnemyActionMain, a0 = garde, ra = appel + 8)
SRC1 = "\n".join([
    "frz_main:",
    "    addiu t9, ra, EAM           # EnemyActionMain",
    "    lw t0, 0x900(a0)            # cible du garde",
    "    nop",
    "    lw t1, 0x18(t0)",
    "    li t2, FROZEN",
    "    srl t3, t1, 12",
    "    srl t4, t2, 12",
    "    beq t3, t4, frz_held        # FROZEN + compteur (12 bits bas)",
    "    nop",
    "    bnez t1, frz_go             # autre marque (endormi par le M9...) : comme d'habitude",
    "    lui t3, %hi(ALERT)",
    "    lw t3, %lo(ALERT)(t3)",
    "    nop",
    "    bnez t3, frz_go             # alerte ou recherche : pas de braquage",
    "    nop",
    "    addiu sp, sp, -24",
    "    sw ra, 16(sp)",
    "    sw a0, 20(sp)",
    "    li a1, R2_START",
    "    jal frz_cond",
    "    li a2, 1                    # de dos, et Snake le vise",
    "    lw a0, 20(sp)",
    "    lw ra, 16(sp)",
    "    beqz v0, frz_go",
    "    addiu sp, sp, 24",
    "    lw t0, 0x900(a0)            # braquage : marque, arrêt, animation",
    "    li t2, FROZEN",
    "    sw t2, 0x18(t0)",
    "    sh zero, 0x64(a0)           # control.step.vx / vz",
    "    sh zero, 0x68(a0)",
    "    addiu sp, sp, -24",
    "    sw ra, 16(sp)",
    "    addiu a0, a0, 0x9C          # body",
    "    li a1, ANIM",
    "    move a2, zero",
    "    jal CFG_ACTION",
    "    li a3, 4",
    "    lw ra, 16(sp)",
    "    nop",
    "    jr ra                       # EnemyActionMain sauté cette image",
    "    addiu sp, sp, 24",
    "frz_held:                      # braquage en cours : t1 = FROZEN + images écoulées",
    "    lhu t3, 6(t0)",
    "    lh t4, 0x42(t0)             # captured",
    "    andi t3, t3, 4              # touché",
    "    or t3, t3, t4",
    "    bnez t3, frz_free           # touché ou attrapé : le jeu reprend la main",
    "    andi t5, t1, 0xFFF",
    "    slti t6, t5, FREEZE_T",
    "    beqz t6, frz_alert          # 5 s sans être assommé ni endormi : alerte",
    "    addiu t1, t1, 1",
    "    sw t1, 0x18(t0)",
    "    sh zero, 0x64(a0)           # reste figé (control.step)",
    "    jr ra",
    "    sh zero, 0x68(a0)",
    "frz_alert:                     # 5 s écoulées : alerte",
    "    li t3, 255",
    "    sw t3, 0xB98(a0)            # alert_level",
    "    li t3, 240",
    "    sh t3, 0xB4A(a0)            # pad.sound : cri",
    "frz_free:",
    "    sw zero, 0x18(t0)",
    "frz_go:",
    "    jr t9                       # EnemyActionMain, retour direct dans WatcherAct",
    "    nop",
])

# zone 1 : frz_cond(a0 = garde, a1 = distance² max, a2 = 1 : de dos et visé) -> v0
SRC2 = "\n".join([
    "frz_cond:",
    "    lui t3, %hi(PLAYER_STATUS)",
    "    lw t3, %lo(PLAYER_STATUS)(t3)",
    "    lui t4, %hi(WEAPON)",
    "    lh t4, %lo(WEAPON)(t4)",
    "    andi t3, t3, 0x800          # Snake vise",
    "    beqz t3, cond_no",
    "    sltiu t4, t4, 2             # SOCOM / M9 (0) ou FAMAS (1)",
    "    beqz t4, cond_no",
    "    lui t5, %hi(PPOS)",
    "    lh t6, %lo(PPOS)(t5)",
    "    lh t7, %lo(PPOS)+4(t5)",
    "    lh t3, 0x20(a0)",
    "    lh t4, 0x24(a0)",
    "    subu t6, t6, t3             # d = Snake - garde (x, z)",
    "    subu t7, t7, t4",
] + mul("t6", "t6", "t3") + mul("t7", "t7", "t4") + [
    "    addu t3, t3, t4             # distance²",
    "    slt t4, t3, a1",
    "    beqz t4, cond_no",
    "    nop",
    "    beqz a2, cond_yes",
    "    lw t4, 0x9C(a0)             # DG_OBJS du garde",
    "    nop",
    "    lh t5, 4(t4)                # avant du garde (colonne 2) : x",
    "    lh t8, 16(t4)               # z",
] + mul("t5", "t6", "t5") + mul("t8", "t7", "t8") + [
    "    addu t5, t5, t8",
    "    sra t5, t5, 12              # d projeté sur l'avant du garde",
    "    bgez t5, cond_no            # Snake devant lui",
    "    nop",
] + mul("t5", "t5", "t5") + [
    "    sll t5, t5, 2",
    "    slt t5, t3, t5              # dans les 60° derrière lui",
    "    beqz t5, cond_no",
    "    lui t4, %hi(PCTRL)",
    "    lw t4, %lo(PCTRL)(t4)",
    "    nop",
    "    lw t4, 0x7C(t4)             # DG_OBJS de Snake (travail + 0x9c = control + 0x7c)",
    "    nop",
    "    lh t5, 4(t4)",
    "    lh t8, 16(t4)",
] + mul("t5", "t6", "t5") + mul("t8", "t7", "t8") + [
    "    addu t5, t5, t8",
    "    sra t5, t5, 12              # d projeté sur l'avant de Snake (le garde est en -d)",
    "    bgtz t5, cond_no",
    "    nop",
] + mul("t5", "t5", "t5") + [
    "    sll t8, t5, 2               # 4 proj²",
    "    sll t5, t3, 1",
    "    addu t5, t5, t3             # 3 distance²",
    "    slt t5, t5, t8              # Snake vise le garde (à 30° près)",
    "    beqz t5, cond_no",
    "    nop",
    "cond_yes:",
    "    jr ra",
    "    li v0, 1",
    "cond_no:",
    "    jr ra",
    "    move v0, zero",
])


def watcher_hooks(ovl, ovb):
    """Appels à EnemyActionMain dans WatcherAct (« addiu a1, sX, 0x888 » = délai de
    DG_GetLightMatrix2, puis « jal EAM ; move a0, sX »), cible à EAM_OFF octets."""
    w = struct.unpack(f"<{len(ovl) // 4}I", ovl[:len(ovl) // 4 * 4])
    out = []
    for i in range(len(w) - 2):
        x = w[i]
        if x >> 26 == 9 and (x >> 16) & 31 == 5 and x & 0xFFFF == 0x888:
            rs = (x >> 21) & 31
            if w[i + 1] >> 26 == 3 and w[i + 2] == (rs << 21 | 4 << 11 | 0x21):
                eam = 0x80000000 | (w[i + 1] & 0x3FFFFFF) << 2
                if eam - (ovb + 4 * (i + 1)) == EAM_OFF:
                    out.append(i + 1)
    return out


def act_table_anim(ovl, ovb, cfg):
    """ActTable[32] de l'overlay (SetAction(work, 0, ...) : « sh zero, 0x8e0(sX) ; lui a1 ;
    lh a1, ActTable(a1) ; jal GM_ConfigObjectAction »)."""
    w = struct.unpack(f"<{len(ovl) // 4}I", ovl[:len(ovl) // 4 * 4])
    jal = 3 << 26 | (cfg >> 2) & 0x3FFFFFF
    for i in range(3, len(w)):
        if (w[i] == jal and w[i - 3] >> 26 == 0x29 and w[i - 3] & 0xFFFF == 0x8E0
                and w[i - 2] >> 16 == 0x3C05 and w[i - 1] >> 16 == 0x84A5):
            base = ((w[i - 2] & 0xFFFF) << 16) + ((w[i - 1] & 0xFFFF) ^ 0x8000) - 0x8000
            return struct.unpack_from("<h", ovl, base - ovb + 64)[0]
    return None


def overlays(stage):
    n = struct.unpack_from("<I", stage, 0)[0]
    for i in range(n // 12):
        name = stage[4 + 12 * i:12 + 12 * i].rstrip(bytes(1)).decode("latin1")
        sec = struct.unpack_from("<I", stage, 12 + 12 * i)[0]
        _, mode, ext, size = struct.unpack_from("<HBBi", stage, sec * 2048 + 4)
        if chr(mode) == "s" and chr(ext) == "b" and size > 0:
            pos = (sec + 1) * 2048
            yield name, stage[pos:pos + size], pos


def build(v):
    sym = pal.syms(v, SYM)
    (a1, n1, _), (a2, n2, _) = ZONES[v]
    cond, sym = mips.assemble(SRC2, a1, sym)      # frz_cond : zone 1 (440 octets)
    main, sym = mips.assemble(SRC1, a2, sym)      # frz_main : zone 2 (320 octets)
    assert len(cond) <= n1 and len(main) <= n2, (len(cond), len(main))
    return [(a1, cond), (a2, main)], sym


def patch_files(exe, stage):
    """EXE et STAGE.DIR d'un disque -> versions patchées, liste des stages (None si déjà fait)."""
    v = pal.version(exe)
    out = bytearray(exe)
    zones, sym = build(v)
    for (a, n, sha), (_, code) in zip(ZONES[v], zones):
        o = 0x800 + a - LOAD
        cur = bytes(out[o:o + n])
        if cur[:len(code)] == code:
            return None
        if hashlib.sha1(cur).hexdigest() != sha:
            raise SystemExit(f"EXE inattendu à {a:08x} ({v}) : chaînes de printf déjà utilisées ?")
        out[o:o + len(code)] = code
    ovb = pal.ovb(v)
    cfg = pal.addr(v, SYM["CFG_ACTION"])
    st = bytearray(stage)
    done = []
    for name, ovl, pos in overlays(stage):
        hooks = watcher_hooks(ovl, ovb)
        if not hooks:
            continue
        anim = act_table_anim(ovl, ovb, cfg)
        if anim != ANIM_FREEZE:
            raise SystemExit(f"{name} : ActTable[32] = {anim} (attendu {ANIM_FREEZE})")
        for k in hooks:
            new, _ = mips.assemble("jal frz_main", ovb + 4 * k, sym)
            st[pos + 4 * k:pos + 4 * k + 4] = new
        done.append(name)
    return bytes(out), bytes(st), done


def patch_image(path):
    disc = psxiso.Disc(path)
    files = disc.files()
    name = next(p for p in files if p in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
    exe = disc.read(*files[name])
    stage = disc.read(*files["MGS/STAGE.DIR"])
    disc.f.close()
    res = patch_files(exe, stage)
    if res is None:
        return name, None
    new_exe, new_stage, done = res
    write_file_inplace(path, files[name][0], new_exe)
    write_file_inplace(path, files["MGS/STAGE.DIR"][0], new_stage)
    return name, done


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        name, done = patch_image(p)
        print(f"{p} : " + ("déjà patché" if done is None else
                            f"{name} patché (Freeze), gardes watcher dans {len(done)} stages"))


if __name__ == "__main__":
    main()
