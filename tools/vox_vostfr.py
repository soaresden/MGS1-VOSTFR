#!/usr/bin/env python3
"""
vox_vostfr.py - Codec et voix en jeu en VOSTFR : nouveau VOX.DAT + renumérotation des codes.

Chaque banque du nouveau VOX.DAT est la banque anglaise appariée (audio et mouvements de
lèvres anglais) dont le bloc de sous-titres (0x03) est réécrit avec les sous-titres FR :
même nombre d'entrées et même texte que la banque française, police FR, horaires recalés
sur la voix anglaise.

- Codec : le texte affiché vient des TALK de RADIO.DAT, chaque entrée de sous-titre fait
  passer au TALK suivant. Garder le nombre d'entrées FR garde la synchro avec le script FR.
- Voix en jeu (GM_VoxStream) : c'est le texte des entrées qui est dessiné (police du bloc).

Horaires : si FR et UK ont autant d'entrées, on prend celles de l'anglais. Sinon les débuts
FR proches (en proportion) d'un début UK s'y calent et le reste est interpolé.

Les banques FR sans équivalent anglais sont recopiées telles quelles (voix française).
Les banques sont rangées dans l'ordre du VOX.DAT français ; les codes VOX (secteur relatif
au début du fichier) changent donc : RADIO.DAT (commandes VOICE) et STAGE.DIR (entiers GCL
0x09 / 0x0A) sont renumérotés sans changer de taille.
"""

import collections, re, struct

import gcx, radio, vox

JIMAKU_MAX = 4088  # tampon jimaku_buffer du jeu : 4090 octets


def caption_block(data, off):
    """Décode un bloc 0x03 : en-tête, lèvres, entrées [(t, durée, texte)], police."""
    size = int.from_bytes(data[off + 1:off + 4], "little")
    b = data[off + 4:off + size]
    start, end, lip_off, sub_off, font_off = struct.unpack_from("<IIHHI", b, 0)
    caps = []
    j = sub_off
    while True:
        nxt, t, dur, _ = struct.unpack_from("<IIII", b, j)
        txt = b[j + 16:b.index(b"\0", j + 16)]
        if not (nxt == 0 and t == 0 and dur == 0 and not txt and not caps):
            caps.append((t, dur, txt))
        if nxt == 0:
            break
        j += nxt
    return dict(start=start, end=end, lips=b[lip_off:sub_off], caps=caps, font=b[font_off:])


def encode_block(start, end, lips, caps, font):
    """Bloc 0x03 complet (avec son en-tête [code][taille 24 bits])."""
    lips = lips + b"\0" * (-len(lips) % 4)
    ents = []
    for k, (t, dur, txt) in enumerate(caps):
        body = txt + b"\0"
        body += b"\0" * (-len(body) % 4)
        nxt = 16 + len(body) if k + 1 < len(caps) else 0
        ents.append(struct.pack("<IIII", nxt, t, dur, 0) + body)
    if not ents:  # liste vide : une entrée nulle
        ents = [bytes(20)]
    sub = b"".join(ents)
    font = font + b"\0" * (-len(font) % 4)
    sub_off = 16 + len(lips)
    body = struct.pack("<IIHHI", start, end, 16, sub_off, sub_off + len(sub)) + lips + sub + font
    return bytes([vox.CAPS1]) + (len(body) + 4).to_bytes(3, "little") + body


def warp(fr, uk):
    """Horaires des entrées FR recalés sur l'audio anglais : [(t, durée)]."""
    if len(fr) == len(uk):
        return [(t, d) for t, d, _ in uk]
    if not fr or not uk:
        return [(t, d) for t, d, _ in fr]
    f0, f1 = fr[0][0], max(t + d for t, d, _ in fr)
    u0, u1 = uk[0][0], max(t + d for t, d, _ in uk)
    pf = [(t - f0) / max(f1 - f0, 1) for t, _, _ in fr]
    pu = [(t - u0) / max(u1 - u0, 1) for t, _, _ in uk]
    # appariement monotone des débuts proches (programmation dynamique)
    tol = 0.06
    n, m = len(fr), len(uk)
    D = [[0.0] * (m + 1) for _ in range(n + 1)]
    P = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            best = (1e9, 0)
            if i and j and abs(pf[i - 1] - pu[j - 1]) < tol:
                best = min(best, (D[i - 1][j - 1] + abs(pf[i - 1] - pu[j - 1]), 0))
            if i:
                best = min(best, (D[i - 1][j] + tol, 1))
            if j:
                best = min(best, (D[i][j - 1] + tol, 2))
            D[i][j], P[i][j] = best
    pts, i, j = [], n, m
    while i or j:
        k = P[i][j]
        if k == 0:
            pts.append((fr[i - 1][0], uk[j - 1][0]))
            i, j = i - 1, j - 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    pts = sorted(set(pts + [(f0, u0), (f1, u1)]))

    def w(x):
        for (a, b), (c, d) in zip(pts, pts[1:]):
            if x <= c:
                return b + (x - a) * (d - b) / max(c - a, 1)
        return pts[-1][1] + x - pts[-1][0]

    out = []
    for k, (t, d, _) in enumerate(fr):
        s, e = round(w(t)), round(w(t + d))
        if k + 1 < len(fr):
            e = min(e, round(w(fr[k + 1][0])) - 1)
        out.append((s, max(e - s, 1)))
    return out


