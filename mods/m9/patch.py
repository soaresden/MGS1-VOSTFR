"""M9, PSG1-T et claymores zzz tranquillisants (code : tools/m9.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import m9


def patch(f):
    f.exe, f.stage, stages, _ = m9.patch_files(f.exe, f.stage)
    return f"EXE : M9, PSG1-T et claymores zzz (soldats endormis dans {len(stages)} stages)"
