#!/usr/bin/env python3
"""
build.py - Construit les images VOSTFR de MGS1 PS1 à partir des CHD (ou BIN) FR et UK.

- Cinématiques (DEMO.DAT) : audio anglais recopié dans le DEMO.DAT français.
- Codec et voix en jeu (VOX.DAT) : banques anglaises avec les sous-titres FR, codes VOX
  renumérotés dans RADIO.DAT et STAGE.DIR, image ISO reconstruite (VOX.DAT grossit).

  python build.py --fr1 FR_D1.chd --uk1 UK_D1.chd --fr2 FR_D2.chd --uk2 UK_D2.chd --out sortie [--carre] [--m9] [--psg1] [--l2r2] [--fps] [--life SNAKE]
  python build.py --vf --fr1 FR_D1.chd --fr2 FR_D2.chd --out sortie --m9 ...   (jeu français + options)
  python build.py --vo --uk1 UK_D1.chd --uk2 UK_D2.chd --out sortie --m9 ...   (jeu anglais + options)

--carre : patch optionnel, Carré fait défiler les dialogues du Codec (voir carre.py).
--m9    : patch optionnel, M9, PSG1-T et claymores tranquillisants (voir m9.py).
--psg1  : patch optionnel, PSG1 utilisable debout ou accroupi (voir psg1.py).
--l2r2  : patch optionnel, L2/R2 penchent la vue subjective comme dans MGS2 (voir l2r2.py).
--fps   : patch optionnel, viser et tirer au SOCOM / M9 en vue subjective (voir fps.py).
--life TEXTE : patch optionnel, texte à la place de « LIFE » dans la barre de vie (voir life.py).

Donner les deux disques permet un appariement exact des banques (table de test sonore du
disque 2, reportée sur le disque 1). Les fichiers intermédiaires vont dans ./work (ignoré).
"""

import argparse, sys
from pathlib import Path

import carre, chd2bin, demo_vostfr, fps, isorebuild, l2r2, life, m9, psg1, psxiso, vox_vostfr, voxalign

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


def tables(path):
    """Banques de VOX.DAT et table du test sonore d'une image."""
    return (voxalign.bank_table(read(path, "VOX.DAT"), read(path, "RADIO.DAT")),
            voxalign.sound_test_table(read(path, "STAGE.DIR")))


def build_disc(fr, uk, anchors, fr_tab, uk_tab, out_bin, square=False, tranq=False, rifle=False, lean=False, aim=False, name=None, vf=False):
    """vf : garde les voix françaises (pas de VOSTFR), seulement les options ; uk inutile."""
    rep = {}
    exe = next(f for f in psxiso.Disc(fr).files() if f in ("MGS/MGS1.EXE", "MGS/MGS2.EXE"))
    if square:
        rep[exe] = carre.patch(read(fr, exe[4:]))
        print(f"  {exe[4:]} : Carré fait défiler le Codec")
    if not vf:
        vostfr(fr, uk, anchors, fr_tab, uk_tab, rep)
    if tranq:
        rep[exe], rep["MGS/STAGE.DIR"], stages, _ = m9.patch_files(
            rep.get(exe) or read(fr, exe[4:]), rep.get("MGS/STAGE.DIR") or read(fr, "STAGE.DIR"))
        print(f"  {exe[4:]} : M9, PSG1-T et claymores zzz (soldats endormis dans {len(stages)} stages)")
    if rifle:  # après m9 (qui vérifie tout le menu de débogage)
        rep[exe] = psg1.patch(rep.get(exe) or read(fr, exe[4:]))
        print(f"  {exe[4:]} : PSG1 debout ou accroupi")
    if lean:
        rep[exe] = l2r2.patch(rep.get(exe) or read(fr, exe[4:]))
        print(f"  {exe[4:]} : L2/R2 penchent la vue subjective")
    if aim:  # après m9 (qui vérifie tout le menu de débogage)
        rep[exe] = fps.patch(rep.get(exe) or read(fr, exe[4:]))
        print(f"  {exe[4:]} : tir au SOCOM / M9 en vue subjective")
    if name:
        new = life.patch(rep.get(exe) or read(fr, exe[4:]), name)
        if new is not None:
            rep[exe] = new
            print(f"  {exe[4:]} : barre de vie « {life.clean(name)} »")

    print(f"  Image -> {out_bin.name}")
    new = isorebuild.rebuild(fr, out_bin, rep)
    print(f"  ZMOVIE.STR -> LBA {new['MGS/ZMOVIE.STR'][0]}, DUMMY3M.DAT -> LBA {new['DUMMY3M.DAT'][0]}")
    out_bin.with_suffix(".cue").write_text(
        f'FILE "{out_bin.name}" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n', encoding="ascii")


