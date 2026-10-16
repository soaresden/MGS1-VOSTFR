#!/usr/bin/env python3
"""
life.py - Patch optionnel : remplace le mot « LIFE » de la barre de vie par un texte au choix
(par exemple « SNAKE »).

Le mot est dessiné par menu_draw_bar (menu/life.c de la décompilation) avec la petite police
du HUD (« num.res », capitales de 5 pixels de haut) ; le cadre sombre derrière le mot s'adapte
tout seul à sa largeur. Le texte vient de la structure gSnakeLifeBarConfig (.data : pointeur
vers le nom, puis les couleurs de la barre), qui pointe vers « LIFE » (case de 8 octets dans
.sdata, suivie de « O2 »). La même structure sert à la barre de vie dessinée dans les menus
d'armes et d'objets (R2 / L2).

Le patch écrit le nouveau texte (16 octets, zéros à la fin) à la place des chaînes
« No %d » / « ID %d » du menu de débogage (jamais affiché, son code est déjà pris par les
autres options), puis fait pointer gSnakeLifeBarConfig dessus. « LIFE » lui-même n'est pas
touché. Seulement l'EXE (MGS1.EXE = MGS2.EXE ; PAL France ou PAL Europe anglaise, adresses
traduites par pal.py). Indépendant des autres options (aucun code ajouté).

Caractères (15 au plus) : lettres (les minuscules s'affichent en capitales, les accents sont
retirés), chiffres, espace et . : ! ? + - = % ( ). Dans la police, ( ) = % sont rangés aux
codes { } / * : le patch les convertit.

  python life.py "SNAKE" image.bin [image2.bin ...]     patch en place (VOSTFR, FR ou UK)
  python life.py --preview "SNAKE" sortie.png             aperçu (même rendu que le jeu)
"""

import struct, sys, unicodedata
from pathlib import Path

import pal, psxiso
from cdsector import write_file_inplace

LOAD = 0x80010000
CONF = 0x8009FC24      # gSnakeLifeBarConfig.name (pointeur), adresse FR
LIFE = 0x800ACBE0      # « LIFE\0\0\0\0 »
ZONE = 0x800ACC64      # « No %d\n\0\0ID %d\n\0\0 » (menu de débogage)
ZONE_ORIG = b"No %d\n\0\0ID %d\n\0\0"
MAXLEN = 15
DEFAULT = "LIFE"

# Police num.res (_menu_number_draw_string, menu/radio.c) : chiffres en haut (v 488), lettres
# en bas (v 493), symboles après les chiffres (u 60 + 6 * rang). Caractère affiché -> code.
CODE = {"(": "{", ")": "}", "=": "/", "%": "*"}
SYMBOLS = ".@:_!?+-/*{}"
SKIP = {".": 2, "@": 2, ":": 2, "_": 4, "!": 2, "?": 6, "+": 6, "-": 6, "/": 6, "*": 6, "{": 3, "}": 3}
ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .:!?+-=%()")
PREVIEWS = Path(__file__).resolve().parent.parent / "docs" / "previews"


def clean(text):
    """Texte saisi -> texte affiché (capitales, sans accents) ; erreur claire sinon."""
    t = text.replace("œ", "oe").replace("Œ", "OE").replace("æ", "ae").replace("Æ", "AE")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().upper().strip()
    bad = sorted(set(t) - ALLOWED)
    if bad:
        raise SystemExit(f"--life : caractères impossibles dans la police du HUD : {' '.join(bad)} "
                         "(lettres, chiffres, espace et . : ! ? + - = % ( ) seulement)")
    if not t:
        raise SystemExit("--life : texte vide")
    if len(t) > MAXLEN:
        raise SystemExit(f"--life : {MAXLEN} caractères au plus ({len(t)} donnés)")
    return t


def encode(text):
    """Texte affiché -> octets écrits dans l'EXE (16, zéros à la fin)."""
    return "".join(CODE.get(c, c) for c in clean(text)).encode("ascii").ljust(16, b"\0")


def glyphs(text):
    """Comme le jeu : [(x, u, v)] de chaque sprite 6x5 et largeur totale en pixels."""
    out, x = [], 0
    for c in encode(text).rstrip(b"\0").decode():
        if c == " ":
            x += 4
            continue
        if c.isdigit():
            u, v, skip = 6 * int(c), 0, 6
        elif c.isalpha():
            u, v, skip = 6 * (ord(c) - 65), 5, 6
            if c == "I":
                x, skip = x + 1, 3
        else:
            u, v, skip = 60 + 6 * SYMBOLS.index(c), 0, SKIP[c]
            if skip < 3:
                x, skip = x + 1, skip + 1
        out.append((x, u, v))
        x += skip
    return out, x


