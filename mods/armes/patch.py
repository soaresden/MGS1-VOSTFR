"""Toutes les armes, munitions toujours pleines (mod de test ; code : tools/armes.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import armes


def patch(f):
    new = armes.patch(f.exe)
    if new is None:
        return None
    f.exe = new
    return "EXE : toutes les armes, munitions toujours pleines"
