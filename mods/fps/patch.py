"""Tir au SOCOM / M9 en vue subjective (code : tools/fps.py). Après m9, qui vérifie tout le menu de débogage."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import fps


def patch(f):
    f.exe = fps.patch(f.exe)
    return "EXE : tir au SOCOM / M9 en vue subjective"
