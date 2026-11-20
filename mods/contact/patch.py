"""Toucher un garde ne donne plus l'alerte : il faut qu'il voie Snake (code : tools/contact.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import contact


def patch(f):
    f.stage, n, names = contact.patch_stage(f.stage)
    return f"STAGE.DIR : toucher un garde ne donne plus l'alerte ({n} soldats, {len(names)} stages)"
