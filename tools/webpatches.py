#!/usr/bin/env python3
"""
webpatches.py - Exporte les options (carre, m9, psg1, l2r2, fps) pour la page web.

La page fabrique les images dans le navigateur (docs/mgs-vostfr.js) ; les options sont
des différences d'octets sur l'EXE et STAGE.DIR d'origine, calculées ici avec les mêmes
scripts que build.py. Seuls les octets écrits par nos patchs sont exportés (notre code
MIPS et les instructions modifiées), avec le CRC32 des fichiers d'origine pour vérifier.

Une entrée par disque : FR1, FR2 (France), UK1, UK2 (Europe, anglais). La barre de vie
(--life) n'est que des données : on exporte où écrire (pointeur, zone du texte), la page encode
le texte elle-même comme life.encode(). Une option qu'un
script ne sait pas encore appliquer à une version est simplement absente de cette version
(la page la grise). Les options doivent être additives (la différence de chaque
combinaison = l'union des différences de chaque option) : c'est vérifié.

  python webpatches.py work/FR1.bin work/FR2.bin work/UK1.bin work/UK2.bin   -> docs/patches.js

À relancer après chaque modification d'une option.
"""

import itertools, json, re, sys, zlib
from pathlib import Path

import carre, fps, l2r2, life, m9, pal, psg1, psxiso

ORDER = ["carre", "m9", "psg1", "l2r2", "fps"]  # ordre de build.py
IDS = {"SLES_015.06": "FR1", "SLES_115.06": "FR2", "SLES_013.70": "UK1", "SLES_113.70": "UK2"}
OUT = Path(__file__).resolve().parent.parent / "docs" / "patches.js"


def run(exe, stage, opts):
    if "carre" in opts:
        exe = carre.patch(exe)
    if "m9" in opts:
        exe, stage, _, _ = m9.patch_files(exe, stage)
    if "psg1" in opts:
        exe = psg1.patch(exe)
    if "l2r2" in opts:
        exe = l2r2.patch(exe)
    if "fps" in opts:
        exe = fps.patch(exe)
    if not isinstance(exe, (bytes, bytearray)) or not isinstance(stage, (bytes, bytearray)):
        raise ValueError("version non gérée par le patch")
    return bytes(exe), bytes(stage)


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
        exe_name = next(f for f in files if f in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
        exe0, st0 = disc.read(*files[exe_name]), disc.read(*files["MGS/STAGE.DIR"])
        opts, missing = {}, {}
        for o in ORDER:
            try:
                exe, st = run(exe0, st0, [o])
            except (Exception, SystemExit) as e:  # option pas encore portée sur cette version
                missing[o] = str(e)[:120]
                continue
            opts[o] = {"exe": runs(exe0, exe), "stage": runs(st0, st)}
        have = [o for o in ORDER if o in opts]
        for r in range(2, len(have) + 1):
            for combo in itertools.combinations(have, r):
                exe, st = run(exe0, st0, combo)
                e2, s2 = exe0, st0
                for o in combo:
                    e2, s2 = apply(e2, opts[o]["exe"]), apply(s2, opts[o]["stage"])
                if (e2, s2) != (exe, st):
                    raise SystemExit(f"{ident} : options non additives {combo}")
        discs[ident] = {"exe": exe_name, "exeCrc": zlib.crc32(exe0), "stageCrc": zlib.crc32(st0), "options": opts}
        try:  # barre de vie (--life) : pointeur u32 LE à écrire et zone de 16 octets pour le texte
            conf, zone, zaddr = life.offsets(pal.version(exe0))
            discs[ident]["life"] = [conf, zone, zaddr]
        except (Exception, SystemExit) as e:
            print(f"{ident} : pas de barre de vie ({e})")
        size = sum(len(hx) // 2 for o in opts.values() for k in o.values() for _, hx in k)
        print(f"{ident} : {', '.join(have) or 'aucune option'} ({size} octets)"
              + (f" ; pas encore : {', '.join(missing)}" if missing else ""))
    js = ("// Généré par tools/webpatches.py - ne pas modifier à la main.\n"
          "globalThis.MGS_PATCHES = " + json.dumps({"order": ORDER, "discs": discs}, separators=(",", ":")) + ";\n")
    OUT.write_text(js, encoding="utf-8")
    print(f"-> {OUT} ({len(js)} octets)")


if __name__ == "__main__":
    main()
