#!/usr/bin/env python3
"""
psxmod.py - Nos mods en paquets .psxmod pour le recomp PC de MGS1 (alexbeavs-ps1-ports/
metal-gear-solid-recomp, moteur psxrecomp), qui tourne sur les disques USA (Rev 1) d'origine.

Le recomp ne lit pas d'image modifiée : il veut le disque d'origine intact et applique les
mods à la volée, d'après un manifeste (format psxrecomp, docs/MOD_PACKAGES.md) :
- différences de l'EXE -> [[patch]] target = "main_exe" (adresse en RAM, octets d'origine
  vérifiés avant d'écrire), appliquées une fois, avant le point d'entrée de l'EXE ;
- différences de STAGE.DIR -> [[patch]] target = "disc_user" (LBA * 2048 + octet, sans
  déborder d'un secteur), ou [[overlay]] (fichier) pour les longs morceaux ; vérifiés aussi.

Un mod de mods/ = une « feature » (case à cocher du lanceur). La barre de vie (texte libre
ailleurs) devient un choix entre quelques textes.

Un paquet par disque : le recomp ne résout les mods que pour le disque monté au lancement
(STAGE.DIR n'est pas au même endroit sur les deux disques ; un patch du disque 1 lu sur le
disque 2 coupe tous les patches disque). Les deux EXE USA sont identiques, donc les patches
d'EXE sont les mêmes. Après le changement de disque en jeu, il faut sauvegarder et relancer
le recomp avec le disque 2 pour retrouver les mods.

  python psxmod.py --us1 work/US1.bin --us2 work/US2.bin [--out work/psxmod]
      -> work/psxmod/MGS1-Mods-USA-Disc1.psxmod, MGS1-Mods-USA-Disc2.psxmod
      à copier dans le dossier du recomp (bouton d'installation de mods du lanceur, ou
      <dossier du jeu>/mods/installed/), puis cocher les mods voulus dans le lanceur.

Les paquets ne vont pas dans le dépôt : les gardes « expected » sont des octets du jeu
d'origine (la règle du dépôt : aucune donnée du jeu). Chacun les fabrique depuis ses disques.

Les disques doivent être les dumps Redump (SHA-1 vérifié) : disc_sha256 = SHA-256 du BIN.
"""

import argparse, hashlib, io, json, re, sys, zipfile
from pathlib import Path

import mods, psxiso

ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"
GAME_ID = "SLUS-00594"          # id du recomp (game.toml), le même avec le disque 2 monté
REDUMP_SHA1 = {"1": "37498e6598ce4eabf00630b6a9197b20861e55a0",
               "2": "d6edfd60a375c10087eacebd709419950c8995ad"}
GAP = 8                          # deux différences à moins de 8 octets = un seul patch
OVERLAY_MIN = 1024               # au-delà : [[overlay]] (fichier) au lieu d'un patch hexadécimal
LIFE_CHOICES = ["SNAKE", "SOLID SNAKE", "FOXHOUND", "VIE"]
GROUPS = {"carre": "Codec", "titre": "Presentation", "life": "Presentation", "bandana": "Presentation"}


def runs(a, b, gap=GAP):
    """Plages [début, fin) où a et b diffèrent, rapprochées si l'écart est petit."""
    out = []
    i, n = 0, len(a)
    while i < n:
        if a[i] == b[i]:
            i += 1
            continue
        j = i
        while j < n and a[j] != b[j]:
            j += 1
        if out and i - out[-1][1] <= gap:
            out[-1][1] = j
        else:
            out.append([i, j])
        i = j
    return out


def toml_str(s):
    return json.dumps(s, ensure_ascii=False)


def hexb(b):
    return " ".join(f"{x:02x}" for x in b)


def text(html):
    return re.sub(r"<[^>]+>", "", html)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while c := f.read(1 << 24):
            h.update(c)
    return h.hexdigest()


