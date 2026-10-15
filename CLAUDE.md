# MGS1 VOSTFR — notes techniques

Voix anglaises (PAL Europe SLES-01370/11370) + textes FR (PAL France SLES-01506/11506).
CHD sources : `D:\batocera\roms\psx\multicd\Metal Gear Solid (France|Europe) (Disc N) [...].chd`.
`work/` (ignoré) : `FR1.bin`… `UK2.bin`, fichiers extraits `work/FR1/MGS/...`, sorties `work/out/`.

## Disques

Mêmes fichiers dans les 4 images, dans `MGS/` : BRF.DAT, DEMO.DAT, FACE.DAT, MGS1.EXE (MGS2.EXE sur le disque 2), RADIO.DAT, STAGE.DIR, VOX.DAT, ZMOVIE.STR (+ DUMMY3M.DAT à la racine).
- ZMOVIE.STR (FMV, XA Form 2) : taille identique FR/UK.
- DEMO.DAT : quasi identique en taille ; VOX.DAT : FR 182 Mo, UK 196 Mo (disque 1).
- RADIO.DAT est identique entre les disques 1 et 2 d'une même version.

## Ce que dit la décompilation (FoxdieTeam/mgs_reversing)

- **Pas de LBA en dur** : au boot, `FS_CdMakePositionTable` (libfs/srchfile.c) lit l'ISO 9660 et trouve STAGE.DIR, RADIO.DAT, FACE.DAT, ZMOVIE.STR, VOX.DAT, DEMO.DAT, BRF.DAT par nom dans `MGS/`. On peut donc reconstruire l'ISO avec des tailles différentes.
- Le numéro de disque vient du nom de l'exe trouvé dans `MGS/` (MGS1.EXE / MGS2.EXE) → `FS_DiskNum`. Le changement de disque est l'acteur `NewAbstractChange` (onoda/abst/ab_ch.c) : il attend l'ouverture du capot puis relit la table des fichiers. Utile pour la phase « 1 disque ».
- **Codes VOX** = secteur relatif au début de VOX.DAT (`vox + FS_StreamGetTop(0)`). Idem DEMO.DAT pour les cinématiques.
- **Codec** : `RADIO.DAT` est un script GCL : `FF op taille_u16_BE args`. op 1 TALK (perso, visage, anim, texte), op 2 VOICE (code VOX u32 BE + bloc imbriqué de TALK).
  **Le texte affiché vient du TALK de RADIO.DAT** ; les entrées de sous-titres de la banque VOX ne servent que d'horloge (chaque entrée affiche le TALK suivant, sa fin l'efface). Donc il faut autant d'entrées de sous-titres dans la banque VOX que de TALK dans le bloc VOICE.
- **Voix en jeu** (`GM_VoxStream`, flags 0/2) : là, c'est le texte des sous-titres de la banque VOX qui est dessiné. Codes VOX dans les scripts de STAGE.DIR.
- Les chunks de RADIO.DAT sont référencés depuis STAGE.DIR (code radio = secteur/taille) → ne pas changer la taille de RADIO.DAT si possible.
- Horloge des sous-titres = compteur de lecture audio (`str_counter`), pas les VSync.

## Format VOX.DAT / DEMO.DAT (tools/vox.py)

Banques alignées sur 2048 octets ; blocs `[code u8][taille u16 LE]` : 0x10 init, 0x01 son (VAG), 0x02 en-tête audio, 0x03 sous-titres+lèvres (PAL), 0x06 (langue 2), 0x05 données de démo, 0xF0 fin.
Bloc sous-titres : u16 à +12 = offset des données lèvres, u16 à +14 = offset des sous-titres (relatifs à +4) ; liste chaînée `{u32 taille_suivant, u32 début, u32 durée, u32 ?, texte\0}`. Police propre au bloc (font_offset).
Texte : ASCII + `1F xx` pour les accents (é = 1F 0F, è = 1F 10, à = 1F 09, ç = 1F 0E, ê = 1F 11, î = 1F 15), `80 7C` = retour à la ligne.

## Phase 1 — cinématiques (fait)

DEMO.DAT : mêmes blocs son FR/UK (nombre et tailles) dans les 119 banques ; seuls des blocs 0x05 (démo) diffèrent parfois. `demo_vostfr.py` recopie l'audio UK dans le DEMO.DAT FR, réécrit en place (`cdsector.write_file_inplace`). Testé dans PCSX-Redux : boot, intro, premier Codec OK.
Reste : les crédits du doublage FR s'affichent dans l'intro (« Olivier Deslandes, Philippe Monnet, Pierre Maubouché ») → à remplacer par le casting anglais (chercher où : STAGE.DIR ou blocs 0x05).

## Phase 2 — Codec et voix en jeu (à faire)

1. Disque 1 : 1101 banques VOX FR, 1107 UK ; disque 2 : 735 / 754. Aligner les banques FR ↔ UK (par position dans RADIO.DAT : VOICE FR 4738 vs UK 4918 → aligner par contenu, pas par ordre).
2. Nouveau VOX.DAT = banques UK (audio + lèvres anglais). Pour chaque banque appelée par le Codec : réécrire sa liste de sous-titres pour qu'elle ait autant d'entrées que de TALK FR (timings recalés sur l'audio anglais). Pour les voix en jeu : remplacer le texte par le texte FR + police FR.
3. Renuméroter les codes VOICE de RADIO.DAT FR (u32, taille inchangée) et les codes VOX de STAGE.DIR FR vers les nouvelles positions.
4. Reconstruire l'ISO (VOX.DAT plus gros → décaler ZMOVIE.STR et DUMMY3M.DAT, réécrire les enregistrements de répertoire).

## Tests

`python tools/emu.py launch image.cue` (arrière-plan) puis `python tools/emu.py cmd "press START 8\nshot s1" 5`. PCSX-Redux + harnais Lua empruntés au projet RE1 Hotkey. Dans MGS PAL : **Rond = valider**, Croix = retour.