def offsets(v):
    """Offsets dans le fichier EXE : (pointeur du nom, zone du texte, adresse de la zone)."""
    o = lambda a: 0x800 + pal.daddr(v, a) - LOAD
    return o(CONF), o(ZONE), pal.daddr(v, ZONE)


def patch(exe, text):
    """EXE PAL France ou Europe -> EXE avec le texte (None si texte = LIFE, rien à faire)."""
    data = encode(text)
    v = pal.version(exe)
    conf, zone, zaddr = offsets(v)
    life = pal.daddr(v, LIFE)
    ptr = struct.unpack_from("<I", exe, conf)[0]
    if ptr == life:
        if exe[zone:zone + 16] != ZONE_ORIG:
            raise SystemExit(f"EXE inattendu : chaînes du menu de débogage modifiées ({v})")
    elif ptr != zaddr:  # zaddr = déjà patché : on remplace le texte
        raise SystemExit(f"EXE inattendu : nom de la barre de vie à {ptr:08x} ({v})")
    if clean(text) == DEFAULT and ptr == life:
        return None
    out = bytearray(exe)
    if clean(text) == DEFAULT:  # retour à l'origine
        out[zone:zone + 16] = ZONE_ORIG
        struct.pack_into("<I", out, conf, life)
    else:
        out[zone:zone + 16] = data
        struct.pack_into("<I", out, conf, zaddr)
    return bytes(out)


def preview(text, now=100, rest=110, vmax=256, x=16, y=16):
    """Image 320x256 du HUD (fond docs/previews/life_bg.png), rendu de menu_draw_bar.
    now = vie, rest = vie affichée (partie rouge entre les deux), vmax = vie max (256 au début)."""
    from PIL import Image
    im = Image.open(PREVIEWS / "life_bg.png").convert("RGB")
    font = Image.open(PREVIEWS / "life_font.png").convert("RGBA")
    px = im.load()

    def rect(x0, y0, w, h, col, semi=False):  # semi : 50 % fond + 50 % couleur
        for yy in range(y0, y0 + h):
            for xx in range(x0, x0 + w):
                if 0 <= xx < 320 and 0 <= yy < 256:
                    px[xx, yy] = tuple((a + b) // 2 for a, b in zip(px[xx, yy], col)) if semi else col

    g, tw = glyphs(text)
    w = vmax // 8
    # ordre de dessin du jeu (la table d'ordre est remplie à l'envers)
    for args in ((x - 1, y, 1, 7), (x, y, w, 1), (x, y + 6, w, 1), (x + w, y, 1, 7)):
        rect(*args, (0, 0, 0))
    rect(x, y + 1, w, 5, (0, 0x18, 0x18), True)
    left, right = (0x10, 0x8F, 0x7F), (0x1F, 0xDF, 0x3F)
    for k in range((now + 7) // 8):
        rect(x + k, y + 1, 1, 5, tuple(l + (r - l) * k // 128 for l, r in zip(left, right)))
    if rest > now:
        rect(x + now // 8, y + 1, (min(rest, vmax) - now) // 8, 5, (200, 0, 0))
    rect(x + 3, y + 3, tw + 2, 7, (0, 0, 0), True)
    for gx, u, v in g:
        im.paste(font.crop((u, v, u + 6, v + 5)), (x + 4 + gx, y + 4), font.crop((u, v, u + 6, v + 5)))
    return im


def patch_image(path, text):
    disc = psxiso.Disc(path)
    files = disc.files()
    name = next(p for p in files if p in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
    exe = disc.read(*files[name])
    disc.f.close()
    new = patch(exe, text)
    if new is not None:
        write_file_inplace(path, files[name][0], new)
    return name, new is not None


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    if sys.argv[1] == "--preview":
        preview(sys.argv[2]).save(sys.argv[3])
        return
    text = sys.argv[1]
    for p in sys.argv[2:]:
        name, done = patch_image(p, text)
        print(f"{p} : {name} {'barre de vie : ' + clean(text) if done else 'inchangé'}")


if __name__ == "__main__":
    main()
