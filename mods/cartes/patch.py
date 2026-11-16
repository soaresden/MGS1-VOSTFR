"""Portes à carte sans équiper la carte (code : tools/cartes.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import cartes


def patch(f):
    f.stage, n = cartes.patch_stage(f.stage)
    return f"STAGE.DIR : {n} portes à carte s'ouvrent sans équiper la carte"
