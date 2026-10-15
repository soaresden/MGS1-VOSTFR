#!/usr/bin/env python3
"""
build.py - Construit les images VOSTFR de MGS1 PS1 à partir des CHD (ou BIN) FR et UK.

Phase 1 : cinématiques (DEMO.DAT) en anglais sous-titrées en français.

  python build.py --fr1 FR_D1.chd --uk1 UK_D1.chd --fr2 FR_D2.chd --uk2 UK_D2.chd --out sortie

Les fichiers intermédiaires vont dans ./work (ignoré par git).
"""

import argparse, shutil, sys
from pathlib import Path

import chd2bin, demo_vostfr, psxiso
from cdsector import write_file_inplace

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"


def to_bin(src, name):
    """CHD -> BIN dans work/ (réutilisé s'il existe déjà)."""
    src = Path(src)
    if src.suffix.lower() != ".chd":
        return src
    dst = WORK / f"{name}.bin"
    if not dst.exists():
        print(f"Conversion {src.name}...")
        sys.argv = ["chd2bin", str(src), str(dst)]
        chd2bin.main()
    return dst


def build_disc(fr, uk, out_bin):
    fr_disc, uk_disc = psxiso.Disc(fr), psxiso.Disc(uk)
    fr_files, uk_files = fr_disc.files(), uk_disc.files()
    lba, size = fr_files["MGS/DEMO.DAT"]
    demo_fr = fr_disc.read(lba, size)
    demo_uk = uk_disc.read(*uk_files["MGS/DEMO.DAT"])
    demo, nb, swapped = demo_vostfr.patch(demo_fr, demo_uk)
    print(f"  DEMO.DAT : {nb} cinématiques, {swapped} blocs son anglais")
    print(f"  Copie de l'image FR -> {out_bin.name}")
    shutil.copyfile(fr, out_bin)
    write_file_inplace(out_bin, lba, demo)
    out_bin.with_suffix(".cue").write_text(
        f'FILE "{out_bin.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n', encoding="ascii")


def main():
    ap = argparse.ArgumentParser()
    for k in ("fr1", "uk1", "fr2", "uk2"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--out", default=str(WORK / "out"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(exist_ok=True)
    names = []
    for d in ("1", "2"):
        fr, uk = getattr(a, f"fr{d}"), getattr(a, f"uk{d}")
        if not (fr and uk):
            continue
        print(f"Disque {d}")
        out_bin = out / f"Metal Gear Solid (VOSTFR) (Disc {d}).bin"
        build_disc(to_bin(fr, f"FR{d}"), to_bin(uk, f"UK{d}"), out_bin)
        names.append(out_bin.with_suffix(".cue").name)
    if len(names) == 2:
        (out / "Metal Gear Solid (VOSTFR).m3u").write_text("\n".join(names) + "\n", encoding="utf-8")
    print("Terminé :", out)


if __name__ == "__main__":
    main()
