#!/usr/bin/env python3
"""
change_us.py - Écrans de changement de disque en français sur la version USA (« Insert DISC 2. »,
« Now Checking... »…), avec la case « French texts » (codec_us.py, .psxmod).

Ces textes sont les arguments (liste de chaînes GCL `07 longueur texte\\0`) d'une commande des
scripts des stages `title` et `change`, sur les deux disques. L'ordre des chaînes n'est pas le même
d'un écran à l'autre : chaque chaîne anglaise est traduite d'après son texte. STAGE.DIR doit garder
sa taille (et le script aussi) : la liste FR occupe exactement la place de la liste US ; si elle
déborde, on prend la combinaison de formulations plus courtes la plus proche des préférées ; la place en trop est
laissée en zéros dans la dernière chaîne traduite (longueur GCL comprise, le jeu lit une chaîne C).
"""

import itertools
import re

import exe_us
import gcx
import usfont

STAGES = ("title", "change", "abst", "demosel")   # abst : chargement d'une sauvegarde de l'autre disque
# texte anglais -> formulations FR, de la préférée à la plus courte ({n} = numéro du disque) ;
# « Appuyez sur START » / « après insertion du disque n. » se lisent dans les deux ordres des listes US
TEXTS = [
    (r"Insert DISC (\d)\.", ["Insérez le disque {n}.", "Insérez le disque {n}"]),
    (r"after inserting DISC (\d)\.", ["après insertion du disque {n}.", "après insertion du disque {n}"]),
    (r"Press the Start Button", ["Appuyez sur START"]),
    (r"Now Checking\.\.\.", ["Vérification...", "Vérification"]),
    (r"RADAR OFF", ["RADAR ETEINT", "RADAR COUPE"]),
    (r"The correct DISC was not inserted\.", ["Ce n'est pas le bon disque.", "Ce n'est pas le bon disque",
                                               "Pas le bon disque."]),
]
START = re.compile(rb"\x07\x0fInsert DISC \d\.\x00")


def texts():
    """Textes FR (accents 1F xx) : pour choisir les accents de la police."""
    return [exe_us.fr_bytes(c.replace("{n}", "1")) for _, cs in TEXTS for c in cs]


def _strings(st, i):
    """Liste de chaînes GCL à l'octet i : [(début, longueur GCL, texte)], fin."""
    out = []
    while st[i] == 0x07:
        n = st[i + 1]
        out.append((i, n, bytes(st[i + 2:i + 2 + n]).split(b"\0")[0]))
        i += 2 + n
    return out, i


def _choices(s):
    for pat, cs in TEXTS:
        m = re.fullmatch(pat, s.decode("latin1"))
        if m:
            return [c.replace("{n}", m.group(1)) if m.groups() else c for c in cs]
    return None


def patch(st, accents):
    """STAGE.DIR avec les écrans de changement de disque en FR. Renvoie (STAGE.DIR, listes, chaînes)."""
    out = bytearray(st)
    lists = done = 0
    for name, a, e in gcx.stage_table(st):
        if name not in STAGES:
            continue
        end = a
        for m in START.finditer(st, a, e):
            if m.start() < end:                # « Insert DISC 2. » dans la liste déjà traitée (abst)
                continue
            items, end = _strings(st, m.start())
            room = end - m.start()
            opts = [_choices(s) for _, _, s in items]
            pick = [0] * len(items)

            def enc(k):
                if opts[k] is None:
                    return items[k][2]
                return usfont.convert(exe_us.fr_bytes(opts[k][pick[k]]), accents)

            def size():
                return sum(2 + len(enc(k)) + 1 for k in range(len(items)))

            # formulations : la combinaison qui tient et s'écarte le moins des préférées
            best = None
            for combo in itertools.product(*[range(len(o)) if o else [0] for o in opts]):
                pick[:] = combo
                if size() <= room and (best is None or sum(combo) < sum(best)):
                    best = combo
            if best is None:
                raise ValueError(f"{name} : textes FR trop longs pour la place ({room} octets)")
            pick[:] = best
            pad = room - size()
            last = max(k for k in range(len(items)) if opts[k] is not None)
            b = bytearray()
            for k in range(len(items)):
                t = enc(k) + bytes(1 + (pad if k == last else 0))
                if len(t) > 255:
                    raise ValueError(f"{name} : chaîne GCL trop longue")
                b += bytes([0x07, len(t)]) + t
            assert len(b) == room
            out[m.start():end] = b
            lists += 1
            done += sum(o is not None for o in opts)
    return bytes(out), lists, done
