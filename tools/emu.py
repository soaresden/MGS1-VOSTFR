#!/usr/bin/env python3
"""
emu.py - Pilote PCSX-Redux pour tester une image (réutilise le harnais Lua du projet RE1 Hotkey).

  python emu.py launch image.cue        (en arrière-plan)
  python emu.py cmd "press START 8\\nshot s1" [attente_s]
  python emu.py cmd quit

Boutons : START, SELECT, CIRCLE (valider dans MGS PAL), CROSS, UP, DOWN...
Les captures sont écrites en PNG dans work/emu/. Chemin du harnais : variable REDUX_TESTS.
"""

import glob, os, subprocess, sys, time
from pathlib import Path

TESTS = Path(os.environ.get("REDUX_TESTS", r"D:\DOCS\Documents\GitHub\Resident Evil 1 Hotkey\tools\emu-tests"))
OUT = Path(__file__).resolve().parent.parent / "work" / "emu"


def launch(cue):
    OUT.mkdir(parents=True, exist_ok=True)
    exe = glob.glob(str(TESTS.parent / "redux" / "pcsx-redux*.exe"))[0]
    env = dict(os.environ, HARNESS_SCRIPT=str(TESTS / "drive.lua"), HARNESS_OUT=str(OUT),
               CMD_FILE=str(OUT / "cmd.txt"), MOVIE_PATCH="0")
    with open(OUT / "emu.log", "w") as log:
        subprocess.run([exe, "-cli", "-stdout", "-run", "-iso", str(Path(cue).resolve()),
                        "-dofile", str(TESTS / "harness.lua")], env=env, stdout=log,
                       stderr=subprocess.STDOUT, cwd=TESTS)


def cmd(text, wait):
    sys.path.insert(0, str(TESTS))
    from run import to_png
    tmp = OUT / "cmd.tmp"
    tmp.write_text(text.replace("\\n", "\n") + "\n", newline="\n")
    os.replace(tmp, OUT / "cmd.txt")
    time.sleep(wait)
    to_png(str(OUT))
    print("".join((OUT / "log.txt").read_text().splitlines(True)[-4:]))


if __name__ == "__main__":
    if sys.argv[1] == "launch":
        launch(sys.argv[2])
    else:
        cmd(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 2)
