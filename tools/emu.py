#!/usr/bin/env python3
"""
emu.py - Pilote PCSX-Redux pour tester une image (harnais Lua emprunté au projet RE1 Hotkey,
pilote emu_drive.lua de ce dépôt).

  python emu.py launch image.cue [--gui]   (en arrière-plan ; --gui garde l'interface,
                                             utile pour changer de disque : File > Open Lid)
  python emu.py cmd "press START 8\\nwait 30\\npress CIRCLE\\nwait 60\\nshot s1" [attente_max_s]
  python emu.py cmd quit

Commandes (exécutées à la suite, « wait N » attend N images) : press BOUTON [images], wait,
shot nom, save nom, load chemin.sstate, dump chemin, quit.
Boutons : START, SELECT, CIRCLE (valider dans MGS PAL), CROSS, UP, DOWN...
Les captures sont écrites en PNG dans work/emu/. Chemin du harnais : variable REDUX_TESTS.
"""

import glob, os, re, subprocess, sys, time
from pathlib import Path

TESTS = Path(os.environ.get("REDUX_TESTS", r"D:\DOCS\Documents\GitHub\Resident Evil 1 Hotkey\tools\emu-tests"))
HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "work" / "emu"


def launch(cue, gui=False):
    OUT.mkdir(parents=True, exist_ok=True)
    exe = glob.glob(str(TESTS.parent / "redux" / "pcsx-redux*.exe"))[0]
    env = dict(os.environ, HARNESS_SCRIPT=str(HERE / "emu_drive.lua"), HARNESS_OUT=str(OUT),
               CMD_FILE=str(OUT / "cmd.txt"))
    args = [exe] + ([] if gui else ["-cli"]) + ["-stdout", "-run", "-iso", str(Path(cue).resolve()),
                                                 "-dofile", str(TESTS / "harness.lua")]
    with open(OUT / "emu.log", "w") as log:
        subprocess.run(args, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=TESTS)


def to_png():
    """Convertit en PNG les captures nouvelles ou modifiées."""
    sys.path.insert(0, str(TESTS))
    from run import rgb555
    from PIL import Image
    for line in (OUT / "log.txt").read_text().splitlines():
        m = re.match(r"SHOT (\S+) (\d+)x(\d+) bpp=(\d)", line)
        if not m:
            continue
        name, w, h, bpp = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        raw, png = OUT / f"{name}.raw", OUT / f"{name}.png"
        if png.exists() and png.stat().st_mtime >= raw.stat().st_mtime:
            continue
        d = raw.read_bytes()
        try:
            im = Image.frombytes("RGB", (w, h), d[:w * h * 3]) if bpp == "1" else rgb555(d, w, h)
            im.save(png)
        except (ValueError, IndexError):
            pass


def cmd(text, wait):
    """Envoie les commandes et attend leur fin (CMDDONE), au plus wait secondes."""
    log = OUT / "log.txt"
    done = log.read_text().count("CMDDONE") if log.exists() else 0
    tmp = OUT / "cmd.tmp"
    tmp.write_text(text.replace("\\n", "\n") + "\n", newline="\n")
    os.replace(tmp, OUT / "cmd.txt")
    end = time.time() + wait
    while time.time() < end and log.read_text().count("CMDDONE") <= done:
        time.sleep(0.5)
    to_png()
    print("".join((OUT / "log.txt").read_text().splitlines(True)[-3:]))


if __name__ == "__main__":
    if sys.argv[1] == "launch":
        launch(sys.argv[2], "--gui" in sys.argv)
    else:
        cmd(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 2)
