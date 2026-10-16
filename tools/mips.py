#!/usr/bin/env python3
"""
mips.py - Petit assembleur MIPS R3000 (PS1) pour les patchs du dépôt.

  words = assemble(source, org, symbols)   -> liste de mots 32 bits (petit-boutiste à l'écriture)

Syntaxe : une instruction par ligne, « étiquette: », commentaires « # » ou « ; ».
Registres $v0 ou v0. Immédiats : expressions Python sur les symboles (+ %hi(x), %lo(x)).
Pseudo-instructions : nop, move, li (1 ou 2 mots selon la valeur, connue au 1er passage
seulement si c'est une constante), la (toujours lui+addiu), b, beqz, bnez, neg, not.
Directives : .word, .half, .byte, .ascii, .asciiz, .align n (puissance de 2).
Pas de réordonnancement : les délais de branchement et de chargement sont à la charge
de l'auteur, comme sur la vraie machine. Un chargement suivi d'une instruction qui lit le
registre chargé est refusé (sur PS1 et DuckStation elle verrait l'ancienne valeur ; PCSX-Redux
ne le reproduit pas), sauf dans le délai d'un saut sans condition.
"""

import re, struct

REGS = {n: i for i, n in enumerate(
    "zero at v0 v1 a0 a1 a2 a3 t0 t1 t2 t3 t4 t5 t6 t7 s0 s1 s2 s3 s4 s5 s6 s7 t8 t9 k0 k1 gp sp fp ra".split())}
REGS["s8"] = 30

R3 = {"addu": 0x21, "subu": 0x23, "and": 0x24, "or": 0x25, "xor": 0x26, "nor": 0x27,
      "slt": 0x2A, "sltu": 0x2B, "add": 0x20, "sub": 0x22}
SHIFT = {"sll": 0, "srl": 2, "sra": 3}
SHIFTV = {"sllv": 4, "srlv": 6, "srav": 7}
IMM = {"addiu": 9, "addi": 8, "slti": 10, "sltiu": 11, "andi": 12, "ori": 13, "xori": 14}
MEM = {"lb": 0x20, "lh": 0x21, "lw": 0x23, "lbu": 0x24, "lhu": 0x25, "sb": 0x28, "sh": 0x29, "sw": 0x2B}
BR2 = {"beq": 4, "bne": 5}
BR1 = {"blez": (6, 0), "bgtz": (7, 0), "bltz": (1, 0), "bgez": (1, 1)}
BRANCHY = set(BR1) | set(BR2) | {"beqz", "bnez", "b", "j", "jal", "jr", "jalr"}
LOADS = {"lb", "lh", "lw", "lbu", "lhu"}
JUMPS = {"j", "jal", "b", "jr", "jalr"}


def reads(word):
    """Registres lus par une instruction encodée (pour le délai de chargement)."""
    op, rs, rt = word >> 26, (word >> 21) & 31, (word >> 16) & 31
    if op == 0:
        f = word & 63
        r = {rt} if f in (0, 2, 3) else set() if f in (0x10, 0x12) else {rs} if f in (8, 9) else {rs, rt}
    elif op in (2, 3, 15):
        r = set()
    elif op in (4, 5) or 0x28 <= op <= 0x2E:
        r = {rs, rt}
    else:
        r = {rs}
    return r - {0}


def reg(s):
    s = s.strip().lstrip("$")
    if s not in REGS:
        raise ValueError(f"registre inconnu : {s}")
    return REGS[s]


def hi(x):
    return ((x + 0x8000) >> 16) & 0xFFFF


def lo(x):
    return x & 0xFFFF


