#!/usr/bin/env python3
"""
apply.py - Nos changements au recomp PC de MGS (psxrecomp + recomp-ui, alexbeavs), avant de le compiler.

  python tools/recomp-patches/apply.py [projet recomp]      (par défaut work/recomp/mgs)

1. Les correctifs *.patch de ce dossier (chemins relatifs au projet recomp ; déjà appliqués : sautés) :
   - ingame-mods-menu.patch : une page « Mods » dans le menu du jeu (Select + L3, ou F1) : chaque mod
     installé s'active ou se coupe, enregistré dans mods/state.toml, effectif au prochain lancement
     (le menu des mods du lanceur n'existe pas avec --no-launcher, donc pas sur Batocera ni RetroBat).
     L'hôte du menu (psx_menu_host.h) donne en plus le catalogue des mods (mod_catalog), lu une fois
     à l'attache (fil principal) ; les changements passent par mod_set, comme avant.
   - widescreen-fullscreen-fades.patch : les fondus et filtres plein écran de MGS sont dessinés en
     coordonnées centrées (-160,-112 320x224) ; le runtime ne les élargissait en 16/9 que s'ils
     partaient de 0, ils gardaient donc des bandes 4:3.
   - widescreen-underwater-filter.patch : les filtres de l'intro (sous l'eau, crédits « David Hayter »)
     recopient l'image comme texture : ~450 sprites de 2 lignes qui la redessinent sur elle-même,
     ondulée et teintée, plus 4 quads qui mélangent l'image précédente. Ces recopies continuent
     maintenant dans les bandes 16/9 (lues dans les bandes seulement ; en OpenGL, un instantané
     de la surface quand la source est celle qu'on dessine ; dessinées en bloc à la fin de la série).
     Activé par PSX_WS_FEEDBACK_QUADS=1 (run.sh, retrobat.cmd).
   - runtime-audio-drc-env.patch : PSX_AUDIO_MAX_CORRECTION, PSX_AUDIO_KP, PSX_AUDIO_SLEW règlent la
     correction de vitesse du son (essai : étirer le son au lieu de le hacher quand le jeu ralentit ;
     refusé par Denis, toute la hauteur change ; non utilisé par run.sh).
   - runtime-text-guard-cache.patch : le garde du code (dirty_ram_text_native_ok_ranges_from) recomparait
     à l'image d'origine tout le code d'une fonction à chaque appel dès que sa page avait reçu une
     écriture différente (données voisines du code) : ~6 millions de memcmp par seconde dans MGS,
     surtout les pages 0x8E000-0x8FFFF. Un compteur par page (chaque écriture gardée, bless, écriture
     brute de l'hôte) et un cache par fonction : comparé une fois, puis gardé tant que ses pages ne
     changent pas. Les pages « sales » (DMA, overlays) gardent la comparaison à chaque appel.
2. widescreen.toml -> game.toml : vrai 16/9 (native-wide : la 3D est calculée sur toute la largeur,
   pas étirée), détection du jeu par le GTE, et les 26 tests d'écran de MGS élargis (le jeu jette ce
   qui sort de x = -160..160 ; listés à la main, voir le fichier). À 4:3 ces tests restent ceux
   d'origine (marge 0) : le même exécutable sert aux deux formats.
3. Régénère le code C du jeu (psxrecomp-game) : les tests élargis y sont écrits.

Ensuite : compiler (cmake --build build-diagnostic ou build-release ; Batocera : tools/batocera/build.sh,
puis tools/batocera/overlays.sh : le cache des overlays dépend de game.toml).
"""

import pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent


def git_apply(proj, patch, *extra):
    return subprocess.run(["git", "apply", "--unsafe-paths", f"--directory={proj.relative_to(REPO).as_posix()}",
                           *extra, str(patch)], cwd=REPO, capture_output=True, text=True)


def patch_files(patch):
    return [l[6:].strip() for l in patch.read_text(encoding="utf-8").splitlines() if l.startswith("+++ b/")]


def main():
    proj = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO / "work" / "recomp" / "mgs"

    for patch in sorted(HERE.glob("*.patch")):
        if git_apply(proj, patch, "--check", "--reverse").returncode == 0:
            print(f"{patch.name} : déjà appliqué")
            continue
        files = patch_files(patch)
        lf = {f: b"\r\n" not in (proj / f).read_bytes() for f in files}
        r = git_apply(proj, patch)
        if r.returncode:
            raise SystemExit(f"{patch.name} : ne s'applique pas (version du recomp différente ?)\n{r.stderr}")
        for f, keep_lf in lf.items():   # git (core.autocrlf) écrit en CRLF : on garde les fins de ligne
            if keep_lf:
                p = proj / f
                p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n"))
        print(f"{patch.name} : appliqué")

    toml = proj / "game.toml"
    s = toml.read_text(encoding="utf-8")
    if "\n[widescreen]" in s:
        s = s[:s.index("\n[widescreen]")]
    s = s.rstrip("\n") + "\n\n" + (HERE / "widescreen.toml").read_text(encoding="utf-8")
    toml.write_text(s, encoding="utf-8", newline="\n")
    print(f"{toml} : [widescreen] à jour")

    fw = proj / "psxrecomp"
    exe = fw / "recompiler" / "build" / ("psxrecomp-game.exe" if sys.platform == "win32" else "psxrecomp-game")
    subprocess.run([str(exe), "--config", "game.toml"], cwd=proj, check=True, stdout=subprocess.DEVNULL)
    n = sum(p.read_text(encoding="utf-8", errors="replace").count("psx_ws_cull_")
            for p in (proj / "generated").glob("*_full_*.c"))
    print(f"code régénéré : {n} tests d'écran élargis")


if __name__ == "__main__":
    main()
