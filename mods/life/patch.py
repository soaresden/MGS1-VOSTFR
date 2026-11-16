"""Texte de la barre de vie à la place de LIFE (code : tools/life.py)."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import life


def patch(f, text):
    new = life.patch(f.exe, text)
    if new is None:
        return None
    f.exe = new
    return f"EXE : barre de vie « {life.clean(text)} »"


def check(text):
    """Erreur tout de suite si le texte ne passe pas dans la police du jeu."""
    life.clean(text)


def web(exe):
    """Pour la page (webpatches.py) : [pointeur u32 LE à écrire, zone de 16 octets du texte, adresse de la zone]."""
    import pal
    return list(life.offsets(pal.version(exe)))
