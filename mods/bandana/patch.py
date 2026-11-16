"""Bandana visible, pans très longs (code : tools/bandana.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import bandana


def patch(f):
    f.exe = bandana.patch(f.exe)
    return "EXE : bandana visible (pans très longs)"
