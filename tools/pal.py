#!/usr/bin/env python3
"""
pal.py - Versions de l'EXE gérées par les patchs : PAL France (SLES-01506/11506, adresses de
référence des patchs) et PAL Europe anglaise (SLES-01370/11370).

Les patchs sont écrits avec les adresses de la version française ; pour la version anglaise,
addr() les traduit avec la table de pal_uk.py (générée par palmap.py : code et données décalés
par morceaux, même compilation). Les octets d'origine sont vérifiés instruction par instruction
sans les champs qui dépendent des adresses, et les cibles de jal/j exactement.
"""

import hashlib, struct

import pal_uk

LOAD = 0x80010000
FR_SIG = "afa7b2e0ba7a6157ced6d66afaa17be8be0e77a1"   # SHA-1 de exe[0x800:0x1000] (textes du début)
FR_OVB = 0x800C47D8
IMM = {0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26,
       0x28, 0x29, 0x2A, 0x2B, 0x2E, 0x32, 0x3A}


class VersionError(SystemExit):
    pass


def version(exe):
    """'FR' ou 'UK' ; exception claire pour une autre version (US, japonaise...)."""
    s = hashlib.sha1(exe[0x800:0x1000]).hexdigest()
    if s == FR_SIG:
        return "FR"
    if s == pal_uk.SIG:
        return "UK"
    raise VersionError("EXE non reconnu : il faut Metal Gear Solid PAL France (SLES-01506/11506) "
                       "ou PAL Europe anglaise (SLES-01370/11370)")


def lookup(tab, a, data=False):
    for seg in ([] if data else tab["CODE"]) + tab["DATA"]:
        if seg[0] <= a < seg[1]:
            return a + seg[2]
    raise VersionError(f"adresse {a:08x} sans équivalent connu dans la version anglaise (palmap.py)")


UK = dict(CODE=pal_uk.CODE, DATA=pal_uk.DATA)


def addr(v, a):
    """Adresse de la version française -> même adresse dans la version v."""
    return a if v == "FR" else lookup(UK, a)


def daddr(v, a):
    """Idem pour une donnée (variable, table)."""
    return a if v == "FR" else lookup(UK, a, data=True)


def gp(v, off):
    """Décalage relatif à gp de la version française -> version v."""
    return off if v == "FR" else lookup(UK, pal_uk.GP_FR + off, data=True) - pal_uk.GP


def ovb(v):
    """Adresse de chargement des overlays de stage."""
    return FR_OVB if v == "FR" else pal_uk.OVB


def syms(v, d):
    """Traduit les adresses (0x80010000-0x801fffff) d'un dictionnaire de symboles."""
    if v == "FR":
        return dict(d)
    return {k: (addr(v, x) if isinstance(x, int) and LOAD <= x < 0x80200000 else x) for k, x in d.items()}


def cave_ok(v, exe, lo, hi, fr_sha):
    """La zone de code ajouté [lo, hi) (adresses françaises) a-t-elle ses octets d'origine ?"""
    a, b = addr(v, lo), addr(v, hi - 4) + 4
    sha = hashlib.sha1(exe[0x800 + a - LOAD:0x800 + b - LOAD]).hexdigest()
    return sha == (fr_sha if v == "FR" else pal_uk.CAVE_SHA1[lo])


def mask(x):
    op = x >> 26
    if op in (2, 3):
        return x & 0xFC000000
    if op in IMM:
        return x & 0xFFFF0000
    return x


def same(v, cur, orig_hex):
    """Les octets cur de la version v correspondent-ils aux octets d'origine (version française) ?"""
    orig = bytes.fromhex(orig_hex)
    if v == "FR":
        return cur == orig
    if len(cur) != len(orig):
        return False
    for k in range(0, len(orig), 4):
        x, y = struct.unpack_from("<I", orig, k)[0], struct.unpack_from("<I", cur, k)[0]
        if mask(x) != mask(y):
            return False
        if x >> 26 in (2, 3) and addr(v, 0x80000000 | (x & 0x3FFFFFF) << 2) != 0x80000000 | (y & 0x3FFFFFF) << 2:
            return False
    return True


def lang(v):
    return "fr" if v == "FR" else "en"
