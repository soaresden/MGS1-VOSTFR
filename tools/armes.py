#!/usr/bin/env python3
"""
armes.py - Mod de test : toutes les armes dès le début, munitions au maximum (une fois).

Pour essayer les armes (et les mods qui les touchent : M9, PSG1-T, claymores zzz, vue subjective) sans
jouer jusqu'à elles. À chaque image où Snake existe, son Act d'origine (0x8005bba0, adresses de la
version française, traduites par pal.py) passe d'abord par un petit code qui, pour les 10 armes
(GM_Weapons 0x800b63a2, munitions ; -1 = pas encore trouvée ; bit 0x8000 = confisquée), donne une fois
l'arme pas encore trouvée, munitions au maximum (GM_WeaponsMax, 20 octets plus loin ; s'il vaut 0, une
valeur par défaut, qui devient aussi le maximum). Ensuite le jeu compte normalement : munitions pas
illimitées (demande de Denis, 2026-11-20). Une arme confisquée (capture, bit 0x8000) n'est pas touchée.

Code ajouté dans une fonction de débogage jamais appelée (0x800852d0, écrit « SG » + 6 chiffres
hexadécimaux ; ni appel, ni pointeur dans l'EXE, ni dans STAGE.DIR des deux disques US) ; on n'en prend
que 0xB0 octets. Le crochet remplace les deux premières instructions de l'Act de Snake par un saut.

  python armes.py image.bin [image2.bin ...]     patch en place (FR, UK ou US d'origine)
"""

import hashlib, sys

import mips, pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
CAVE, CAVE_END = 0x800852D0, 0x800852D0 + 0xB0
CAVE_SHA1 = {"FR": "08bdffb11d17e03409709c3e293438d933c2fc9e",
             "UK": "ae89384830e837ea21cfb8a60221a00e246fe5c7",
             "US": "429c711951d03fa1187b5ec928105f2b9b09ed66"}
SNA_ACT = 0x8005BBA0      # Act de Snake
SYM = dict(WEAPONS=0x800B63A2, ACT8=SNA_ACT + 8)
# SOCOM, FA-MAS, grenades, Nikita, Stinger, claymores, C4, grenades paralysantes, grenades chaff, PSG1
DEFAULTS = [25, 60, 8, 10, 10, 8, 8, 8, 8, 20]

CAVE_SRC = r"""
allw:
    la t0, WEAPONS
    la t3, allw_def
    li t1, 10
    li t4, -1
allw_loop:
    lh t2, 0(t0)              # munitions (-1 : pas trouvée)
    lh t5, 0x14(t0)           # maximum
    bne t2, t4, allw_next     # déjà là (ou confisquée) : on n'y touche plus
    nop
    lh t6, 0(t3)              # valeur par défaut
    bgtz t5, allw_set
    move t2, t5
    move t2, t6               # pas de maximum : la valeur par défaut, qui le devient
    sh t6, 0x14(t0)
allw_set:
    sh t2, 0(t0)
allw_next:
    addiu t0, t0, 2
    addiu t1, t1, -1
    bnez t1, allw_loop
    addiu t3, t3, 2
    addiu sp, sp, -0x38       # les deux instructions remplacées par le saut
    j ACT8
    sw s1, 0x2c(sp)
allw_def:
""" + "".join(f"    .half {n}\n" for n in DEFAULTS)

HOOK = (SNA_ACT, "c8ffbd272c00b1af", "j allw\nnop")


def patch(exe):
    """EXE d'origine (FR, UK ou US) -> EXE patché ; None s'il l'est déjà."""
    v = pal.version(exe)
    addr, orig, src = HOOK
    a = pal.addr(v, addr)
    o = 0x800 + a - LOAD
    cave = pal.addr(v, CAVE)
    code, sym = mips.assemble(CAVE_SRC, cave, pal.syms(v, SYM))
    if len(code) > CAVE_END - CAVE:
        raise SystemExit(f"code trop gros ({len(code)} octets)")
    co = 0x800 + cave - LOAD
    if exe[co:co + len(code)] == code:
        return None
    hook, _ = mips.assemble(src, a, sym)
    if not pal.same(v, exe[o:o + 8], orig):
        raise SystemExit(f"EXE inattendu à {a:08x} ({v}) : Act de Snake déjà modifié ?")
    zone = exe[co:co + CAVE_END - CAVE]
    if hashlib.sha1(zone).hexdigest() != CAVE_SHA1[v]:
        raise SystemExit(f"EXE inattendu à {cave:08x} ({v}) : fonction inutilisée déjà modifiée ?")
    out = bytearray(exe)
    out[co:co + len(code)] = code
    out[o:o + len(hook)] = hook
    return bytes(out)


def patch_image(path):
    disc = psxiso.Disc(path)
    files = disc.files()
    name = next(p for p in files if p in ("MGS/MGS1.EXE", "MGS/MGS2.EXE") or p.startswith(("SLUS_", "SLES_")))
    lba, size = files[name]
    exe = disc.read(lba, size)
    disc.f.close()
    new = patch(exe)
    if new:
        write_file_inplace(path, lba, new)
    return name


def main():
    for p in sys.argv[1:]:
        print(f"{p} : {patch_image(p)} patché (toutes les armes)")


if __name__ == "__main__":
    main()
