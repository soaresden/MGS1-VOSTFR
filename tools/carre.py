#!/usr/bin/env python3
"""
carre.py - Patch optionnel : Carré fait défiler les dialogues du Codec (comme dans MGS2).

Dans le jeu d'origine, X pendant un appel coupe la voix ; il faut ensuite appuyer pour
chaque réplique. Avec ce patch, Carré coupe la voix lui aussi, puis toutes les répliques
restantes de l'appel défilent seules (comme si on martelait le bouton). Les questions
(sauvegarde, choix oui/non) ne sont pas touchées.

Modifie seulement l'exécutable (MGS1.EXE / MGS2.EXE, identiques ; PAL France ou PAL Europe
anglaise, adresses traduites par pal.py), en place,
dans la boucle Codec (menu/radio.c de la décompilation) :
- état 5 « appel en cours » : la coupure de voix réagit aussi à Carré enfoncé ;
- état 4 « attente d'une touche » : Carré enfoncé pose un drapeau (bits 0x8000 = défilement,
  0x100 = voix coupée pour la suite) dans les drapeaux de l'appel ; tant qu'il est posé,
  chaque réplique passe aussitôt. Le drapeau disparaît avec l'appel ;
- état 7 « fin d'appel » : un appel passé au Carré referme le Codec (retour au jeu), même
  s'il a été décroché par le joueur (sinon le jeu reste sur l'écran des fréquences, qu'on
  quitte d'habitude sans s'en rendre compte en martelant X). Petit code ajouté à la fin du
  menu de débogage inutilisé (0x80045900-0x80045a08, voir m9.py).

  python carre.py image.bin [image2.bin ...]     patch en place (VOSTFR, FR ou UK d'origine)
"""

import struct, sys

import mips, pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000  # adresse de chargement, en-tête PS-X EXE de 0x800 octets

R = dict(zero=0, v0=2, v1=3, a0=4, a1=5, a2=6, t0=8, s0=16, s1=17, s2=18, s3=19, s4=20)


def i_type(op, rs, rt, imm):
    return op << 26 | R[rs] << 21 | R[rt] << 16 | imm & 0xFFFF


def r_type(funct, rs="zero", rt="zero", rd="zero", sa=0):
    return R[rs] << 21 | R[rt] << 16 | R[rd] << 11 | sa << 6 | funct


def lw(rt, off, rs): return i_type(0x23, rs, rt, off)
def lh(rt, off, rs): return i_type(0x21, rs, rt, off)
def lhu(rt, off, rs): return i_type(0x25, rs, rt, off)
def sh(rt, off, rs): return i_type(0x29, rs, rt, off)
def andi(rt, rs, imm): return i_type(0x0C, rs, rt, imm)
def addiu(rt, rs, imm): return i_type(0x09, rs, rt, imm)
def sll(rd, rt, sa): return r_type(0x00, rt=rt, rd=rd, sa=sa)
def srl(rd, rt, sa): return r_type(0x02, rt=rt, rd=rd, sa=sa)
def or_(rd, rs, rt): return r_type(0x25, rs, rt, rd)
def and_(rd, rs, rt): return r_type(0x24, rs, rt, rd)
def move(rd, rs): return r_type(0x21, rs, "zero", rd)
def jal(target): return 3 << 26 | (target >> 2) & 0x3FFFFFF
def j(target): return 2 << 26 | (target >> 2) & 0x3FFFFFF
NOP = 0


def branch(op, rs, pc, target):
    return i_type(op, rs, "zero", (target - pc - 4) >> 2)


def assemble(pc, prog):
    """prog : liste d'instructions ou de (op_branche, reg, cible)."""
    out = []
    for k, ins in enumerate(prog):
        if isinstance(ins, tuple):
            op, rs, target = ins
            ins = branch({"beqz": 4, "bnez": 5}[op], rs, pc + 4 * k, target)
        out.append(ins)
    return out


WAKE_TASK, CLEAR_TEXT, STATE_END = 0x80049420, 0x80042178, 0x800430DC

# État 4 (0x80042bc0-0x80042c2c, 28 instructions)
STATE4 = 0x80042BC0


def state4(v="FR"):
    A = lambda a: pal.addr(v, a)
    pc = A(STATE4)
    adv, deb = pc + 0x50, pc + 0x64
    return assemble(pc, [
        move("a0", "s3"), jal(A(0x800424BC)), move("a1", "s4"),   # trace le repère d'attente
        lw("v1", 0x218, "s3"),          # v1 = appel en cours
        lhu("s1", 0, "s0"),             # s1 = touches enfoncées
        lhu("v0", 0x18, "v1"),          # v0 = drapeaux de l'appel
        andi("a1", "s1", 0x80),         # Carré enfoncé ?
        sll("a1", "a1", 8),             # -> 0x8000 (défilement)
        srl("t0", "a1", 7),             # -> 0x100 (voix coupée)
        or_("a1", "a1", "t0"),
        or_("v0", "v0", "a1"),
        andi("a1", "v0", 0x8000),
        lh("s2", 0x212, "s3"),          # s2 = touches tenues à l'arrivée (anti-rebond)
        lhu("a2", 4, "s0"),             # a2 = touches relâchées
        ("bnez", "a1", adv),            # défilement : réplique suivante
        sh("v0", 0x18, "v1"),
        andi("a2", "a2", 0xF0F0),       # comportement d'origine : une touche relâchée...
        ("beqz", "a2", deb),
        NOP,
        ("bnez", "s2", deb),            # ... qui n'était pas déjà tenue
        addiu("v0", "zero", 3),         # adv :
        jal(A(WAKE_TASK)),
        sh("v0", 0x210, "s3"),          # état 3
        jal(A(CLEAR_TEXT)),
        move("a0", "s3"),
        and_("s2", "s2", "s1"),         # deb : anti-rebond
        j(A(STATE_END)),
        sh("s2", 0x212, "s3"),
    ])


