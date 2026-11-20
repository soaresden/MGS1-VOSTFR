#!/usr/bin/env python3
"""
objets.py - Mod de test : tous les objets (menu L2), rations et médicaments toujours pleins.

Le pendant de armes.py. À chaque image où Snake existe, son Act passe par un petit code qui, pour les
24 objets (GM_Items 0x800b63ca, version française, traduite par pal.py ; -1 = pas encore trouvé),
donne l'objet s'il n'est pas encore trouvé :
  - 1 pour un objet simple (cartons, lunettes, masque, gilet, tenue furtive, bandana, clé PAL...) ;
  - la carte au niveau 7 (toutes les portes), 5 rations, 3 médicaments contre le rhume, 3 diazépam :
    remis à ces valeurs à chaque image (une carte ramassée ne la fait pas redescendre ; illimités).
Pas de table des maximums des objets après GM_Items (contrairement aux armes : GM_WeaponsMax).
Jamais donnés : la bombe à retardement (elle exploserait sur Snake), l'appareil photo (pas dans
cette version) et le silencieux : tant que GM_Items[silencieux] > 0, l'Act du SOCOM (et du M9) ne
fait que lever GM_SilencerFlag et sort (US 0x80067844) : le jeu le remet à zéro en le fixant ;
redonné à chaque image, il empêchait de tirer. On le ramasse normalement (le M9 est silencieux). Un objet repris par le jeu (capture : valeur négative autre que -1) n'est pas touché.

Code : juste après celui de armes.py, dans la même fonction de débogage jamais appelée
(0x800852d0 + 0xB0, 0xB0 octets). Crochet : les instructions 3 et 4 de l'Act de Snake (Act + 8,
« move s1, a0 ; lui a1, 4 ») ; armes.py prend les deux premières et revient en Act + 8 : les deux
mods marchent seuls ou ensemble.

  python objets.py image.bin [image2.bin ...]     patch en place (FR, UK ou US d'origine)
"""

import hashlib, sys

import mips, pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
CAVE, CAVE_END = 0x800852D0 + 0xB0, 0x800852D0 + 0x160
CAVE_SHA1 = {"FR": "ee7d67bd53bf808917b1a09b1fc19f332d0b53bd",
             "UK": "e221e0cc4e309796bdc5ac22454d4928152639f4",
             "US": "1c38409ab0268d3e350f8ad8aa2470761ba03fe6"}
SNA_ACT = 0x8005BBA0      # Act de Snake (version française)
SYM = dict(ITEMS=0x800B63CA, ACT16=SNA_ACT + 16)
# Valeur donnée (7 bits bas) ; 0x80 = remise à cette valeur à chaque image ; 0 = jamais donné.
# Cigarettes, jumelles, carton A, B, C, lunettes infrarouges, thermiques, masque à gaz, gilet,
# ketchup, tenue furtive, bandana, appareil photo, rations, médicament, diazépam, clé PAL, carte,
# bombe à retardement, détecteur de mines, disque, corde, mouchoir, silencieux
DEFAULTS = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0x85, 0x83, 0x83, 1, 0x87, 0, 1, 1, 1, 1, 0]
assert len(DEFAULTS) == 24

CAVE_SRC = r"""
objs:
    la t0, ITEMS
    la t3, objs_def
    li t1, 24
    li t4, -1
objs_loop:
    lbu t6, 0(t3)             # ce qu'on donne (0 : rien)
    lh t2, 0(t0)              # l'objet (-1 : pas trouvé)
    beqz t6, objs_next
    andi t7, t6, 0x7f
    beq t2, t4, objs_set      # pas trouvé : on le donne
    andi t8, t6, 0x80         # à garder plein ?
    bltz t2, objs_next        # repris par le jeu : on n'y touche pas
    nop
    beqz t8, objs_next
    nop
objs_set:
    sh t7, 0(t0)
objs_next:
    addiu t0, t0, 2
    addiu t1, t1, -1
    bnez t1, objs_loop
    addiu t3, t3, 1
    move s1, a0               # les deux instructions remplacées par le saut
    j ACT16
    lui a1, 4
objs_def:
""" + "".join(f"    .byte {n}\n" for n in DEFAULTS)

HOOK = (SNA_ACT + 8, "218880000400053c", "j objs\nnop")


def patch(exe):
    """EXE d'origine (FR, UK ou US, avec ou sans armes.py) -> EXE patché ; None s'il l'est déjà."""
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
        print(f"{p} : {patch_image(p)} patché (tous les objets)")


if __name__ == "__main__":
    main()
