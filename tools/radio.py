#!/usr/bin/env python3
"""
radio.py - Lecture du script Codec RADIO.DAT de MGS1 PS1.

Commandes : FF <op> <taille u16 BE> <arguments>, la taille compte ses 2 octets.
  op 1 TALK  : perso u16, visage u16, anim u16, texte
  op 2 VOICE : code VOX u32 BE (secteur relatif au début de VOX.DAT), puis un bloc imbriqué
  op 3 ANIM, 4 ADD_CONTACT, 5 MEMSAVE, 6 SOUND, 7 PROMPT, 8 VARSAVE, 0x10 IF, 0x20 SWITCH...

Le texte TALK est ce qui s'affiche dans le Codec ; les entrées de sous-titres de la banque
VOX ne donnent que le rythme (chaque entrée fait apparaître le TALK suivant).
"""

import struct


def scan(data):
    """Repère les commandes VOICE et les TALK qu'elles contiennent.

    Renvoie [(offset_voice, code_vox, [offsets_talk])]. On parcourt les commandes à plat :
    les blocs imbriqués suivent directement l'en-tête de la commande.
    """
    voices, i = [], 0
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        op, size = data[i + 1], struct.unpack_from(">H", data, i + 2)[0]
        if op == 2 and size >= 6:
            code = struct.unpack_from(">I", data, i + 4)[0]
            end = i + 2 + size
            talks, j = [], i + 8
            while j < end:
                if data[j] == 0xFF and data[j + 1] == 1:
                    talks.append(j)
                    j += 2 + struct.unpack_from(">H", data, j + 2)[0]
                else:
                    j += 1
            voices.append((i, code, talks))
            i = end
        else:
            i += 1
    return voices


def talk_text(data, off):
    size = struct.unpack_from(">H", data, off + 2)[0]
    return data[off + 10:off + 2 + size].split(b"\0")[0]
