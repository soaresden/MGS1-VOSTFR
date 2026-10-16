#!/usr/bin/env python3
"""
psg1loup.py - Patch optionnel : le PSG1 dans la grotte, là où Meryl attendait, avant Sniper Wolf.

Jeu d'origine (scripts de s10a, s09a, s07b, s04a ; P = progression, var GCL 0x0a) : Sniper Wolf
blesse Meryl dans le passage souterrain (s10a, cinématique, P = 0x91) et repousse Snake ; Snake
ressort puis revient (P = 0x92, cinématique, P = 0x94) ; Campbell appelle (« va chercher le PSG1
à l'armurerie », P = 0x95) ; en traversant la salle du commandant (s07b), P = 0x96 ; à
l'armurerie (s04a), ramasser le PSG1 déclenche un autre appel de Campbell ; au retour dans le
passage avec P = 0x96, Meryl n'est plus là (il reste le sang) et le combat commence.

Avec ce patch, après l'appel de Campbell, il suffit de ressortir dans la grotte (s09a, celle des
chiens-loups) : le PSG1 est là où Meryl attendait. Le ramassage lance l'appel de Campbell de
l'armurerie, et au retour dans le passage Meryl n'est plus là, comme dans le jeu d'origine.

Retouches (scripts GCL de STAGE.DIR, aucun changement de taille) :
- s10a (2 scripts) et s10ar : après la cinématique du retour, `P = 0x95` -> `P = 0x96`
  (`11 00 00 0A 02 95 31 14` -> `... 02 96 ...`) : Meryl partie dès cet appel, comme après s07b ;
- s09a, boîte de munitions PSG1 « seebe » (en 1000, 0, -11500, qui n'apparaît d'origine que si
  l'on a déjà le PSG1), réécrite à taille égale (132 octets) :
  `if (P == 0x96 && PSG1 <= 0) { PSG1 = 0 ; chara seebe -p 8500 0 -6500 -b b2 -i b9 -n 5
  -m 'PSG1' -x { appel de Campbell } }` (-i en short au lieu d'un octet : un octet de plus, pour
  tomber juste).
  Une vraie arme au sol (`-b b0`) est impossible ici : son modèle (cache 0x4D5F = 0x4D5F + type)
  n'est pas dans les fichiers de s09a, l'objet serait invisible et ne se ramasserait pas. On
  garde donc la boîte de munitions (modèle 0x4D61, présent) et l'on donne le PSG1 vide en
  entrant dans la grotte (sans quoi le jeu refuse les munitions : « GET WEAPON FIRST ») ; la
  boîte apporte les 5 balles. Position : là où attend Meryl (acteur s95f2, points 8500 0 -6500
  et 11000 0 -8500). Bloc de ramassage `-x` = l'appel de Campbell de l'armurerie, recopié de
  s04a (proc 0x7E9C : `0x24e1 -c 14085 t<appel> b0`). Place prise sur le message (« PSG1 » au lieu
  de « PSG1/BULLET * 5 ») et sur l'enveloppe de réapparition des objets
  (`0xd86 (expr 14 04 00 01)`, délai selon la difficulté, aucun objet en Extreme) : la boîte
  apparaît donc aussi en Extreme. Après le combat (P >= 0x97), ou une fois le PSG1 chargé, elle
  n'apparaît plus. L'armurerie marche toujours (PSG1 déjà là : munitions).

  python psg1loup.py image.bin [image2.bin ...]     patch en place (STAGE.DIR)
"""

import struct
import sys

import gcx, psxiso
from cdsector import write_file_inplace

P95 = bytes.fromhex("1100000a029531143100")    # P = 0x95 (après la cinématique du retour, s10a)
# s09a, tels quels dans les versions FR et UK : appel p3353 (réapparition), enveloppe
# `0xd86 (expr 14 04 00 01) {`, puis `0xd86 (PSG1 >= 0) {` ...
PRE = bytes.fromhex("70083353120001610060" "00830d867f" "300714040001" "3100" "400074"
                    "6000700d866c")
# ... condition PSG1 >= 0 et objet « seebe » ...
BOX = bytes.fromhex("300b118000340200310e3100" "4000" "5d600059" "9906" "07" "068767" "06eebe"
                    "50700a" "0103e8" "010000" "01d314" "5062030202" "5069030209" "506e04010005"
                    "506d130710") + b"PSG1/BULLET * 5" + bytes(1)
