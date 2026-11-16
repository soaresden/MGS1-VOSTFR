#!/usr/bin/env python3
"""
build.py - Construit les images de MGS1 PS1 à partir des CHD (ou BIN) : VOSTFR et/ou mods.

VOSTFR (mods/vostfr) : textes du disque français, voix du disque européen (anglais).
- Cinématiques (DEMO.DAT) : audio anglais recopié dans le DEMO.DAT français.
- Codec et voix en jeu (VOX.DAT) : banques anglaises avec les sous-titres FR, codes VOX
  renumérotés dans RADIO.DAT et STAGE.DIR, image ISO reconstruite (VOX.DAT grossit).

Les mods sont les dossiers de mods/ (voir tools/mods.py) : chacun ajoute son option --<cli>,
appliquée dans l'ordre de son mod.json. « python build.py -h » les liste.

  python build.py --fr1 FR_D1.chd --uk1 UK_D1.chd --fr2 FR_D2.chd --uk2 UK_D2.chd --out sortie [--carre] [--m9] [--life SNAKE] ...
  python build.py --jeu FR --fr1 FR_D1.chd --fr2 FR_D2.chd --out sortie --m9 ...   (jeu français + mods ; --vf pareil)
  python build.py --jeu UK --uk1 UK_D1.chd --uk2 UK_D2.chd --out sortie --m9 ...   (jeu anglais + mods ; --vo pareil)

--combine : en plus des 2 disques, une image unique « (1 CD) » pour émulateurs (mods/combine,
            son allégé pour tenir sous 99 minutes, pas de changement de disque).

Donner les deux disques permet un appariement exact des banques (table de test sonore du
disque 2, reportée sur le disque 1). Les fichiers intermédiaires vont dans ./work (ignoré).
"""

import argparse, sys
from pathlib import Path

import chd2bin, isorebuild, mods, psxiso

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


def read(path, name):
    d = psxiso.Disc(path)
    return d.read(*d.files()[f"MGS/{name}"])


def build_disc(fr, out_bin, chosen, texts, base=None):
    """Une image : la VOSTFR si base = (uk, ctx), puis les mods choisis (mods/, dans l'ordre)."""
    rep = {}
    exe = next(f for f in psxiso.Disc(fr).files() if f in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
    if base:
        uk, ctx = base
        mods.module(VOSTFR).patch(fr, uk, ctx, rep, exe == "MGS/MGS2.EXE", read)
    f = mods.Files(rep.get(exe), rep.get("MGS/STAGE.DIR"), lambda: read(fr, exe[4:]), lambda: read(fr, "STAGE.DIR"))
    mods.apply(f, chosen, texts)
    if "exe" in f.changed:
        rep[exe] = f.exe
    if "stage" in f.changed:
        rep["MGS/STAGE.DIR"] = f.stage

    print(f"  Image -> {out_bin.name}")
    new = isorebuild.rebuild(fr, out_bin, rep)
    print(f"  ZMOVIE.STR -> LBA {new['MGS/ZMOVIE.STR'][0]}, DUMMY3M.DAT -> LBA {new['DUMMY3M.DAT'][0]}")
    out_bin.with_suffix(".cue").write_text(
        f'FILE "{out_bin.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n', encoding="ascii")


VOSTFR = next(m for m in mods.mods() if m["type"] == "base")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    vers = {v["id"]: v for v in mods.versions()}
    ap = argparse.ArgumentParser()
    for v in vers:
        for d in ("1", "2"):
            ap.add_argument(f"--{v.lower()}{d}", metavar="CHD/BIN", help=f"disque {d}, version {v} ({vers[v]['disques'][d]})")
    ap.add_argument("--out", default=str(WORK / "out"))
    ap.add_argument("--jeu", choices=sorted(vers), help="jeu d'origine + mods seulement, sans VOSTFR")
    ap.add_argument("--vf", action="store_const", dest="jeu", const="FR", help="= --jeu FR (jeu français + mods)")
    ap.add_argument("--vo", action="store_const", dest="jeu", const="UK", help="= --jeu UK (jeu anglais + mods)")
    for m in mods.mods():
        if m["type"] == "texte":
            ap.add_argument(f"--{m['cli']}", metavar="TEXTE", help=m["aide"])
        elif m.get("cli"):
            ap.add_argument(f"--{m['cli']}", action="store_true", help=m["aide"])
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(exist_ok=True)
    chosen, texts, final = [], {}, []
    for m in mods.mods():
        val = getattr(a, m["cli"], None) if m.get("cli") else None
        if not val:
            continue
        if m["type"] == "final":
            final.append(m)
            continue
        if m["type"] == "texte":
            mods.module(m).check(val)  # erreur tout de suite si le texte ne passe pas
            texts[m["id"]] = val
        chosen.append(m["id"])
    disc = lambda v, d: getattr(a, f"{v.lower()}{d}")

    if a.jeu:  # jeu d'origine + mods, sans VOSTFR
        if not chosen and not final:
            raise SystemExit(f"--jeu {a.jeu} sans mod : rien à faire")
        tag = vers[a.jeu]["nomCourt"]
        for m in chosen:
            if a.jeu not in mods.mods_by_id()[m]["versions"]:
                raise SystemExit(f"--{m} : pas encore disponible pour la version {a.jeu}")
        names = []
        for d in ("1", "2"):
            if not disc(a.jeu, d):
                continue
            print(f"Disque {d}")
            out_bin = out / f"Metal Gear Solid ({tag}) (Disc {d}).bin"
            build_disc(to_bin(disc(a.jeu, d), f"{a.jeu}{d}"), out_bin, chosen, texts)
            names.append(out_bin.with_suffix(".cue").name)
        finish(out, tag, names, final)
        return

    src, dst = VOSTFR["versions"][0], VOSTFR["besoin"][1]  # textes FR, voix UK
    imgs = {d: (to_bin(disc(src, d), f"{src}{d}"), to_bin(disc(dst, d), f"{dst}{d}"))
            for d in ("1", "2") if disc(src, d) and disc(dst, d)}
    ctx = mods.module(VOSTFR).prepare(imgs, read)
    names = []
    for d, (fr, uk) in imgs.items():
        print(f"Disque {d}")
        out_bin = out / f"Metal Gear Solid (VOSTFR) (Disc {d}).bin"
        build_disc(fr, out_bin, chosen, texts, (uk, ctx[d]))
        names.append(out_bin.with_suffix(".cue").name)
    finish(out, "VOSTFR", names, final)


def finish(out, tag, names, final):
    """.m3u des 2 disques, puis les mods « final » (CD Combiner : « Metal Gear Solid (TAG) (1 CD).bin »)."""
    if len(names) == 2:
        (out / f"Metal Gear Solid ({tag}).m3u").write_text("\n".join(names) + "\n", encoding="utf-8")
        for m in final:
            print(m["fr"])
            mods.module(m).patch(out / f"Metal Gear Solid ({tag}) (Disc 1).bin", out / f"Metal Gear Solid ({tag}) (Disc 2).bin",
                                 out / f"Metal Gear Solid ({tag}) (1 CD).bin", log=lambda s: print("  " + s))
    print("Terminé :", out)


if __name__ == "__main__":
    main()
