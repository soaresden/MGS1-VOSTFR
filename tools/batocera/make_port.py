"""make_port.py - Assemble le portage (recomp PC alexbeavs + mods MGS1-VOSTFR) pour Batocera et / ou RetroBat.

    python tools/batocera/make_port.py [--cible batocera|retrobat|tous] [--out DOSSIER] [--sans-disques]

Sorties (dans work/, rien du jeu n'est versionné) :
  batocera : work/batocera/Metal Gear Solid.sh/   -> /userdata/roms/ports/ (\\\\BATOCERA\\share\\roms\\ports)
             bin/aarch64 (Retroid Pocket 5 & co) et bin/x86_64 (PC), le reste commun ; run.sh, padto.keys,
             es_features_mgs.cfg (menu ADVANCED GAME OPTIONS > METAL GEAR SOLID : disque, textes FR, rendu).
  retrobat : work/retrobat/roms/windows/          -> RetroBat\\roms\\windows\\
             « Metal Gear Solid - Disque 1.bat », « ... Disque 2.bat » et le dossier « Metal Gear Solid » (l'exe
             Windows + le même contenu : disc, mods, saves, game.toml, assets).
Entrées :
  work/batocera/bin/<processeur>/, work/batocera/common/   (tools/batocera/build.sh, dans WSL)
  work/recomp/mgs/build-release/                           (exe Windows du recomp, construit sous Windows)
  work/recomp/mgs/disc/   disque 1 USA Rev 1 (cue + bin), SLUS_005.94, SYSTEM.CNF (prepare_disc du recomp)
  work/US2.bin            disque 2 USA Rev 1
  work/psxmod/MGS1-Mods-USA-Disc1.psxmod, ...Disc2.psxmod  (tools/psxmod.py)

Les deux paquets de mods sont installés (mods/installed/<id>/<version>/, comme le fait le lanceur du recomp) ; un
seul est actif à la fois (mods/state.toml) : le lanceur met celui du disque lancé.
"""
import argparse
import os
import re
import shutil
import sys
import zipfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
W = os.path.join(REPO, "work")
HERE = os.path.dirname(os.path.abspath(__file__))
DISC = "Metal Gear Solid (USA) (Disc %d) (Rev 1)"
EXE = "Metal_Gear_Solid_Recompiled"
STATE_VALUES = {"life": {"life_text": "snake"}}  # valeurs par défaut des options (comme le lanceur du PC)


