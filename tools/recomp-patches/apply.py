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
   - widescreen-x-radar-scope.patch (après les autres : il touche les mêmes fichiers) :
     * radar : une zone de dessin du HUD plus petite que la moitié de l'image, dans un tiers de côté
       (le radar de MGS : zone 235..303 x 16..67, décalage au centre, carte dessinée autour de 0,0) se
       déplace d'un bloc vers son coin, comme son cadre : zone + décalage + test de rejet ; ce qui est
       dessiné dedans n'est plus décalé à part ; la surface large est découpée à la zone déplacée
       (wide_set_view mode 2 : découpe X seule, le centre reste l'image 4:3 ; GL seulement).
     * lunette / jumelles : un quadrilatère noir opaque avec deux sommets sur x = 0 ou x = 320 (le
       masque de la lunette du PSG1 = ~40 trapèzes du cercle au bord) est prolongé dans la bande 16/9
       par un rectangle noir de la hauteur de ce côté. Activé par PSX_WS_EDGE_MASKS=1 (run.sh, retrobat.cmd).
   - widescreen-y-hud-groups.patch (après x-radar-scope, même fonction) : le HUD 16/9 se range par tiers,
     primitive par primitive ; un ensemble à cheval sur deux tiers se coupait (menus L2 / R2 : une rangée de
     5 cases sur tout le bas ; nom d'un objet ramassé, écrit à la position de l'objet). Avant d'envoyer la
     liste, les primitives de la zone du HUD sont regroupées (8 px d'écart au plus) ; un groupe dont les
     morceaux ne sont pas d'accord bouge d'un bloc : vers le bord où il est ancré (à 1/6 de la largeur), sinon
     selon le tiers de son centre. Les groupes plus hauts que la moitié de l'image (écrans 2D) gardent
     l'ancienne règle. Parcours borné (en-têtes seulement, 0x8000 nœuds). PSX_WS_HUD_GROUPS=0 le coupe.
   - runtime-audio-drc-env.patch : PSX_AUDIO_MAX_CORRECTION, PSX_AUDIO_KP, PSX_AUDIO_SLEW règlent la
     correction de vitesse du son (essai : étirer le son au lieu de le hacher quand le jeu ralentit ;
     refusé par Denis, toute la hauteur change ; non utilisé par run.sh).
   - runtime-render-thread-gp1.patch : MGS (libgpu, PutDispEnv) écrit GP1(08h) à chaque image avec la
     même valeur ; gr_display_mode_changed est un point de synchronisation du fil de rendu (GL : le fil
     du jeu prend le contexte jusqu'à la fin de l'image), donc tout le dessin se faisait sur le fil du
     jeu (Retroid : 20-30 images/s dans l'intro, attentes futex dans pack_flush à chaque sprite qui
     relit l'image). Signalé seulement quand la valeur change (oubliée au reset et après restauration).
   - runtime-text-guard-cache.patch : le garde du code (dirty_ram_text_native_ok_ranges_from) recomparait
     à l'image d'origine tout le code d'une fonction à chaque appel dès que sa page avait reçu une
     écriture différente (données voisines du code) : ~6 millions de memcmp par seconde dans MGS,
     surtout les pages 0x8E000-0x8FFFF. Un compteur par page (chaque écriture gardée, bless, écriture
     brute de l'hôte) et un cache par fonction : comparé une fois, puis gardé tant que ses pages ne
     changent pas. Les pages « sales » (DMA, overlays) gardent la comparaison à chaque appel.
   - title-mods-entry.patch + mgs_title_mods.c (copié dans le projet) : une entrée MODS dans le menu
     titre du jeu, entre SPECIAL et VR TRAINING. Le jeu n'est pas modifié : deux fonctions de
     l'overlay « title » sont enveloppées en C (func_override, gardées par leurs octets) : l'état 7
     (curseur, valeur 6 = MODS) et la copie des polygones (MODS emprunte un des 6 polygones hors de
     vue ; le mot est fait avec les lettres du jeu, envoyé dans un coin libre de la VRAM). Rond ou
     START sur MODS ouvre la page Mods du menu en jeu (PSX_MENU_OPEN_MODS) ; en la quittant après un
     changement, le jeu redémarre (à froid) pour l'appliquer.
2. widescreen.toml -> game.toml : vrai 16/9 (native-wide : la 3D est calculée sur toute la largeur,
   pas étirée), détection du jeu par le GTE, et les 26 tests d'écran de MGS élargis (le jeu jette ce
   qui sort de x = -160..160 ; listés à la main, voir le fichier). À 4:3 ces tests restent ceux
   d'origine (marge 0) : le même exécutable sert aux deux formats.
3. Régénère le code C du jeu (psxrecomp-game) : les tests élargis y sont écrits.

Ensuite : compiler (cmake --build build-diagnostic ou build-release ; Batocera : tools/batocera/build.sh,
puis tools/batocera/overlays.sh : le cache des overlays dépend de game.toml).
"""

import pathlib, subprocess, sys, tempfile

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent


def git_apply(proj, patch, *extra):
    return subprocess.run(["git", "apply", "--unsafe-paths", f"--directory={proj.relative_to(REPO).as_posix()}",
                           *extra, str(patch)], cwd=REPO, capture_output=True, text=True)


def patch_files(patch):
    return [l[6:].strip() for l in patch.read_text(encoding="utf-8").splitlines() if l.startswith("+++ b/")]


def already_applied(proj, patches):
    """Patches déjà posés. Ils se superposent (title-mods-entry touche les lignes de ingame-mods-menu) :
    on les retire du dernier au premier sur une copie des fichiers, chacun voit l'état d'avant lui."""
    done = set()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        for patch in patches:
            for f in patch_files(patch):
                if (proj / f).exists() and not (tmp / f).exists():
                    (tmp / f).parent.mkdir(parents=True, exist_ok=True)
                    (tmp / f).write_bytes((proj / f).read_bytes())
        for patch in reversed(patches):
            if subprocess.run(["git", "apply", "--reverse", str(patch)], cwd=tmp,
                              capture_output=True).returncode == 0:
                done.add(patch)
    return done


def main():
    proj = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO / "work" / "recomp" / "mgs"

    # sources C du jeu à nous (title-mods-entry.patch les ajoute à CMakeLists.txt) : toujours recopiées
    for src in ("mgs_title_mods.c",):
        (proj / src).write_bytes((HERE / src).read_bytes())
        print(f"{src} : copié")

    patches = sorted(HERE.glob("*.patch"))
    done = already_applied(proj, patches)
    for patch in patches:
        if patch in done:
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
