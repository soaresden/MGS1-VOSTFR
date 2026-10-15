#!/usr/bin/env python3
"""
vox.py - Lecture des archives VOX.DAT / DEMO.DAT de MGS1 PS1.

Une archive est une suite de banques alignées sur 2048 octets. Chaque banque est une
suite de blocs [code u8][taille u16 LE][...] :
  0x10 Init   0x01 Son (VAG)   0x02 en-tête audio   0x03 / 0x06 sous-titres + lèvres
  0x04 en-tête 2   0x05 démo   0xF0 fin de banque

  python vox.py banks  VOX.DAT            liste des banques
  python vox.py subs   VOX.DAT [banque]   sous-titres
"""

import struct, sys

INIT, SOUND, HDR1, CAPS1, HDR2, DEMO, CAPS2, END = 0x10, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0xF0


def blocks(data, start):
    """Itère les blocs (code, offset, taille) d'une banque jusqu'au bloc de fin."""
    i = start
    while i + 3 <= len(data):
        code, size = data[i], struct.unpack_from("<H", data, i + 1)[0]
        if size == 0:
            return
        yield code, i, size
        if code == END:
            return
        i += size


def banks(data):
    """Liste des (offset, fin) des banques."""
    out, i = [], 0
    while i + 8 <= len(data):
        if data[i] != INIT or struct.unpack_from("<H", data, i + 1)[0] != 8:
            i += 2048
            continue
        end = i
        for code, off, size in blocks(data, i):
            end = off + size
        out.append((i, end))
        i = (end + 2047) // 2048 * 2048
    return out


def captions(data, off):
    """Sous-titres d'un bloc 0x03/0x06 : [(offset_absolu, temps, durée, inconnu, texte_brut)]."""
    caps_rel = struct.unpack_from("<H", data, off + 14)[0]
    j, out = off + caps_rel + 4, []
    while True:
        size, t, dur, unk = struct.unpack_from("<IIII", data, j)
        end = data.index(b"\0", j + 16)
        out.append((j, t, dur, unk, data[j + 16:end]))
        if size == 0:
            return out
        j += size


def text(raw):
    """Rendu lisible : ASCII tel quel, octets spéciaux en {xx}."""
    s = ""
    for b in raw:
        s += chr(b) if 32 <= b < 127 else ("|" if b == 10 else f"{{{b:02x}}}")
    return s


def bank_info(data, start):
    info = {"sound": 0, "caps": [], "codes": []}
    for code, off, size in blocks(data, start):
        info["codes"].append(code)
        if code == SOUND:
            info["sound"] += size - 4
        elif code == HDR1:
            info["rate"], info["ch"] = data[off + 10], data[off + 12]
        elif code in (CAPS1, CAPS2):
            info["caps"].append((code, off, captions(data, off)))
    return info


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    data = open(path, "rb").read()
    bl = banks(data)
    if cmd == "banks":
        for n, (s, e) in enumerate(bl):
            inf = bank_info(data, s)
            ncap = sum(len(c[2]) for c in inf["caps"])
            first = next((text(c[2][0][4]) for c in inf["caps"] if c[2]), "")
            print(f"{n:4d} sect {s // 2048:6d} taille {e - s:8d} son {inf['sound']:8d} caps {ncap:3d}  {first[:70]}")
    elif cmd == "subs":
        sel = [int(sys.argv[3])] if len(sys.argv) > 3 else range(len(bl))
        for n in sel:
            inf = bank_info(data, bl[n][0])
            print(f"== banque {n} (secteur {bl[n][0] // 2048})")
            for code, off, caps in inf["caps"]:
                for j, t, dur, unk, raw in caps:
                    print(f"  [{code}] t={t:6d} d={dur:5d} u={unk:x}  {text(raw)}")


if __name__ == "__main__":
    main()
