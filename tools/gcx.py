#!/usr/bin/env python3
"""
gcx.py - Lecture des scripts GCX (bytecode GCL) de STAGE.DIR et repérage exact des codes VOX / DEMO.

Stage (libfs/datacnf.h) : secteur d'en-tête {u8 1, u8, s16 secteurs, tags {u16 id, char mode,
char ext, s32 taille}... , tag nul}, puis les fichiers dans l'ordre des tags, chacun aligné sur
2048 octets, sauf les tags 'c' (cache) qui forment un seul bloc : leur champ taille est le décalage
du fichier dans ce bloc, le dernier ('c', 0xFF) en donne la taille totale. Scripts = 'c'/'g'.

GCX (libgcl/command.c) : u32 BE taille de la table des procédures, table {u16 id, u16 décalage}
terminée par un u32 nul, corps des procédures (chacun = valeur ARG 0x40), u32 taille du script,
script principal (valeur ARG). Bloc = suite d'instructions : 0x30 expression [n], 0x60 commande
[u16 taille, u16 id, u8 décalage des options, arguments...], 0x70 appel [n, u16 id, valeurs], 0x00 fin.
Valeurs : 0x1X variable (4 octets), 0x01 short, 0x09 int / 0x0A symbole (u32 BE), 0x06 / 0x08
(u16), 0x02-0x04 (u8), 0x07 chaîne [n], 0x20 tableau (u8), 0x40 bloc [u16 taille], 0x30 expression
[n] (valeurs et opérateurs 0x31 xx), 0x50 option [lettre, n] suivie de ses valeurs.

Codes (vérifié sur les 4 disques FR / UK) : toujours des jetons 0x09 ou 0x0A. Cinématiques =
commande « demo » (id 0xA242), valeur de l'option 's' -> secteur relatif à DEMO.DAT. Voix = tout
autre jeton 0x09 / 0x0A dont la valeur est un début de banque de VOX.DAT (non nul). Le balayage
brut d'octets (vox_vostfr.gcl_ints) attrape aussi des données d'overlays : à éviter.
"""

import struct

DEMO_CMD = 0xA242


def _be16(b, i):
    return struct.unpack_from(">H", b, i)[0]


def _be32(b, i):
    return struct.unpack_from(">I", b, i)[0]


def stage_table(st):
    """Répertoire de STAGE.DIR : [(nom, début, fin)] en octets."""
    size = struct.unpack_from("<I", st, 0)[0]
    ent = [(st[4 + 12 * k:12 + 12 * k].rstrip(b"\0").decode("latin1"),
            struct.unpack_from("<I", st, 12 + 12 * k)[0] * 2048) for k in range(size // 12)]
    return [(n, o, ent[k + 1][1] if k + 1 < len(ent) else len(st)) for k, (n, o) in enumerate(ent)]


def scripts(st, a):
    """Débuts des scripts GCX du stage qui commence à l'octet a."""
    tags, i = [], a + 4
    while True:
        tid, mode, ext, sz = struct.unpack_from("<HBBi", st, i)
        if mode == 0:
            break
        tags.append((chr(mode), chr(ext), sz))
        i += 8
    pos, k, out = a + 2048, 0, []
    while k < len(tags):
        if tags[k][0] == "c":
            j = k
            while j < len(tags) and tags[j][0] == "c":
                j += 1
            grp = tags[k:j]
            out += [pos + off for _, ext, off in grp[:-1] if ext == "g"]
            pos += (grp[-1][2] + 2047) // 2048 * 2048
            k = j
        else:
            pos += (tags[k][2] + 2047) // 2048 * 2048
            k += 1
    return out


class _Walker:
    def __init__(self, b, cb):
        self.b, self.cb = b, cb

    def block(self, p, cmd):
        b = self.b
        while True:
            t = b[p]
            if t == 0:
                return
            if t == 0x30:
                self.expr(p + 2, p + 1 + b[p + 1], cmd)
                p += 1 + b[p + 1]
            elif t == 0x60:
                size = _be16(b, p + 1)
                self.values(p + 6, p + 1 + size, _be16(b, p + 3))
                p += 1 + size
            elif t == 0x70:
                self.values(p + 4, p + 1 + b[p + 1], cmd)
                p += 1 + b[p + 1]
            else:
                raise ValueError(f"GCX : instruction {t:#x} en {p:#x}")

    def value(self, p, cmd, opt):
        b = self.b
        t = b[p]
        if t & 0xF0 == 0x10:
            return p + 4
        if t in (9, 10):
            self.cb(p, cmd, opt)
            return p + 5
        if t in (1, 6, 8):
            return p + 3
        if t in (2, 3, 4, 0x20):
            return p + 2
        if t == 7:
            return p + 2 + b[p + 1]
        if t == 0x40:
            self.block(p + 3, cmd)
            return p + 1 + _be16(b, p + 1)
        if t == 0x30:
            self.expr(p + 2, p + 1 + b[p + 1], cmd, opt)
            return p + 1 + b[p + 1]
        if t == 0x50:
            return p + 3
        raise ValueError(f"GCX : valeur {t:#x} en {p:#x}")

    def values(self, p, end, cmd):
        opt = None
        while p < end and self.b[p]:
            if self.b[p] == 0x50:
                opt = chr(self.b[p + 1])
            p = self.value(p, cmd, opt)

    def expr(self, p, end, cmd, opt=None):
        while p < end and self.b[p]:
            p = p + 2 if self.b[p] == 0x31 else self.value(p, cmd, opt)


def int_tokens(st, g):
    """Jetons 0x09 / 0x0A du script GCX à l'octet g : [(position, id de commande, option)]."""
    out = []
    w = _Walker(st, lambda p, cmd, opt: out.append((p, cmd, opt)))
    proclen = _be32(st, g)
    pt = g + 4
    procs = []
    while _be32(st, pt):
        procs.append(_be16(st, pt + 2))
        pt += 4
    for off in procs:
        w.block(pt + 4 + off + 3, None)
    w.block(g + 4 + proclen + 4 + 3, None)
    return out


def codes(st, vox_starts, demo_starts):
    """Codes de STAGE.DIR : [(position du jeton, 'vox' | 'demo', nom du stage)]. La valeur (u32 BE)
    est en position + 1. vox_starts / demo_starts : secteurs de début des banques."""
    out = []
    for name, a, _ in stage_table(st):
        for g in scripts(st, a):
            for p, cmd, opt in int_tokens(st, g):
                v = _be32(st, p + 1)
                if cmd == DEMO_CMD:
                    if opt == "s" and v in demo_starts:
                        out.append((p, "demo", name))
                elif v and v in vox_starts:
                    out.append((p, "vox", name))
    return out
