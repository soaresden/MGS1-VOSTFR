"""Tous les objets, rations et médicaments toujours pleins (mod de test ; code : tools/objets.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import objets


def patch(f):
    new = objets.patch(f.exe)
    if new is None:
        return None
    f.exe = new
    return "EXE : tous les objets, rations et médicaments toujours pleins"
