#!/usr/bin/env python3
"""
webpatches.py - Exporte les mods « option » et « texte » de mods/ pour la page web.

La page fabrique les images dans le navigateur (docs/mgs-vostfr.js) ; les options sont
des différences d'octets sur l'EXE et STAGE.DIR d'origine, calculées ici avec les mêmes
scripts que build.py. Seuls les octets écrits par nos patchs sont exportés (notre code
MIPS et les instructions modifiées), avec le CRC32 des fichiers d'origine pour vérifier.

Une entrée par disque, nommée d'après versions/ : FR1, FR2 (France), UK1, UK2 (Europe, anglais).
Un mod « texte » (la barre de vie) n'est que des données : son patch.py donne avec web(exe) où
écrire (pointeur, zone du texte), la page encode le texte elle-même comme life.encode(). Un mod
qui ne sait pas encore s'appliquer à une version (ou ne la liste pas dans son mod.json) est
simplement absent de cette version (la page le grise). Les options doivent être additives (la différence de chaque
combinaison = l'union des différences de chaque option) : c'est vérifié sur chaque paire et sur
l'ensemble (toutes les combinaisons : 2^n constructions, trop long passé une dizaine de mods).

  python webpatches.py work/FR1.bin work/FR2.bin work/UK1.bin work/UK2.bin work/US1.bin work/US2.bin   -> docs/patches.js

À relancer après chaque modification d'une option.
"""

import itertools, json, re, sys, zlib
from pathlib import Path

import mods, psxiso

MODS = [m for m in mods.mods() if m["type"] == "option"]
ORDER = [m["id"] for m in MODS]  # ordre de build.py
TEXT = [m for m in mods.mods() if m["type"] == "texte"]
IDS = mods.disc_ids()
EXES = {v["id"] + d: names for v in mods.versions() for d, names in v["exe"].items()}
OUT = Path(__file__).resolve().parent.parent / "docs" / "patches.js"


def run(exe, stage, opts):
    f = mods.Files(exe, stage)
    mods.apply(f, opts, log=lambda m: None)
    if not isinstance(f.exe, (bytes, bytearray)) or not isinstance(f.stage, (bytes, bytearray)):
        raise ValueError("version non gérée par le patch")
    return bytes(f.exe), bytes(f.stage)


def runs(a, b):
    """Plages d'octets modifiés : [[offset, "hex"], ...]."""
    if len(a) != len(b):
        raise ValueError("un patch change la taille d'un fichier")
    out, i = [], 0
    while i < len(a):
        if a[i] == b[i]:
            i += 1
            continue
        j = i
        while j < len(a) and a[j] != b[j]:
            j += 1
        out.append([i, b[i:j].hex()])
        i = j
    return out


def apply(data, rs):
    d = bytearray(data)
    for off, hx in rs:
        d[off:off + len(hx) // 2] = bytes.fromhex(hx)
    return bytes(d)


def main():
    discs = {}
    for path in sys.argv[1:]:
        disc = psxiso.Disc(path)
        files = disc.files()
        cnf = disc.read(*files["SYSTEM.CNF"]).decode("ascii", "replace")
        ident = IDS.get(re.search(r"cdrom:\\?([A-Z0-9_.]+)", cnf, re.I).group(1).upper())
        if not ident:
            raise SystemExit(f"{path} : disque inconnu")
        exe_name = EXES[ident][0]   # les autres copies (version USA) sont identiques
        exe0, st0 = disc.read(*files[exe_name]), disc.read(*files["MGS/STAGE.DIR"])
        opts, missing = {}, {}
        for o in ORDER:
            if ident[:-1] not in mods.mods_by_id()[o]["versions"]:
                missing[o] = "version non listée dans mod.json"
                continue
            try:
                exe, st = run(exe0, st0, [o])
            except (Exception, SystemExit) as e:  # option pas encore portée sur cette version
                missing[o] = str(e)[:120]
                continue
            opts[o] = {"exe": runs(exe0, exe), "stage": runs(st0, st)}
        have = [o for o in ORDER if o in opts]
        for combo in list(itertools.combinations(have, 2)) + ([tuple(have)] if len(have) > 2 else []):
            exe, st = run(exe0, st0, combo)
            e2, s2 = exe0, st0
            for o in combo:
                e2, s2 = apply(e2, opts[o]["exe"]), apply(s2, opts[o]["stage"])
            if (e2, s2) != (exe, st):
                raise SystemExit(f"{ident} : options non additives {combo}")
        discs[ident] = {"exe": exe_name, "exes": EXES[ident], "exeCrc": zlib.crc32(exe0), "stageCrc": zlib.crc32(st0), "options": opts}
        for m in TEXT:  # barre de vie : pointeur u32 LE à écrire et zone de 16 octets pour le texte
            try:
                discs[ident][m["id"]] = mods.module(m).web(exe0)
            except (Exception, SystemExit) as e:
                print(f"{ident} : pas de {m['id']} ({e})")
        size = sum(len(hx) // 2 for o in opts.values() for k in o.values() for _, hx in k)
        print(f"{ident} : {', '.join(have) or 'aucune option'} ({size} octets)"
              + (f" ; pas encore : {', '.join(missing)}" if missing else ""))
    js = ("// Généré par tools/webpatches.py - ne pas modifier à la main.\n"
          "globalThis.MGS_PATCHES = " + json.dumps({"order": ORDER, "discs": discs}, separators=(",", ":")) + ";\n")
    OUT.write_text(js, encoding="utf-8")
    print(f"-> {OUT} ({len(js)} octets)")


if __name__ == "__main__":
    main()