# ... option -x (bloc : $var161 = $var000, drapeau de réapparition), puis les fins de blocs
END_X = bytes.fromhex("50781a" "400018" "60001464c00f300d" "12000161" "12000000" "3114" "3100" "00" "00")
TAIL = bytes(5)    # fin des options de chara, des deux blocs et des deux commandes 0xd86

NEW_POS = bytes.fromhex("012134" "010000" "01e69c")                # 8500, 0, -6500
COND = bytes.fromhex("3015" "1100000a02963109" "118000340200310c" "3113" "3100")  # P == 0x96 && PSG1 <= 0
SETTER = bytes.fromhex("60001264c00d" "300b" "118000340200" "3114" "3100" "00")   # PSG1 = 0


def campbell_call(st):
    """Commande d'appel de Campbell au ramassage du PSG1 de l'armurerie (s04a, proc 0x7E9C) :
    `60 00 13 24 E1 01 50 63 0B 01 37 05 0A <appel u32> 02 00 00` (0x24e1 -c 14085 t<appel> b0)."""
    a, e = next((a, e) for n, a, e in gcx.stage_table(st) if n == "s04a")
    for g in gcx.scripts(st, a):
        procs, pt = [], g + 4
        while gcx._be32(st, pt):
            procs.append((gcx._be16(st, pt), gcx._be16(st, pt + 2)))
            pt += 4
        for pid, off in procs:
            if pid == 0x7E9C:
                cmd = st[pt + 4 + off + 3:pt + 4 + off + 3 + 20]   # 1re instruction de la procédure
                if cmd[:13] == bytes.fromhex("60001324e10150630b0137050a") and cmd[17:] == bytes.fromhex("020000"):
                    return cmd
    raise SystemExit("s04a : appel de Campbell du PSG1 introuvable")


def new_box(call):
    """Les 132 octets qui remplacent les deux 0xd86 imbriqués (voir l'en-tête)."""
    chara = (bytes.fromhex("60004f990607" "068767" "06eebe" "50700a") + NEW_POS
             + bytes.fromhex("5062030202" "506904010009" "506e04010005" "506d080705") + b"PSG1\0"
             + bytes.fromhex("50781a400018") + call + bytes(2)      # -x { appel }, fin de bloc
             + bytes(1))                                            # fin des options
    assert chara[1:3] == struct.pack(">H", len(chara) - 1)
    body = SETTER + chara + bytes(1)
    block = b"\x40" + struct.pack(">H", len(body) + 2) + body
    size = 5 + len(COND) + len(block) + 1
    return b"\x60" + struct.pack(">H", size) + bytes.fromhex("0d86") + bytes([size - 4]) + COND + block + bytes(1)


def patch_stage(st):
    """STAGE.DIR -> (STAGE.DIR patché, nombre de retouches)."""
    out = bytearray(st)
    call = campbell_call(st)
    n = 0
    for name, a, e in gcx.stage_table(st):
        if name in ("s10a", "s10ar"):
            i = st.find(P95, a, e)
            if i == -1:
                raise SystemExit(f"{name} : P = 0x95 introuvable (déjà patché ?)")
            while i != -1:
                out[i + 5] = 0x96
                n += 1
                i = st.find(P95, i + 1, e)
        elif name == "s09a":
            i = st.find(BOX, a, e)
            if i == -1:
                raise SystemExit("s09a : boîte de munitions PSG1 introuvable (déjà patchée ?)")
            assert st.find(BOX, i + 1, e) == -1
            s, x = i - len(PRE) + 9, i + len(BOX)           # s : début de l'enveloppe 0xd86
            assert st[i - len(PRE):i] == PRE, "s09a : enveloppe inattendue"
            assert st[x:x + len(END_X) + len(TAIL)] == END_X + TAIL, "s09a : bloc de ramassage inattendu"
            new = new_box(call)
            assert len(new) == x + len(END_X) + len(TAIL) - s == 132
            out[s:s + len(new)] = new
            n += 1
    return bytes(out), n


def patch_image(path):
    d = psxiso.Disc(path)
    lba, size = d.files()["MGS/STAGE.DIR"]
    new, n = patch_stage(d.read(lba, size))
    d.f.close()
    write_file_inplace(path, lba, new)
    return n


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for p in sys.argv[1:]:
        print(p, ":", patch_image(p), "retouches (PSG1 dans la grotte, là où Meryl attendait)")


if __name__ == "__main__":
    main()
