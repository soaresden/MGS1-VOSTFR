"""VOSTFR : voix anglaises, textes français (code : tools/demo_vostfr.py, vox_vostfr.py, voxalign.py).

prepare() apparie les banques VOX des deux versions (les deux disques donnent un appariement
exact : table de test sonore du disque 2, reportée sur le disque 1) ; patch() remplit rep
(nom de fichier -> octets) pour un disque.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import demo_vostfr, vox_vostfr, voxalign


def tables(path, read):
    """Banques de VOX.DAT et table du test sonore d'une image."""
    return (voxalign.bank_table(read(path, "VOX.DAT"), read(path, "RADIO.DAT")),
            voxalign.sound_test_table(read(path, "STAGE.DIR")))


def prepare(imgs, read):
    """imgs : {"1": (fr, uk), "2": (fr, uk)} -> {disque: (ancres, banques FR, banques UK)}."""
    print("Appariement des banques VOX...")
    tab = {(d, k): tables(p, read) for d, pair in imgs.items() for k, p in zip("FU", pair)}
    anchors = {d: {} for d in imgs}
    if "2" in imgs:
        (f2, names_fr), (u2, names_uk) = tab["2", "F"], tab["2", "U"]
        anchors["2"] = voxalign.anchors_disc2(f2, u2, names_fr, names_uk)
        if "1" in imgs:
            anchors["1"] = voxalign.anchors_disc1(tab["1", "F"][0], tab["1", "U"][0], f2, u2, anchors["2"])
    return {d: (anchors[d], tab[d, "F"][0], tab[d, "U"][0]) for d in imgs}


def patch(fr, uk, ctx, rep, disc2, read):
    """Cinématiques, VOX.DAT, RADIO.DAT et STAGE.DIR en VOSTFR (dans rep)."""
    anchors, fr_tab, uk_tab = ctx
    demo, nb, swapped = demo_vostfr.patch(read(fr, "DEMO.DAT"), read(uk, "DEMO.DAT"))
    rep["MGS/DEMO.DAT"] = demo
    del demo
    print(f"  DEMO.DAT : {nb} cinématiques, {swapped} blocs son anglais")

    radio_fr, radio_uk = read(fr, "RADIO.DAT"), read(uk, "RADIO.DAT")
    mapping = voxalign.align(fr_tab, uk_tab, anchors, radio_fr, radio_uk)
    alone = [i for i in range(len(fr_tab)) if i not in mapping]
    print(f"  VOX.DAT : {len(mapping)}/{len(fr_tab)} banques appariées (FR seules : {alone})")
    new_vox, secmap, kept = vox_vostfr.build_vox(read(fr, "VOX.DAT"), read(uk, "VOX.DAT"), mapping)
    rep["MGS/VOX.DAT"] = new_vox
    print(f"  VOX.DAT : {len(new_vox) // 2048} secteurs, {kept} banque(s) gardée(s) en français")

    rep["MGS/RADIO.DAT"], n = vox_vostfr.renumber_radio(radio_fr, secmap)
    print(f"  RADIO.DAT : {n} commandes VOICE renumérotées")
    rep["MGS/STAGE.DIR"], done, _ = vox_vostfr.renumber_stage(read(fr, "STAGE.DIR"), secmap, disc2)
    print(f"  STAGE.DIR : {done} codes VOX renumérotés" + ("" if disc2 else " (test sonore : codes du disque 2, laissés)"))