def copy(src, dst):
    """Copie si la cible manque ou diffère (taille / date) ; gros fichiers : lien dur quand c'est possible."""
    if os.path.isdir(src):
        os.makedirs(dst, exist_ok=True)
        for n in os.listdir(src):
            copy(os.path.join(src, n), os.path.join(dst, n))
        return
    if os.path.isfile(dst):
        a, b = os.stat(src), os.stat(dst)
        if a.st_size == b.st_size and int(a.st_mtime) <= int(b.st_mtime):
            return
        os.remove(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.getsize(src) > 64 << 20:
        try:
            os.link(src, dst)
            return
        except OSError:
            pass
    shutil.copy2(src, dst)


def text(name, dst, eol):
    t = open(os.path.join(HERE, name), encoding="utf-8").read()
    with open(dst, "w", encoding="utf-8", newline=eol) as o:
        o.write(t)


def manifest(z):
    t = z.read("manifest.toml").decode("utf-8")
    pid = re.search(r'^id = "([^"]+)"', t, re.M).group(1)
    ver = re.search(r'^version = "([^"]+)"', t, re.M).group(1)
    feats = re.findall(r'^\[\[feature\]\]\s*\nid = "([^"]+)"', t, re.M)
    return pid, ver, feats


def install(pkg, mods):
    with zipfile.ZipFile(pkg) as z:
        pid, ver, feats = manifest(z)
        d = os.path.join(mods, "installed", pid, ver)
        stamp = os.path.join(d, ".source")
        sig = "%d %d" % (os.path.getsize(pkg), int(os.path.getmtime(pkg)))
        if not (os.path.isfile(stamp) and open(stamp).read() == sig):
            if os.path.isdir(d):
                shutil.rmtree(d)
            z.extractall(d)
            open(stamp, "w").write(sig)
    return pid, ver, feats


def state(pid, ver, feats):
    out = ["format_version = 2", "", "[[package]]", 'id = "%s"' % pid, 'version = "%s"' % ver]
    for f in sorted(feats):
        out += ["", "[[feature]]", 'package_id = "%s"' % pid, 'id = "%s"' % f, "enabled = true"]
        if f in STATE_VALUES:
            out.append("[feature.values]")
            out += ['%s = "%s"' % kv for kv in STATE_VALUES[f].items()]
    return "\n".join(out) + "\n"


def game(root, common, discs):
    """Ce qui est commun à toutes les cibles : config du jeu, disques, mods, sauvegardes."""
    os.makedirs(root, exist_ok=True)
    for f in ("game.toml", "assets", "licenses", "psx_game_version.txt"):
        if os.path.exists(os.path.join(common, f)):
            copy(os.path.join(common, f), os.path.join(root, f))
    disc = os.path.join(root, "disc")
    os.makedirs(disc, exist_ok=True)
    src = os.path.join(W, "recomp", "mgs", "disc")
    for f in ("SLUS_005.94", "SYSTEM.CNF"):
        copy(os.path.join(src, f), os.path.join(disc, f))
    if discs:
        for n, b in ((1, os.path.join(src, DISC % 1 + ".bin")), (2, os.path.join(W, "US2.bin"))):
            if not os.path.isfile(b):
                sys.exit("disque %d introuvable : %s" % (n, b))
            copy(b, os.path.join(disc, DISC % n + ".bin"))
            with open(os.path.join(disc, DISC % n + ".cue"), "w", newline="\n") as o:
                o.write('FILE "%s.bin" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n' % (DISC % n))
    mods = os.path.join(root, "mods")
    first = None
    for n in (1, 2):
        pkg = os.path.join(W, "psxmod", "MGS1-Mods-USA-Disc%d.psxmod" % n)
        if not os.path.isfile(pkg):
            sys.exit("paquet introuvable : %s (tools/psxmod.py)" % pkg)
        r = install(pkg, mods)
        first = first or r
    st = os.path.join(mods, "state.toml")
    if not os.path.isfile(st):
        open(st, "w", newline="\n").write(state(*first))
    os.makedirs(os.path.join(root, "saves"), exist_ok=True)


def batocera(out, discs):
    root = os.path.join(out, "batocera", "Metal Gear Solid.sh")
    bins = os.path.join(W, "batocera", "bin")
    archs = [x for x in ("aarch64", "x86_64") if os.path.isfile(os.path.join(bins, x, EXE))]
    if not archs:
        sys.exit("aucun exécutable dans %s : lancer d'abord tools/batocera/build.sh (WSL)" % bins)
    game(root, os.path.join(W, "batocera", "common"), discs)
    for x in archs:
        copy(os.path.join(bins, x), os.path.join(root, "bin", x))
    for f in ("run.sh", "padto.keys", "es_features_mgs.cfg"):
        text(f, os.path.join(root, f), "\n")  # fins de ligne Unix : lu par bash / EmulationStation
    print("batocera :", root, "(" + ", ".join("bin/" + x for x in archs) + ")")


def retrobat(out, discs):
    win = os.path.join(out, "retrobat", "roms", "windows")
    root = os.path.join(win, "Metal Gear Solid")
    rel = os.path.join(W, "recomp", "mgs", "build-release")
    if not os.path.isfile(os.path.join(rel, EXE + ".exe")):
        sys.exit("exe Windows introuvable : %s (construire le recomp sous Windows)" % rel)
    game(root, rel, discs)
    copy(os.path.join(rel, EXE + ".exe"), os.path.join(root, EXE + ".exe"))
    if os.path.isdir(os.path.join(rel, "overlay_toolchain")):  # compile les overlays (sinon : interprétés)
        copy(os.path.join(rel, "overlay_toolchain"), os.path.join(root, "overlay_toolchain"))
    text("retrobat.cmd", os.path.join(root, "retrobat.cmd"), "\r\n")
    for n in (1, 2):
        with open(os.path.join(win, "Metal Gear Solid - Disque %d.bat" % n), "w", newline="\r\n") as o:
            o.write('@echo off\ncall "%%~dp0Metal Gear Solid\\retrobat.cmd" %d\n' % n)
    print("retrobat :", win)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cible", choices=("batocera", "retrobat", "tous"), default="batocera")
    ap.add_argument("--out", default=W)
    ap.add_argument("--sans-disques", action="store_true", help="ne pas copier les disques (on les met soi-même)")
    a = ap.parse_args()
    if a.cible in ("batocera", "tous"):
        batocera(a.out, not a.sans_disques)
    if a.cible in ("retrobat", "tous"):
        retrobat(a.out, not a.sans_disques)


if __name__ == "__main__":
    main()
