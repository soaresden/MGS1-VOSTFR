#!/usr/bin/env python3
"""
titre.py - Patch optionnel : écran titre « METAL GEAR SOLID - SHADOW FIXES », by Soaresden, v1.0.

L'écran titre (stage « title » de STAGE.DIR) prend ses images dans le fichier DAR du stage
(tag 'n'/'d') : entrées {u16 id, u8 extension, u8 0, u32 taille (multiple de 4 : le jeu passe à
l'entrée suivante sans réaligner, une taille impaire le fait planter), données}, les
images étant des PCX ('p' ; 8 bits + palette, ou 4 plans de 1 bit) que le jeu charge en VRAM.
Retouches (même nombre de secteurs pour le DAR, STAGE.DIR ne change pas de taille) :
- logo (PCX 0x26F0, 230 x 45, 8 bits) : la bande claire sous « METAL GEAR », qui portait
  « S O L I D », porte « SOLID - SHADOW FIXES » (lettres refaites, mêmes couleurs : dégradé des
  index 17-30, une couleur par rangée) ;
- visage de Snake (PCX 0xC76A, 116 x 206, 8 bits, au centre de l'écran) : « by Soaresden  v1.0 »
  juste au-dessus du menu (NEW GAME / PRESS START BUTTON), en rose (la couleur la plus claire de l'image) cerné de
  sombre.
Les polices viennent de Windows (Arial gras, graissé d'un pixel pour la bande), rendues sans lissage.

  python titre.py image.bin [image2.bin ...]     patch en place (MGS/STAGE.DIR et MGS2/STAGE.DIR)
"""

import struct
import sys
from pathlib import Path

import gcx, psxiso
from cdsector import write_file_inplace

VERSION = "v1.0"
BAND = "SOLID - SHADOW FIXES"
CREDIT = f"by Soaresden  {VERSION}"
LOGO, FACE = 0x26F0, 0xC76A
FONTS = Path("C:/Windows/Fonts")


def _font(name, size):
    from PIL import ImageFont
    for p in (FONTS / name, Path(name)):
        if p.exists():
            return ImageFont.truetype(str(p), size)
    raise SystemExit(f"police {name} introuvable")