def build_bank(fr, fs, uk, us):
    """Banque UK de [us...] avec les sous-titres FR de la banque [fs...]."""
    fr_blocks = [caption_block(fr, o) for c, o, _ in vox.blocks(fr, fs) if c == vox.CAPS1]
    fr_caps = [c for b in fr_blocks for c in b["caps"]]
    font = next((b["font"] for b in fr_blocks if b["font"]), b"")
    uk_list = list(vox.blocks(uk, us))
    uk_blocks = [(o, caption_block(uk, o)) for c, o, _ in uk_list if c == vox.CAPS1]
    if not uk_blocks:
        if fr_caps:
            return None  # pas de bloc de sous-titres côté anglais : on garde la banque FR
        e = uk_list[-1][1] + uk_list[-1][2]
        return uk[us:e]
    uk_caps = [(c, n) for n, (_, b) in enumerate(uk_blocks) for c in b["caps"]]
    times = warp(fr_caps, [c for c, _ in uk_caps])
    # répartition des entrées dans les blocs anglais
    per = [[] for _ in uk_blocks]
    for k, ((_, _, txt), (t, d)) in enumerate(zip(fr_caps, times)):
        if len(fr_caps) == len(uk_caps):
            n = uk_caps[k][1]
        else:
            n = next((n for n, (_, b) in enumerate(uk_blocks) if t < b["end"]), len(uk_blocks) - 1)
        b = uk_blocks[n][1]
        t = max(t, b["start"])
        d = max(1, min(d, b["end"] - t))
        per[n].append((t, d, txt))
    new = {}
    for n, (o, b) in enumerate(uk_blocks):
        blk = encode_block(b["start"], b["end"], b["lips"], per[n], font)
        if len(blk) - 4 > JIMAKU_MAX:
            raise ValueError(f"bloc de sous-titres trop gros ({len(blk)} octets)")
        new[o] = blk
    out = bytearray()
    for c, o, size in uk_list:
        out += new.get(o, uk[o:o + size])
    return bytes(out)


def build_vox(fr, uk, mapping):
    """Nouveau VOX.DAT. mapping : {indice banque FR: indice banque UK}.

    Renvoie (données, {secteur FR: nouveau secteur}, nb de banques gardées en français)."""
    bf, bu = vox.banks(fr), vox.banks(uk)
    out, secmap, kept = bytearray(), {}, 0
    for i, (fs, fe) in enumerate(bf):
        bank = None
        if i in mapping:
            bank = build_bank(fr, fs, uk, bu[mapping[i]][0])
        if bank is None:
            bank, kept = fr[fs:fe], kept + 1
        secmap[fs // 2048] = len(out) // 2048
        out += bank
        out += b"\0" * (-len(out) % 2048)
    return bytes(out), secmap, kept


def renumber_radio(data, secmap):
    """Codes des commandes VOICE de RADIO.DAT (u32 BE, taille inchangée)."""
    out = bytearray(data)
    n = 0
    for off, code, _ in radio.scan(data):
        if code in secmap:
            struct.pack_into(">I", out, off + 4, secmap[code])
            n += code != secmap[code]
    return bytes(out), n


def stage_table(st):
    """Répertoire de STAGE.DIR : {nom: (début, fin)} en octets."""
    size = struct.unpack_from("<I", st, 0)[0]
    ent = [(st[4 + 12 * k:12 + 12 * k].rstrip(b"\0").decode(), struct.unpack_from("<I", st, 12 + 12 * k)[0] * 2048)
           for k in range(size // 12)]
    return {n: (o, ent[k + 1][1] if k + 1 < len(ent) else len(st)) for k, (n, o) in enumerate(ent)}


def gcl_ints(st, a, b, wanted):
    """Entiers GCL (0x09 int / 0x0A symbole, u32 BE) de [a, b) dont la valeur est dans wanted."""
    out = []
    for m in re.finditer(rb"[\x09\x0a]", st[a:b - 4]):
        i = a + m.start()
        v = struct.unpack_from(">I", st, i + 1)[0]
        if v and v in wanted:
            out.append((i, v))
    return out


def renumber_stage(st_fr, st_uk, secmap, fr_to_uk):
    """Codes VOX des scripts GCL de STAGE.DIR FR.

    Les codes sont les jetons entiers (0x09 / 0x0A) des scripts GCX (gcx.codes), et non tous les
    octets 0x09 / 0x0A du fichier : un balayage brut modifiait aussi des données d'overlays (s03b,
    s19b). Par prudence, un code n'est renuméroté que si le même stage anglais contient le code de
    la banque anglaise appariée. fr_to_uk : {secteur FR: secteur UK}.
    """
    out = bytearray(st_fr)
    tu = stage_table(st_uk)
    uk_secs = set(fr_to_uk.values())
    uk_vals = {}
    done = skipped = 0
    for p, kind, name in gcx.codes(st_fr, set(secmap), set()):
        if kind != "vox" or name not in tu:
            continue
        if name not in uk_vals:
            uk_vals[name] = {v for _, v in gcl_ints(st_uk, *tu[name], uk_secs)}
        v = struct.unpack_from(">I", st_fr, p + 1)[0]
        if fr_to_uk.get(v) in uk_vals[name]:
            struct.pack_into(">I", out, p + 1, secmap[v])
            done += 1
        else:
            skipped += 1
    return bytes(out), done, skipped
