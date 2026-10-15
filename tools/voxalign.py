#!/usr/bin/env python3
"""
voxalign.py - Appariement des banques VOX.DAT françaises et anglaises (même disque).

Les deux VOX.DAT rangent les banques dans le même ordre, mais la version anglaise en a
quelques-unes de plus (et la française quelques doublons). On combine trois sources :

1. La table de test sonore de STAGE.DIR (stage « sound ») : `"vcNNNNNN" -> code`, mêmes
   noms en FR et en UK. Elle décrit le VOX.DAT du disque 2 : appariement exact là-bas.
2. Les banques communes aux deux disques (même empreinte MD5) : on reporte les paires du
   disque 2 sur le disque 1. On ne garde que les ancres qui respectent l'ordre.
3. Entre deux ancres, programmation dynamique sur la durée audio, le nombre de sous-titres
   et l'usage (Codec ou non). Puis les appels VOICE de RADIO.DAT (même script en FR et en
   UK) « votent » pour les banques restées sans partenaire.

  python voxalign.py FR1.bin UK1.bin [FR2.bin UK2.bin]   rapport d'appariement
"""

import bisect, collections, hashlib, math, re, struct, sys

import numpy as np

import radio, vox

GAP = 2.5


def bank_table(vox_data, radio_data):
    """Une entrée par banque : secteur, empreinte, taille audio, nb de sous-titres, Codec ?"""
    codec = {c for _, c, _ in radio.scan(radio_data)}
    out = []
    for s, e in vox.banks(vox_data):
        inf = vox.bank_info(vox_data, s)
        out.append(dict(sec=s // 2048, md5=hashlib.md5(vox_data[s:e]).hexdigest(), snd=inf["sound"],
                        ncap=sum(len(c[2]) for c in inf["caps"]), R=(s // 2048) in codec))
    return out


def sound_test_table(stage):
    """Table du test sonore : {"vcNNNNNN": code VOX} (codes du disque 2)."""
    return {m.group(1).decode(): struct.unpack(">I", m.group(2))[0]
            for m in re.finditer(rb"\x07\x09(vc\d{6})\x00\x09(.{4})", stage, re.S)}


def cost(a, b):
    c = 3.0 if a["R"] != b["R"] else 0.0
    if a["snd"] and b["snd"]:
        c += abs(math.log(a["snd"] / b["snd"])) * 4
    elif a["snd"] != b["snd"]:
        c += 3
    return c + abs(a["ncap"] - b["ncap"]) * 0.5 / (1 + min(a["ncap"], b["ncap"]) ** 0.5)


def dp(F, U):
    """Alignement global (Needleman-Wunsch) de deux listes de banques -> {i: j}."""
    n, m = len(F), len(U)
    D = np.zeros((n + 1, m + 1))
    P = np.zeros((n + 1, m + 1), np.int8)
    D[:, 0] = np.arange(n + 1) * GAP
    D[0, :] = np.arange(m + 1) * GAP
    P[1:, 0], P[0, 1:] = 1, 2
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            o = (D[i - 1, j - 1] + cost(F[i - 1], U[j - 1]), D[i - 1, j] + GAP, D[i, j - 1] + GAP)
            k = 0 if o[0] <= o[1] and o[0] <= o[2] else (1 if o[1] <= o[2] else 2)
            D[i, j], P[i, j] = o[k], k
    out, i, j = {}, n, m
    while i > 0 or j > 0:
        k = P[i, j]
        if k == 0:
            out[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    return out


def increasing(pairs):
    """Plus longue sous-suite croissante des paires (i, j) : ancres cohérentes avec l'ordre."""
    items = sorted(pairs.items())
    if not items:
        return {}
    tails, tidx, prev = [], [], [-1] * len(items)
    for k, (_, j) in enumerate(items):
        p = bisect.bisect_left(tails, j)
        if p == len(tails):
            tails.append(j)
            tidx.append(k)
        else:
            tails[p], tidx[p] = j, k
        prev[k] = tidx[p - 1] if p else -1
    out, k = {}, tidx[-1]
    while k >= 0:
        out[items[k][0]] = items[k][1]
        k = prev[k]
    return out


def fill(F, U, anchors):
    """Complète les ancres par programmation dynamique entre deux ancres successives."""
    out = dict(anchors)
    prev = (-1, -1)
    for a, b in sorted(anchors.items()) + [(len(F), len(U))]:
        if a - prev[0] > 1 and b - prev[1] > 1:
            for x, y in dp(F[prev[0] + 1:a], U[prev[1] + 1:b]).items():
                out[prev[0] + 1 + x] = prev[1] + 1 + y
        prev = (a, b)
    return out


def voice_votes(F, U, al, radio_fr, radio_uk):
    """Aligne les suites d'appels VOICE FR/UK ; chaque paire alignée vote (banque FR -> UK)."""
    sf = {b["sec"]: i for i, b in enumerate(F)}
    su = {b["sec"]: i for i, b in enumerate(U)}
    vf = [sf[c] for _, c, _ in radio.scan(radio_fr) if c and c in sf]
    vu = [su[c] for _, c, _ in radio.scan(radio_uk) if c and c in su]
    n, m = len(vf), len(vu)
    D = np.zeros((n + 1, m + 1))
    P = np.zeros((n + 1, m + 1), np.int8)
    D[:, 0] = np.arange(n + 1) * GAP
    D[0, :] = np.arange(m + 1) * GAP
    P[1:, 0], P[0, 1:] = 1, 2
    for i in range(1, n + 1):
        a = vf[i - 1]
        for j in range(1, m + 1):
            b = vu[j - 1]
            c = 0.0 if al.get(a) == b else cost(F[a], U[b]) + 0.5
            o = (D[i - 1, j - 1] + c, D[i - 1, j] + GAP, D[i, j - 1] + GAP)
            k = 0 if o[0] <= o[1] and o[0] <= o[2] else (1 if o[1] <= o[2] else 2)
            D[i, j], P[i, j] = o[k], k
    votes = collections.defaultdict(collections.Counter)
    i, j = n, m
    while i > 0 and j > 0:
        k = P[i, j]
        if k == 0:
            votes[vf[i - 1]][vu[j - 1]] += 1
            i, j = i - 1, j - 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    return votes


def align(F, U, anchors, radio_fr, radio_uk):
    """{indice banque FR: indice banque UK} ; les banques FR absentes restent en français."""
    al = fill(F, U, increasing(anchors))
    for a, cnt in voice_votes(F, U, al, radio_fr, radio_uk).items():
        b, k = cnt.most_common(1)[0]
        # une banque FR sans partenaire, appelée au moins deux fois au même endroit que b
        if a not in al and k >= 2 and k == sum(cnt.values()):
            al[a] = b
    return al


def anchors_disc2(F2, U2, table_fr, table_uk):
    sf = {b["sec"]: i for i, b in enumerate(F2)}
    su = {b["sec"]: i for i, b in enumerate(U2)}
    return {sf[c]: su[table_uk[name]] for name, c in table_fr.items()
            if name in table_uk and c in sf and table_uk[name] in su}


def anchors_disc1(F1, U1, F2, U2, pairs2):
    """Reporte les paires du disque 2 sur les banques identiques du disque 1."""
    count = collections.Counter(b["md5"] for t in (F1, U1, F2, U2) for b in t)
    f2 = {b["md5"]: i for i, b in enumerate(F2)}
    u1 = {b["md5"]: i for i, b in enumerate(U1)}
    out = {}
    for i, b in enumerate(F1):
        if count[b["md5"]] > 4:  # banque répétée (silence...) : ambiguë
            continue
        j2 = f2.get(b["md5"])
        if j2 in pairs2:
            k = u1.get(U2[pairs2[j2]]["md5"])
            if k is not None:
                out[i] = k
    return out


def main():
    import psxiso
    imgs = [psxiso.Disc(p) for p in sys.argv[1:]]
    data = []
    for d in imgs:
        f = d.files()
        data.append({k: d.read(*f[f"MGS/{k}"]) for k in ("VOX.DAT", "RADIO.DAT", "STAGE.DIR")})
    tabs = [bank_table(x["VOX.DAT"], x["RADIO.DAT"]) for x in data]
    names = [sound_test_table(x["STAGE.DIR"]) for x in data[:2]]
    if len(data) == 4:
        p2 = anchors_disc2(tabs[2], tabs[3], names[0], names[1])
        a1 = anchors_disc1(tabs[0], tabs[1], tabs[2], tabs[3], p2)
        discs = [(0, a1), (2, p2)]
    else:
        discs = [(0, {})]
    for k, anc in discs:
        F, U = tabs[k], tabs[k + 1]
        al = align(F, U, anc, data[k]["RADIO.DAT"], data[k + 1]["RADIO.DAT"])
        eq = sum(1 for a, b in al.items() if F[a]["ncap"] == U[b]["ncap"])
        print(f"disque {k // 2 + 1} : {len(F)} banques FR, {len(U)} UK, {len(anc)} ancres, "
              f"{len(al)} appariées ({eq} avec autant de sous-titres), FR seules : "
              f"{[a for a in range(len(F)) if a not in al]}")


if __name__ == "__main__":
    main()