def _mask(text, font, w, h):
    """Masque du texte (liste de rangées de booléens), centré, rendu sans lissage."""
    from PIL import Image, ImageDraw
    im = Image.new("1", (w, h + 8), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    box = d.textbbox((0, 0), text, font=font)
    x = (w - (box[2] - box[0])) // 2 - box[0]
    d.text((x, -box[1]), text, font=font, fill=1)
    px = im.load()
    rows = [[bool(px[i, j]) for i in range(w)] for j in range(h + 8)]
    while rows and not any(rows[-1]):
        rows.pop()
    return rows


def dar_entries(dar):
    p, out = 0, []
    while p + 8 <= len(dar):
        tid, ext, size = struct.unpack_from("<HBxI", dar, p)
        if size == 0 or ext == 0:
            break
        out.append([tid, ext, dar[p + 8:p + 8 + size]])
        p += 8 + (size + 3) // 4 * 4
    return out, dar[p:]


def dar_build(entries, tail):
    out = bytearray()
    for tid, ext, data in entries:
        out += struct.pack("<HBxI", tid, ext, len(data)) + data + bytes(-len(data) % 4)
    return bytes(out + tail)


def pcx_decode(b):
    """PCX 8 bits (1 plan) -> (largeur, hauteur, pixels [rangées], fin des données RLE)."""
    assert b[0] == 0x0A and b[2] == 1 and b[3] == 8 and b[65] == 1, "PCX 8 bits attendu"
    xmin, ymin, xmax, ymax = struct.unpack_from("<4H", b, 4)
    bpl = struct.unpack_from("<H", b, 66)[0]
    w, h = xmax - xmin + 1, ymax - ymin + 1
    raw, p = bytearray(), 128
    while len(raw) < bpl * h:
        c = b[p]
        p += 1
        if c >= 0xC0:
            raw += bytes([b[p]]) * (c & 0x3F)
            p += 1
        else:
            raw.append(c)
    return w, h, [list(raw[y * bpl:y * bpl + w]) for y in range(h)], p


def pcx_encode(b, pix):
    """Recode les pixels dans le PCX b (même en-tête, même palette finale)."""
    bpl = struct.unpack_from("<H", b, 66)[0]
    end = pcx_decode(b)[3]
    rle = bytearray()
    for row in pix:
        line = bytes(row) + bytes(bpl - len(row))
        i = 0
        while i < len(line):
            v, n = line[i], 1
            while i + n < len(line) and line[i + n] == v and n < 63:
                n += 1
            if n > 1 or v >= 0xC0:
                rle += bytes([0xC0 | n, v])
            else:
                rle.append(v)
            i += n
    out = b[:128] + bytes(rle) + b[end:]
    return out + bytes(-len(out) % 4)          # le jeu enchaîne les entrées du DAR sans réaligner


def _row_colors(pix, rows, x0, x1):
    """Index de lettre le plus fréquent de chaque rangée (lettres = index >= 16)."""
    out = []
    for y in rows:
        c = {}
        for v in pix[y][x0:x1]:
            if v >= 16:
                c[v] = c.get(v, 0) + 1
        out.append(max(c, key=c.get))
    return out


def patch_logo(b):
    w, h, pix, _ = pcx_decode(b)
    assert (w, h) == (230, 45)
    rows = range(37, 44)                           # lettres de la bande (7 rangées)
    cols = _row_colors(pix, rows, 11, 219)
    for y in rows:                                 # efface « S O L I D » (fond de bande = 2)
        pix[y][11:219] = [2 if v >= 16 else v for v in pix[y][11:219]]
    m = _mask(BAND, _font("arialbd.ttf", 9), 208, 7)
    assert len(m) <= 7, "texte de bande trop haut"
    top = 37 + (7 - len(m)) // 2
    for j, r in enumerate(m):
        for i, on in enumerate(r):
            if on or (i and r[i - 1]):             # graissé d'un pixel, comme les lettres d'origine
                pix[top + j][11 + i] = cols[top + j - 37]
    return pcx_encode(b, pix)


def patch_face(b):
    w, h, pix, _ = pcx_decode(b)
    assert (w, h) == (116, 206)
    pal = b[-768:]
    lum = lambda i: sum(pal[3 * i:3 * i + 3])
    ink = max(range(1, 256), key=lum)
    dark = min((i for i in range(1, 256) if lum(i) > 0), key=lum)
    m = _mask(CREDIT, _font("arialbd.ttf", 10), w - 4, 10)
    top = 138                                      # au-dessus du menu (écran y 178-186)
    on = {(2 + i, top + j) for j, r in enumerate(m) for i, v in enumerate(r) if v}
    for x, y in on:                                # cerne sombre
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (x + dx, y + dy) not in on and 0 <= x + dx < w and 0 <= y + dy < h and pix[y + dy][x + dx]:
                    pix[y + dy][x + dx] = dark
    for x, y in on:
        pix[y][x] = ink
    return pcx_encode(b, pix)


def _dar_span(st, a):
    """(position, taille, position du champ taille) du fichier DAR ('n'/'d') du stage en a."""
    i, pos = a + 4, a + 2048
    while True:
        tid, mode, ext, size = struct.unpack_from("<HBBi", st, i)
        if mode == 0:
            raise SystemExit("title : DAR introuvable")
        if chr(mode) == "n" and chr(ext) == "d":
            return pos, size, i + 4
        if chr(mode) == "c":
            raise SystemExit("title : DAR introuvable avant le cache")
        pos += (size + 2047) // 2048 * 2048
        i += 8


def patch_stage(st):
    """STAGE.DIR -> (STAGE.DIR patché, nombre d'images retouchées)."""
    out = bytearray(st)
    a = next(a for n, a, e in gcx.stage_table(st) if n == "title")
    pos, size, fld = _dar_span(st, a)
    ents, tail = dar_entries(st[pos:pos + size])
    n = 0
    for e in ents:
        if e[0] == LOGO and e[1] == ord("p"):
            e[2] = patch_logo(e[2])
            n += 1
        elif e[0] == FACE and e[1] == ord("p"):
            e[2] = patch_face(e[2])
            n += 1
    if n != 2:
        raise SystemExit("title : logo ou visage introuvable (déjà patché ?)")
    new = dar_build(ents, tail)
    if (len(new) + 2047) // 2048 != (size + 2047) // 2048:
        raise SystemExit(f"title : DAR trop grand ({len(new)} octets au lieu de {size})")
    out[pos:pos + (size + 2047) // 2048 * 2048] = new + bytes((size + 2047) // 2048 * 2048 - len(new))
    struct.pack_into("<i", out, fld, len(new))
    return bytes(out), n


def patch_image(path):
    d = psxiso.Disc(path)
    files = d.files()
    todo = []
    for k in ("MGS/STAGE.DIR", "MGS2/STAGE.DIR"):
        if k in files:
            lba, size = files[k]
            todo.append((lba, patch_stage(d.read(lba, size))[0]))
    d.f.close()
    for lba, new in todo:
        write_file_inplace(path, lba, new)
    return len(todo)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        print(p, ":", patch_image(p), "STAGE.DIR, écran titre « Shadow Fixes »")


if __name__ == "__main__":
    main()
