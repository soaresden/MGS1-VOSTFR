#!/usr/bin/env python3
"""
mods.py - Les mods du dossier mods/ et les versions du jeu du dossier versions/.

Un mod = un dossier mods/<id>/ :
- mod.json : tout ce qu'il faut savoir sur lui (voir CLAUDE.md) ; pour build.py :
  « type » (option : différences d'octets sur l'EXE et/ou STAGE.DIR ; texte : idem avec un
  texte, la barre de vie ; base : la VOSTFR ; final : sur les images finies, le CD Combiner),
  « ordre » (ordre d'application), « cli » (--<cli> dans build.py), « aide », « versions »
  (versions du jeu gérées, voir versions/) ; pour la page : « rang » (place dans la liste),
  textes fr/en, captures, etc.
- patch.py : patch(f[, texte]) modifie f.exe et/ou f.stage (octets) et renvoie le message
  du journal, ou None s'il n'y a rien à faire.

Une version = versions/<id>.json : numéros des disques (SYSTEM.CNF), nom court, textes de la page.

  python mods.py      -> docs/mods.js (ce que la page affiche ; à relancer après chaque mod.json)
"""

import importlib.util, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "mods.js"


def mods():
    """Tous les mods, dans l'ordre d'application."""
    out = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "mods").glob("*/mod.json"))]
    return sorted(out, key=lambda m: m["ordre"])


def mods_by_id():
    return {m["id"]: m for m in mods()}


def versions():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "versions").glob("*.json"))]


def disc_ids():
    """Numéro du disque (SYSTEM.CNF) -> « FR1 », « UK2 »..."""
    return {serial: v["id"] + d for v in versions() for d, serial in v["disques"].items()}


_loaded = {}


def module(m):
    """mods/<id>/patch.py, chargé une fois."""
    if m["id"] not in _loaded:
        spec = importlib.util.spec_from_file_location(f"mod_{m['id']}", ROOT / "mods" / m["id"] / "patch.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _loaded[m["id"]] = mod
    return _loaded[m["id"]]


class Files:
    """EXE et STAGE.DIR d'un disque, lus seulement si un mod en a besoin."""

    def __init__(self, exe=None, stage=None, read_exe=None, read_stage=None):
        self._exe, self._stage, self._rx, self._rs = exe, stage, read_exe, read_stage
        self.changed = set()

    @property
    def exe(self):
        if self._exe is None:
            self._exe = self._rx()
        return self._exe

    @exe.setter
    def exe(self, v):
        self._exe = v
        self.changed.add("exe")

    @property
    def stage(self):
        if self._stage is None:
            self._stage = self._rs()
        return self._stage

    @stage.setter
    def stage(self, v):
        self._stage = v
        self.changed.add("stage")


def apply(f, chosen, texts=None, log=print):
    """Applique les mods « option » et « texte » choisis (ids) à f, dans l'ordre."""
    texts = texts or {}
    for m in mods():
        if m["id"] not in chosen or m["type"] not in ("option", "texte"):
            continue
        mod = module(m)
        msg = mod.patch(f, texts[m["id"]]) if m["type"] == "texte" else mod.patch(f)
        if msg:
            log("  " + msg)


def page():
    """Ce que la page affiche : versions (base VOSTFR comprise) et mods, rangés."""
    keep = lambda m: {k: v for k, v in m.items() if k not in ("ordre", "cli", "aide", "fichiers")}
    ms = mods()
    base = [dict(keep(m), version=True) for m in ms if m["type"] == "base"]
    vers = [dict(keep(v), version=True) for v in versions()]
    return {"versions": base + vers,
            "mods": sorted((keep(m) for m in ms if m["type"] != "base"), key=lambda m: m["rang"]),
            "ids": disc_ids()}


def main():
    js = ("// Généré par tools/mods.py à partir de mods/*/mod.json et versions/*.json - ne pas modifier à la main.\n"
          "globalThis.MGS_MODS = " + json.dumps(page(), ensure_ascii=False, indent=1) + ";\n")
    OUT.write_text(js, encoding="utf-8")
    print(f"-> {OUT} ({len(js)} octets) : " + ", ".join(m["id"] for m in page()["mods"]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
