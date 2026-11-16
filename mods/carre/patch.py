"""Carré fait défiler les dialogues du Codec (code : tools/carre.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import carre


def patch(f):
    f.exe = carre.patch(f.exe)
    return "EXE : Carré fait défiler le Codec"