def vostfr(fr, uk, anchors, fr_tab, uk_tab, rep):
    """Cinématiques, VOX.DAT, RADIO.DAT et STAGE.DIR en VOSTFR (dans rep)."""
    demo, nb, swapped = demo_vostfr.patch(read(fr, "DEMO.DAT"), read(uk, "DEMO.DAT"))
    rep["MGS/DEMO.DAT"] = demo
    del demo
    print(f"  DEMO.DAT : {nb} cinématiques, {swapped} blocs son anglais")

    radio_fr, radio_uk = read(fr, "RADIO.DAT"), read(uk, "RADIO.DAT")
    mapping = voxalign.align(fr_tab, uk_tab, anchors, radio_fr, radio_uk)
    alone = [i for i in range(len(fr_tab)) if i not in mapping]
    print(f"  VOX.DAT : {len(mapping)}/{len(fr_tab)} banques appariées (FR seules : {alone})")
    new_vox, secmap, kept = vox_vostfr.build_vox(read(fr, "VOX.DAT"), read(uk, "VOX.DAT"), mapping)
    rep["MGS/VOX.DAT"] = new_vox
    print(f"  VOX.DAT : {len(new_vox) // 2048} secteurs, {kept} banque(s) gardée(s) en français")

    rep["MGS/RADIO.DAT"], n = vox_vostfr.renumber_radio(radio_fr, secmap)
    print(f"  RADIO.DAT : {n} commandes VOICE renumérotées")
    fr_to_uk = {fr_tab[a]["sec"]: uk_tab[b]["sec"] for a, b in mapping.items()}
    rep["MGS/STAGE.DIR"], done, skipped = vox_vostfr.renumber_stage(
        read(fr, "STAGE.DIR"), read(uk, "STAGE.DIR"), secmap, fr_to_uk)
    print(f"  STAGE.DIR : {done} codes VOX renumérotés ({skipped} faux positifs ignorés)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    for k in ("fr1", "uk1", "fr2", "uk2"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--out", default=str(WORK / "out"))
    ap.add_argument("--carre", action="store_true", help="Carré fait défiler les dialogues du Codec")
    ap.add_argument("--m9", action="store_true", help="M9, PSG1-T et claymores tranquillisants")
    ap.add_argument("--psg1", action="store_true", help="PSG1 utilisable debout ou accroupi")
    ap.add_argument("--l2r2", action="store_true", help="L2/R2 penchent la vue subjective (comme MGS2)")
    ap.add_argument("--fps", action="store_true", help="viser et tirer au SOCOM / M9 en vue subjective")
    ap.add_argument("--life", metavar="TEXTE", help="texte à la place de « LIFE » dans la barre de vie (ex. SNAKE)")
    ap.add_argument("--vf", action="store_true", help="jeu français d'origine + options seulement (--uk1/--uk2 inutiles)")
    ap.add_argument("--vo", action="store_true", help="jeu anglais (Europe) d'origine + options seulement (--fr1/--fr2 inutiles)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(exist_ok=True)
    if a.life:
        life.clean(a.life)  # erreur tout de suite si le texte ne passe pas
    opts = (a.carre, a.m9, a.psg1, a.l2r2, a.fps, a.life)
    if a.vf or a.vo:  # jeu d'origine + options, sans VOSTFR
        if not any(opts):
            raise SystemExit("--vf / --vo sans option : rien à faire")
        side, tag = ("fr", "VF") if a.vf else ("uk", "EN")
        names = []
        for d in ("1", "2"):
            if not getattr(a, f"{side}{d}"):
                continue
            print(f"Disque {d}")
            out_bin = out / f"Metal Gear Solid ({tag}) (Disc {d}).bin"
            build_disc(to_bin(getattr(a, f"{side}{d}"), f"{side.upper()}{d}"), None, None, None, None, out_bin, *opts, vf=True)
            names.append(out_bin.with_suffix(".cue").name)
        if len(names) == 2:
            (out / f"Metal Gear Solid ({tag}).m3u").write_text("\n".join(names) + "\n", encoding="utf-8")
        print("Terminé :", out)
        return
    imgs = {d: (to_bin(getattr(a, f"fr{d}"), f"FR{d}"), to_bin(getattr(a, f"uk{d}"), f"UK{d}"))
            for d in ("1", "2") if getattr(a, f"fr{d}") and getattr(a, f"uk{d}")}
    print("Appariement des banques VOX...")
    tab = {(d, k): tables(p) for d, pair in imgs.items() for k, p in zip("FU", pair)}
    anchors = {d: {} for d in imgs}
    if "2" in imgs:
        (f2, names_fr), (u2, names_uk) = tab["2", "F"], tab["2", "U"]
        anchors["2"] = voxalign.anchors_disc2(f2, u2, names_fr, names_uk)
        if "1" in imgs:
            anchors["1"] = voxalign.anchors_disc1(tab["1", "F"][0], tab["1", "U"][0], f2, u2, anchors["2"])
    names = []
    for d, (fr, uk) in imgs.items():
        print(f"Disque {d}")
        out_bin = out / f"Metal Gear Solid (VOSTFR) (Disc {d}).bin"
        build_disc(fr, uk, anchors[d], tab[d, "F"][0], tab[d, "U"][0], out_bin, *opts)
        names.append(out_bin.with_suffix(".cue").name)
    if len(names) == 2:
        (out / "Metal Gear Solid (VOSTFR).m3u").write_text("\n".join(names) + "\n", encoding="utf-8")
    print("Terminé :", out)


if __name__ == "__main__":
    main()