class Asm:
    def __init__(self, org, symbols=None):
        self.org = org
        self.sym = dict(symbols or {})

    def val(self, expr, final):
        expr = expr.strip()
        env = dict(self.sym)
        env.update(hi=hi, lo=lo)
        expr = expr.replace("%hi(", "hi(").replace("%lo(", "lo(")
        try:
            return int(eval(expr, {"__builtins__": {}}, env))
        except NameError:
            if final:
                raise
            return 0

    def size(self, op, args):
        """Taille en octets d'une ligne (1er passage)."""
        if op == ".word":
            return 4 * len(args)
        if op == ".half":
            return 2 * len(args)
        if op == ".byte":
            return len(args)
        if op in (".ascii", ".asciiz"):
            return len(self.string(args)) + (op == ".asciiz")
        if op == "la":
            return 8
        if op == "li":
            try:
                v = self.val(args[1], True)
            except NameError:
                return 8
            return 4 if -0x8000 <= v < 0x10000 else 8
        return 4

    @staticmethod
    def string(args):
        s = ",".join(args).strip()
        return eval(s).encode("latin1")

    def parse(self, src):
        lines = []
        for raw in src.splitlines():
            line = re.split(r"[#;]", raw, 1)[0].strip()
            while True:
                m = re.match(r"^([A-Za-z_.][\w.]*):\s*(.*)$", line)
                if not m:
                    break
                lines.append(("label", m.group(1)))
                line = m.group(2)
            if not line:
                continue
            if line.startswith((".ascii", ".asciiz")):
                op, rest = line.split(None, 1)
                lines.append((op, [rest]))
                continue
            parts = line.split(None, 1)
            op = parts[0].lower()
            args = [a.strip() for a in split_args(parts[1])] if len(parts) > 1 else []
            lines.append((op, args))
        return lines

    def assemble(self, src):
        lines = self.parse(src)
        # 1er passage : étiquettes
        pc = self.org
        self.sizes = []
        for op, args in lines:
            if op == "label":
                self.sym[args] = pc
            elif op == ".align":
                n = 1 << self.val(args[0], True)
                pc = (pc + n - 1) & ~(n - 1)
            else:
                self.sizes.append(self.size(op, args))
                pc += self.sizes[-1]
        self.end = pc
        # 2e passage
        out = bytearray()
        pc = self.org
        sizes = iter(self.sizes)
        prev_branch = False
        load = None    # registre chargé par l'instruction précédente
        prev_op = None
        for op, args in lines:
            if op == "label":
                continue
            if op.startswith("."):
                load = None
            if op == ".align":
                n = 1 << self.val(args[0], True)
                while (self.org + len(out)) % n:
                    out.append(0)
                pc = self.org + len(out)
                continue
            self.cur = next(sizes)
            if prev_branch and self.cur != 4:
                raise ValueError(f"pseudo-instruction de 2 mots dans un délai : {op} {args}")
            prev_branch = op in BRANCHY
            b = self.encode(op, args, pc)
            if len(b) != self.cur:
                raise ValueError(f"taille changée entre les passes : {op} {args}")
            if load and not op.startswith(".") and load in reads(struct.unpack_from("<I", b)[0]):
                raise ValueError(f"délai de chargement : {op} {', '.join(args)} lit le registre "
                                 f"chargé juste avant (0x{pc:08x})")
            load = reg(args[0]) if op in LOADS and prev_op not in JUMPS else None
            prev_op = op
            out += b
            pc += len(b)
        return bytes(out)

    def encode(self, op, args, pc):
        v = lambda e: self.val(e, True)
        w = lambda *xs: b"".join(struct.pack("<I", x & 0xFFFFFFFF) for x in xs)
        if op == ".word":
            return w(*[v(a) for a in args])
        if op == ".half":
            return b"".join(struct.pack("<H", v(a) & 0xFFFF) for a in args)
        if op == ".byte":
            return bytes(v(a) & 0xFF for a in args)
        if op in (".ascii", ".asciiz"):
            return self.string(args) + (b"\0" if op == ".asciiz" else b"")
        if op == "nop":
            return w(0)
        if op == "move":
            return w(rtype(0x21, reg(args[1]), 0, reg(args[0])))
        if op == "neg":
            return w(rtype(0x23, 0, reg(args[1]), reg(args[0])))
        if op == "not":
            return w(rtype(0x27, reg(args[1]), 0, reg(args[0])))
        if op == "li":
            rt, x = reg(args[0]), v(args[1])
            if self.cur == 4:
                if -0x8000 <= x < 0x8000:
                    return w(itype(9, 0, rt, x))
                return w(itype(13, 0, rt, x))
            return w(itype(15, 0, rt, x >> 16), itype(13, rt, rt, x))
        if op == "la":
            rt, x = reg(args[0]), v(args[1])
            return w(itype(15, 0, rt, hi(x)), itype(9, rt, rt, lo(x)))
        if op == "lui":
            return w(itype(15, 0, reg(args[0]), v(args[1])))
        if op in R3:
            return w(rtype(R3[op], reg(args[1]), reg(args[2]), reg(args[0])))
        if op in SHIFT:
            return w(rtype(SHIFT[op], 0, reg(args[1]), reg(args[0]), v(args[2])))
        if op in SHIFTV:
            return w(rtype(SHIFTV[op], reg(args[2]), reg(args[1]), reg(args[0])))
        if op in ("mult", "multu", "div", "divu"):
            f = {"mult": 0x18, "multu": 0x19, "div": 0x1A, "divu": 0x1B}[op]
            return w(rtype(f, reg(args[0]), reg(args[1]), 0))
        if op in ("mfhi", "mflo"):
            return w(rtype(0x10 if op == "mfhi" else 0x12, 0, 0, reg(args[0])))
        if op == "jr":
            return w(rtype(8, reg(args[0]), 0, 0))
        if op == "jalr":
            rd = reg(args[1]) if len(args) > 1 else 31
            return w(rtype(9, reg(args[0]), 0, rd))
        if op in IMM:
            return w(itype(IMM[op], reg(args[1]), reg(args[0]), v(args[2])))
        if op in MEM:
            m = re.match(r"^(.*)\((.+)\)$", args[1])
            off = v(m.group(1)) if m.group(1).strip() else 0
            return w(itype(MEM[op], reg(m.group(2)), reg(args[0]), off))
        if op in ("j", "jal"):
            t = v(args[0])
            if (t ^ pc) & 0xF0000000:
                raise ValueError(f"saut hors segment : {args[0]}")
            return w((2 if op == "j" else 3) << 26 | (t >> 2) & 0x3FFFFFF)
        if op in BR2 or op in ("beqz", "bnez", "b"):
            if op == "b":
                rs, rt, tgt, code = 0, 0, args[0], 4
            elif op in ("beqz", "bnez"):
                rs, rt, tgt, code = reg(args[0]), 0, args[1], 4 if op == "beqz" else 5
            else:
                rs, rt, tgt, code = reg(args[0]), reg(args[1]), args[2], BR2[op]
            return w(itype(code, rs, rt, self.branch(pc, v(tgt))))
        if op in BR1:
            code, rt = BR1[op]
            return w(itype(code, reg(args[0]), rt, self.branch(pc, v(args[1]))))
        raise ValueError(f"instruction inconnue : {op} {args}")

    @staticmethod
    def branch(pc, target):
        d = (target - pc - 4) >> 2
        if not -0x8000 <= d < 0x8000:
            raise ValueError("branchement trop loin")
        return d


def split_args(s):
    out, depth, cur = [], 0, ""
    for c in s:
        if c == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        depth += c == "("
        depth -= c == ")"
        cur += c
    out.append(cur)
    return out


def rtype(funct, rs, rt, rd, sa=0):
    return rs << 21 | rt << 16 | rd << 11 | sa << 6 | funct


def itype(op, rs, rt, imm):
    return op << 26 | rs << 21 | rt << 16 | imm & 0xFFFF


def assemble(src, org, symbols=None):
    """Assemble src à l'adresse org ; renvoie (octets, table des symboles)."""
    a = Asm(org, symbols)
    code = a.assemble(src)
    return code, a.sym
