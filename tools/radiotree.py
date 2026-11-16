#!/usr/bin/env python3
"""
radiotree.py - Fragments de RADIO.DAT (Codec) en arbre, pour les réécrire avec des tailles justes.

Fragment (menu/radiomes.c) : u16 fréquence, u32 code FACE.DAT (secteur 24 bits | secteurs << 24),
u16 drapeaux, puis le script (un bloc), puis la police du fragment (font_set_font_addr(1, …)),
jusqu'au fragment suivant.

Bloc : [octet][u16 BE taille] commandes… 00 ; il occupe 1 + taille octets.
Commande : FF code [u16 BE taille, comptée] arguments.
  TALK 01 : 3 mots u16, texte\\0         VOICE 02 : code VOX u32, bloc
  IF 10 : valeur, bloc, puis (FF 12 valeur bloc)* (FF 11 bloc)? 00
  SWITCH 20 : valeur, (21 mot bloc)* (22 bloc)? 00      RANDSWITCH 30 : mot, (31 mot bloc)* 00
  autres (ANIM, ADD_CONTACT, MEMSAVE, SOUND, PROMPT, VARSAVE, EVAL) : arguments bruts.
Les valeurs suivent GCL (comme gcx.py). Codes radio des scripts de STAGE.DIR (commande radio
0x24E1, options b / o / c, jetons 0x0A) : octet du fragment dans RADIO.DAT sur 24 bits, et
nombre de secteurs à lire en plus sur l'octet du haut (EXE US 0x8004a4e8 : lecture de
(code >> 24) + 1 secteurs depuis l'octet & ~0x7FF, fragment à l'octet & 0x7FF du tampon).
"""

import struct

TALK, VOICE, IF, ELSE, ELSEIF, SWITCH, CASE, DEFAULT, RANDSWITCH, RCASE = 1, 2, 0x10, 0x11, 0x12, 0x20, 0x21, 0x22, 0x30, 0x31


def be16(b, i):
    return (b[i] << 8) | b[i + 1]


def value_len(b, p):
    """Longueur d'une valeur GCL (libgcl)."""
    t = b[p]
    if t & 0xF0 == 0x10:
        return 4
    if t in (9, 10):
        return 5
    if t in (1, 6, 8):
        return 3
    if t in (2, 3, 4, 0x20):
        return 2
    if t == 7:
        return 2 + b[p + 1]
    if t == 0x30:
        return 1 + b[p + 1]
    raise ValueError(f"valeur GCL {t:#x} en {p:#x}")


def _size(n):
    if n > 0xFFFF:
        raise ValueError(f"taille {n} : plus de 65535 octets")
    return struct.pack(">H", n)


class Block:
    def __init__(self, lead, items):
        self.lead, self.items = lead, items   # items : [Cmd]

    def size(self):
        return 4 + sum(c.size() for c in self.items)

    def bytes(self):
        body = b"".join(c.bytes() for c in self.items) + b"\0"
        return bytes([self.lead]) + _size(len(body) + 2) + body


class Cmd:
    """code, parts : suite de bytes (arguments bruts) et de Block, dans l'ordre."""
    def __init__(self, code, parts):
        self.code, self.parts = code, parts

    def size(self):
        return 4 + sum(p.size() if isinstance(p, Block) else len(p) for p in self.parts)

    def bytes(self):
        body = b"".join(p.bytes() if isinstance(p, Block) else p for p in self.parts)
        return bytes([0xFF, self.code]) + _size(len(body) + 2) + body

    # TALK
    @property
    def text(self):
        return self.parts[0][6:].split(b"\0")[0]

    def set_text(self, t):
        assert self.code == TALK
        self.parts[0] = self.parts[0][:6] + t + b"\0"


def parse_block(b, p):
    lead, size = b[p], be16(b, p + 1)
    end = p + 1 + size
    i, items = p + 3, []
    while b[i]:
        items.append(parse_cmd(b, i))
        i += 2 + be16(b, i + 2)
    if i + 1 != end:
        raise ValueError(f"bloc {p:#x} : fin {i + 1:#x} au lieu de {end:#x}")
    return Block(lead, items)


def block_len(b, p):
    return 1 + be16(b, p + 1)


def parse_cmd(b, i):
    if b[i] != 0xFF:
        raise ValueError(f"commande attendue en {i:#x}")
    code, size = b[i + 1], be16(b, i + 2)
    a, end = i + 4, i + 2 + size
    parts = []

    def raw(x, y):
        if y > x:
            parts.append(bytes(b[x:y]))

    def blk(x):
        parts.append(parse_block(b, x))
        return x + block_len(b, x)

    if code == VOICE:
        raw(a, a + 4)
        p = blk(a + 4)
        raw(p, end)
    elif code == IF:
        p = a + value_len(b, a)
        raw(a, p)
        p = blk(p)
        while p < end and b[p] == 0xFF and b[p + 1] in (ELSE, ELSEIF):
            q = p + 2 + (value_len(b, p + 2) if b[p + 1] == ELSEIF else 0)
            raw(p, q)
            p = blk(q)
        raw(p, end)
    elif code == SWITCH or code == RANDSWITCH:
        p = a + (value_len(b, a) if code == SWITCH else 2)
        raw(a, p)
        while p < end and b[p] in (CASE, DEFAULT, RCASE):
            q = p + 1 + (0 if b[p] == DEFAULT else 2)
            raw(p, q)
            p = blk(q)
        raw(p, end)
    else:
        raw(a, end)
    c = Cmd(code, parts)
    if c.bytes() != bytes(b[i:end]):
        raise ValueError(f"commande {code:#x} en {i:#x} : relecture différente")
    return c


class Fragment:
    def __init__(self, b, off, end):
        self.head = bytes(b[off:off + 8])
        self.script = parse_block(b, off + 8)
        self.tail = bytes(b[off + 8 + block_len(b, off + 8):end])   # police (+ remplissage)

    def bytes(self):
        return self.head + self.script.bytes() + self.tail


def walk(node, fn, voice=None):
    """fn(cmd, voice) sur toutes les commandes, dans l'ordre ; voice = VOICE englobante."""
    items = node.items if isinstance(node, Block) else []
    for c in items:
        fn(c, voice)
        v = c if c.code == VOICE else voice
        for p in c.parts:
            if isinstance(p, Block):
                walk(p, fn, v)


def radio_codes(st):
    """Codes radio de STAGE.DIR : [(position du jeton 0x0A, étape, valeur)] dans l'ordre des scripts."""
    import gcx
    out = []
    for name, a, _ in gcx.stage_table(st):
        for g in gcx.scripts(st, a):
            for p, cmd, opt in gcx.int_tokens(st, g):
                if cmd == 0x24E1 and opt in ("b", "o", "c") and st[p] == 0x0A:
                    out.append((p, name, struct.unpack_from(">I", st, p + 1)[0]))
    return out
