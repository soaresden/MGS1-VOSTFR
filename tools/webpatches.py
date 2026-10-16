#!/usr/bin/env python3
"""
webpatches.py - Exporte les options (carre, m9, psg1, l2r2, fps) pour la page web.

La page fabrique les images VOSTFR dans le navigateur (docs/mgs-vostfr.js) ; les options
sont des différences d'octets sur l'EXE et STAGE.DIR français, calculées ici avec les
mêmes scripts que build.py. Seuls les octets écrits par nos patchs sont exportés (notre
code MIPS et les instructions modifiées), avec le CRC32 du fichier d'origine pour vérifier.

Les options doivent être additives (la différence de chaque combinaison = l'union des
différences de chaque option) : c'est vérifié pour toutes les combinaisons.

  python webpatches.py work/FR1.bin work/FR2.bin     -> docs/patches.js

À relancer après chaque modification d'une option.
"""

import itertools, json, sys, zlib
from pathlib import Path

import carre, fps, l2r2, m9, psg1, psxiso

ORDER = ["carre", "m9", "psg1", "l2r2", "fps"]  # ordre de build.py
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
    return exe, stage


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
        exe_name = next(f for f in files if f in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
        n = exe_name[7]
        exe0, st0 = disc.read(*files[exe_name]), disc.read(*files["MGS/STAGE.DIR"])
        opts = {}
        for o in ORDER:
            exe, st = run(exe0, st0, [o])
            opts[o] = {"exe": runs(exe0, exe), "stage": runs(st0, st)}
        for r in range(2, len(ORDER) + 1):
            for combo in itertools.combinations(ORDER, r):
                exe, st = run(exe0, st0, combo)
                e2, s2 = exe0, st0
                for o in combo:
                    e2, s2 = apply(e2, opts[o]["exe"]), apply(s2, opts[o]["stage"])
                if (e2, s2) != (exe, st):
                    raise SystemExit(f"disque {n} : options non additives {combo}")
        discs[n] = {"exe": exe_name, "exeCrc": zlib.crc32(exe0), "stageCrc": zlib.crc32(st0), "options": opts}
        size = sum(len(hx) // 2 for o in opts.values() for k in o.values() for _, hx in k)
        print(f"disque {n} : {size} octets de patch")
    js = ("// Généré par tools/webpatches.py - ne pas modifier à la main.\n"
          "globalThis.MGS_PATCHES = " + json.dumps({"order": ORDER, "discs": discs}, separators=(",", ":")) + ";\n")
    OUT.write_text(js, encoding="utf-8")
    print(f"-> {OUT} ({len(js)} octets)")


if __name__ == "__main__":
    main()
