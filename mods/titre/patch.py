"""Écran titre « METAL GEAR SOLID - SHADOW FIXES » (code : tools/titre.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import titre


def patch(f):
    f.stage, _ = titre.patch_stage(f.stage)
    return f"STAGE.DIR : écran titre « Shadow Fixes » {titre.VERSION}"