def sha1_file(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        while c := f.read(1 << 24):
            h.update(c)
    return h.hexdigest()


def build_variant(exe0, st0, mid, texts):
    f = mods.Files(bytearray(exe0), bytearray(st0))
    mods.apply(f, [mid], texts, log=lambda s: None)
    if len(f.exe) != len(exe0) or len(f.stage) != len(st0):
        raise SystemExit(f"{mid} : la taille de l'EXE ou de STAGE.DIR change, impossible en .psxmod")
    return bytes(f.exe), bytes(f.stage)


class Package:
    def __init__(self, d, sha):
        self.d, self.sha = d, sha
        self.lines, self.files = [], {}
        self.count = {"main_exe": 0, "disc_user": 0, "overlay": 0}

    def head(self):
        d = self.d
        self.lines += [
            "# Généré par tools/psxmod.py (dépôt soaresden/MGS1-VOSTFR) - ne pas modifier à la main.",
            "format_version = 10",
            f'id = "soaresden.mgs1-mods.disc{d}"',
            f'version = "{VERSION}"',
            f'name = {toml_str(f"MGS1 VOSTFR project mods (USA disc {d})")}',
            'author = "soaresden"',
            "description = " + toml_str(
                f"Mods from github.com/soaresden/MGS1-VOSTFR for the USA (Rev 1) disc {d}. "
                f"Active when disc {d} is the mounted disc at launch: after the in-game disc change, "
                "save and relaunch with the other disc. / Mods du projet MGS1-VOSTFR pour le disque "
                f"{d} USA (Rev 1) : actifs quand le disque {d} est monté au lancement ; après le "
                "changement de disque, sauvegarder et relancer."),
            'resolver = "declarative"',
            'save_compatibility = "shared"',
            "",
            "[[target]]",
            f'game_id = "{GAME_ID}"',
            f'disc_sha256 = "{self.sha}"',
            "",
        ]

    def feature(self, m):
        self.lines += [
            "[[feature]]",
            f'id = "{m["id"]}"',
            f"name = {toml_str(m['en'])}",
            "description = " + toml_str(text(m["enS"]) + " / " + text(m["frS"])),
            f'group = "{GROUPS.get(m["id"], "Gameplay")}"',
            "default_enabled = false",
            "",
        ]

    def exe_patches(self, mid, a, b, when=None):
        for s, e in runs(a, b):
            if s < 0x800:
                raise SystemExit(f"{mid} : l'en-tête de l'EXE change")
            self.patch(mid, "main_exe", f"address = 0x{0x80010000 + s - 0x800:08X}", a[s:e], b[s:e], when)

    def stage_patches(self, mid, lba, a, b, when=None):
        base = lba * 2048
        for s, e in runs(a, b):
            if e - s >= OVERLAY_MIN:
                name = f"payload/{mid}/{base + s:010d}.bin"
                self.files[name] = b[s:e]
                self.lines += [
                    "[[overlay]]",
                    f'feature = "{mid}"',
                    'target = "disc_user"',
                    f"offset = {base + s}",
                    f'file = "{name}"',
                    f'sha256 = "{hashlib.sha256(b[s:e]).hexdigest()}"',
                    f'expected_sha256 = "{hashlib.sha256(a[s:e]).hexdigest()}"',
                ] + ([self.when(when)] if when else []) + [""]
                self.count["overlay"] += 1
                continue
            k = s
            while k < e:  # un patch disc_user ne déborde pas d'un secteur
                end = min(e, (base + k) // 2048 * 2048 + 2048 - base)
                self.patch(mid, "disc_user", f"offset = {base + k}", a[k:end], b[k:end], when)
                k = end

    @staticmethod
    def when(w):
        return "when = { " + ", ".join(f"{k} = {toml_str(v)}" for k, v in w.items()) + " }"

    def patch(self, mid, target, loc, old, new, when):
        self.lines += ["[[patch]]", f'feature = "{mid}"', f'target = "{target}"', loc,
                       f'expected = "{hexb(old)}"', f'replace = "{hexb(new)}"'] + \
                      ([self.when(when)] if when else []) + [""]
        self.count[target] += 1

    def write(self, path):
        files = {"manifest.toml": ("\n".join(self.lines)).encode("utf-8"), **self.files}
        path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:  # comme tools/psxmod_pack.py
            for name in sorted(files):
                info = zipfile.ZipInfo(name)
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                z.writestr(info, files[name], compresslevel=9)
        path.write_bytes(buf.getvalue())
        return files["manifest.toml"]


def package(d, bin_path, out):
    sha1 = sha1_file(bin_path)
    if sha1 != REDUMP_SHA1[d]:
        raise SystemExit(f"disque {d} : SHA-1 {sha1}, pas le dump Redump USA (Rev 1) attendu par le recomp")
    sha = sha256_file(bin_path)
    v = next(v for v in mods.versions() if v["id"] == "US")
    disc = psxiso.Disc(bin_path)
    fl = disc.files()
    exe_name = v["exe"][d][0]
    exe0 = bytes(disc.read(*fl[exe_name]))
    lba, size = fl["MGS/STAGE.DIR"]
    st0 = bytes(disc.read(lba, size))
    if int.from_bytes(exe0[0x18:0x1C], "little") != 0x80010000:
        raise SystemExit("EXE : adresse de chargement inattendue")

    p = Package(d, sha)
    p.head()
    seen = {}
    for m in mods.mods():
        if m["type"] not in ("option", "texte") or "US" not in m["versions"]:
            continue
        mid = m["id"]
        if not re.fullmatch(r"[a-z0-9_-]+", mid):
            raise SystemExit(f"id de mod invalide pour psxrecomp : {mid}")
        p.feature(m)
        if m["type"] == "texte":
            p.lines += ["[[option]]", f'feature = "{mid}"', 'id = "life_text"', 'label = "Text / Texte"',
                        'type = "choice"', f'default = "{LIFE_CHOICES[0].lower().replace(" ", "-")}"', ""]
            for c in LIFE_CHOICES:
                p.lines += ["[[option.choice]]", f'value = "{c.lower().replace(" ", "-")}"', f"label = {toml_str(c)}", ""]
            variants = [({"life_text": c.lower().replace(" ", "-")}, {mid: c}) for c in LIFE_CHOICES]
        else:
            variants = [(None, {})]
        for when, texts in variants:
            exe1, st1 = build_variant(exe0, st0, mid, texts)
            # les mods ne se recouvrent pas (vérifié comme dans webpatches.py)
            for kind, a, b in (("exe", exe0, exe1), ("stage", st0, st1)):
                for s, e in runs(a, b, 0):
                    for k in range(s, e):
                        o = seen.setdefault((kind, k), mid)
                        if o != mid:
                            raise SystemExit(f"{mid} et {o} écrivent le même octet ({kind} 0x{k:X})")
            p.exe_patches(mid, exe0, exe1, when)
            p.stage_patches(mid, lba, st0, st1, when)
    path = out / f"MGS1-Mods-USA-Disc{d}.psxmod"
    p.write(path)
    print(f"  {path.name} : {p.count['main_exe']} patches EXE, {p.count['disc_user']} patches STAGE.DIR, "
          f"{p.count['overlay']} overlays, {path.stat().st_size} octets (disc_sha256 {sha[:16]}…)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--us1", metavar="BIN", help="disque 1 USA (Rev 1), BIN Redump (ou CHD)")
    ap.add_argument("--us2", metavar="BIN", help="disque 2 USA (Rev 1), BIN Redump (ou CHD)")
    ap.add_argument("--out", default=str(ROOT / "work" / "psxmod"))
    a = ap.parse_args()
    if not a.us1 and not a.us2:
        ap.error("donner --us1 et/ou --us2")
    import build
    out = Path(a.out)
    for d, src in (("1", a.us1), ("2", a.us2)):
        if src:
            print(f"Disque {d}")
            package(d, build.to_bin(src, f"US{d}"), out)


if __name__ == "__main__":
    main()
