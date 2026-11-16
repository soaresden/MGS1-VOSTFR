"""CD Combiner : les 2 disques finis en une seule image (code : tools/combine.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import combine


def patch(disc1, disc2, out, log=print):
    combine.combine(disc1, disc2, out, log=log)