# État 5 (0x80042d10-0x80042d34, 10 instructions) : coupure de la voix
STATE5 = 0x80042D10
SKIP = 0x80042D84


def state5(v="FR"):
    pc, skip = pal.addr(v, STATE5), pal.addr(v, SKIP)
    return assemble(pc, [
        lhu("v0", 0x18, "s1"),
        lhu("v1", 0, "s0"),             # touches enfoncées
        andi("v0", "v0", 1),            # appel impossible à couper ?
        ("bnez", "v0", skip),
        lhu("a1", 4, "s0"),             # touches relâchées
        andi("v1", "v1", 0x80),         # Carré enfoncé
        andi("a1", "a1", 0x40),         # ou X relâché (origine)
        or_("v0", "v1", "a1"),
        ("beqz", "v0", skip),
        NOP,
    ])


# Octets d'origine attendus (EXE PAL France), pour ne rien patcher à l'aveugle
ORIG = {
    STATE4: "21206002" "2f09010c" "21288002" "04000296" "00000000" "f0f04230" "0b004010"
            "00000000" "12026286" "00000000" "07004014" "00000000" "0825010c" "00000000"
            "5e08010c" "21206002" "03000224" "100262a6" "00000596" "12026286" "00000000"
            "2410a200" "03004014" "00000000" "370c0108" "120260a6" "370c0108" "120265a6",
    STATE5: "18002296" "00000000" "01004230" "19004014" "00000000" "04000296" "00000000"
            "40004230" "14004010" "00000000",
}


# État 7 : fin d'appel. Code ajouté (gp+0x828 = octet du menu de débogage, jamais lu)
CAVE, CAVE_END = 0x80045900, 0x80045A08
CAVE_SHA1 = "f5d7152a60d954f968ff8eda79668077764decc6"
END_CHECK = 0x8004A384   # menu_radio_end_check
CAVE_SRC = '''
# remplace l'appel à menu_radio_end_check : l'appel finissant a-t-il été sauté au Carré ?
end_check:
    lw t0, 0x218(s3)            # appel en cours
    nop
    lhu t0, 0x18(t0)
    nop
    andi t0, t0, 0x8000
    beqz t0, end_check_go
    li t1, 1
    sb t1, 0x828(gp)
end_check_go:
    j END_CHECK
    nop

# remplace « lhu v0, type de l'appel » au choix fermeture / écran des fréquences :
# appel sauté au Carré -> type 2 (comme un appel entrant) pour ce test seulement
call_type:
    lhu v0, 0x814(gp)
    lbu t0, 0x828(gp)
    nop
    beqz t0, call_type_ret
    nop
    sb zero, 0x828(gp)
    andi v0, v0, 0xFFF0
    ori v0, v0, 2
call_type_ret:
    jr ra
    nop
'''
HOOKS = [
    (0x80042EB8, "e128010c", "jal end_check"),
    (0x80042EE8, "14088297", "jal call_type"),   # le délai (li v1, 2) reste
]


def words(lst):
    return b"".join(struct.pack("<I", w) for w in lst)


def patch(exe):
    """EXE PAL France ou Europe -> EXE patché."""
    v = pal.version(exe)
    out = bytearray(exe)
    for addr, new in ((STATE4, state4(v)), (STATE5, state5(v))):
        a = pal.addr(v, addr)
        off = 0x800 + a - LOAD
        n = len(ORIG[addr]) // 2
        cur = bytes(out[off:off + n])
        if cur == words(new):
            continue  # déjà patché
        if not pal.same(v, cur, ORIG[addr]):
            raise SystemExit(f"EXE inattendu à {a:08x} ({v})")
        out[off:off + n] = words(new)
    # gp+0x828 et gp+0x814 : mêmes décalages dans les deux versions (pal.gp)
    assert pal.gp(v, 0x828) == 0x828 and pal.gp(v, 0x814) == 0x814
    cave = pal.addr(v, CAVE)
    code, sym = mips.assemble(CAVE_SRC, cave, {"END_CHECK": pal.addr(v, END_CHECK)})
    assert CAVE + len(code) <= CAVE_END
    off = 0x800 + cave - LOAD
    if bytes(out[off:off + len(code)]) != code:
        if not pal.cave_ok(v, exe, CAVE, CAVE_END, CAVE_SHA1):
            raise SystemExit(f"EXE inattendu à {cave:08x} ({v})")
        out[off:off + len(code)] = code
    for addr, orig, src in HOOKS:
        a = pal.addr(v, addr)
        new, _ = mips.assemble(src, a, sym)
        o = 0x800 + a - LOAD
        cur = bytes(out[o:o + len(new)])
        if cur == new:
            continue
        if not pal.same(v, cur, orig):
            raise SystemExit(f"EXE inattendu à {a:08x} ({v})")
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
    for p in sys.argv[1:]:
        print(f"{p} : {patch_image(p)} patché (Carré fait défiler le Codec)")


if __name__ == "__main__":
    main()
