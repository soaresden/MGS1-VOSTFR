"""L2/R2 penchent la vue subjective (code : tools/l2r2.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import l2r2


def patch(f):
    f.exe = l2r2.patch(f.exe)
    return "EXE : L2/R2 penchent la vue subjective"
