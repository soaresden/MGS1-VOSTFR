"""PSG1 debout ou accroupi (code : tools/psg1.py). Après m9, qui vérifie tout le menu de débogage."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import psg1


def patch(f):
    f.exe = psg1.patch(f.exe)
    return "EXE : PSG1 debout ou accroupi"
