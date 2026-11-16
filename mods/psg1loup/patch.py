"""PSG1 dans la grotte, là où Meryl attendait (code : tools/psg1loup.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import psg1loup


def patch(f):
    f.stage, _ = psg1loup.patch_stage(f.stage)
    return "STAGE.DIR : PSG1 dans la grotte, là où Meryl attendait"
