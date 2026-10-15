# MGS1 VOSTFR — notes techniques

Voix anglaises (PAL Europe SLES-01370/11370) + textes FR (PAL France SLES-01506/11506).
CHD sources : `D:\batocera\roms\psx\multicd\Metal Gear Solid (France|Europe) (Disc N) [...].chd`.
`work/` (ignoré) : `FR1.bin`… `UK2.bin`, fichiers extraits `work/FR1/MGS/...`, sorties `work/out/`.
Décompilation de référence : FoxdieTeam/mgs_reversing (adresses US, pas PAL).

## Disques

Mêmes fichiers dans les 4 images, dans `MGS/` : BRF.DAT, DEMO.DAT, FACE.DAT, MGS1.EXE (MGS2.EXE sur le disque 2), RADIO.DAT, STAGE.DIR, VOX.DAT, ZMOVIE.STR (+ DUMMY3M.DAT à la racine). Ordre sur le disque : … STAGE.DIR, VOX.DAT, ZMOVIE.STR, DUMMY3M.DAT, postgap Form 2.
- ZMOVIE.STR (FMV, XA Form 2) : taille identique FR/UK. Positions des films relatives au fichier.
- VOX.DAT : FR 182 Mo, UK 196 Mo (disque 1) ; FR 174, UK 189 (disque 2).
- RADIO.DAT et STAGE.DIR : même taille sur les deux disques d'une version, mais contenus différents (codes VOX propres à chaque disque).

## Ce que dit la décompilation

- **Pas de LBA en dur** : au boot, `FS_CdMakePositionTable` (libfs/srchfile.c) lit l'ISO 9660 et trouve les fichiers de `MGS/` par nom (pos = LBA + 150). ZMOVIE.STR est reconnu par son attribut XA (0x2555) : garder l'enregistrement de répertoire intact sauf LBA/taille.
- Numéro de disque = nom de l'exe dans `MGS/`. Changement de disque : `NewAbstractChange` (onoda/abst/ab_ch.c) attend capot ouvert puis fermé (`CdlStatShellOpen`) et relit la table des fichiers.
- **Codes VOX** = secteur relatif au début de VOX.DAT (`vox + FS_StreamGetTop(0)`). Idem DEMO.DAT.
- **Flux** (libfs/stream.c) : blocs lus comme des entiers, `type | taille << 8` (taille 24 bits) → tailles multiples de 4.
- **Codec** : `RADIO.DAT` = fragments de script `FF op taille_u16_BE args` (op 1 TALK, op 2 VOICE code u32 BE + bloc), police du fragment après le script. Le texte affiché vient du TALK ; la boucle Codec (menu/radio.c) passe au TALK suivant quand le pointeur de sous-titre courant (jimctrl) change ou revient à NULL. Donc autant d'entrées de sous-titres que de TALK exécutés.
- **Sous-titres** (game/jimctrl.c) : le bloc 0x03 est copié dans `jimaku_buffer` (4090 octets max). `NewJimakuControl(flags)` : 0 = voix en jeu (texte dessiné), 1 = Codec (pas dessiné), 2 = démo. Police du bloc via `font_set_font_addr(3, …)`. `GM_JimakuCounter` (nb d'entrées passées) sert aussi à des acteurs (demodoll) : garder le nombre d'entrées FR.
- **Voix en jeu** : `GM_VoxStream(code)` ; codes donnés par les scripts GCL de STAGE.DIR (Briefing compris : stage `brf`, 19 codes).

## Formats

### VOX.DAT / DEMO.DAT (tools/vox.py)

Banques alignées sur 2048 octets ; blocs `[code u8][taille 24 bits LE]` : 0x10 init (type du bloc suivant), 0x01 son, 0x02 en-tête audio, 0x04 marqueur, 0x03 sous-titres + lèvres, 0x05 démo, 0xF0 fin.
Bloc 0x03 (après ses 4 octets d'en-tête) : u32 début, u32 fin (0x7FFFFFFF pour le dernier bloc), u16 offset lèvres (0x10), u16 offset sous-titres, u32 offset police (= fin si pas de police). Entrées `{u32 taille_entrée (0 = dernière), u32 début, u32 durée, u32 0, texte\0}` alignées sur 4. Liste vide = une entrée nulle. Une banque peut avoir 2 blocs 0x03 (le 2e au milieu du flux, début = fin du 1er).
Texte : ASCII + `1F xx` pour les accents (é = 1F 0F, è = 1F 10, à = 1F 09, ç = 1F 0E, ê = 1F 11, î = 1F 15), `80 7C` = retour à la ligne.

### STAGE.DIR

En-tête u32 taille de la table puis `{nom[8], u32 secteur}` par stage. Entiers GCL : `0x01` short, `0x09` int, `0x0A` symbole (u32 BE). **Les codes VOX sont des 0x0A (ou 0x09).** Un balayage brut donne ~3 % de faux positifs (textures, texte de debug) : on ne renumérote que si le même stage UK contient le code de la banque UK appariée.
Stage `sound` : table du test sonore `07 09 "vcNNNNNN\0" 09 code`, identique sur les deux disques, codes du **disque 2**. Mêmes noms en FR et UK (732 communs).

## Phase 1 — cinématiques (fait)

DEMO.DAT : mêmes blocs son FR/UK dans les 119 banques. `demo_vostfr.py` recopie l'audio UK dans le DEMO.DAT FR.
Reste : les crédits du doublage FR dans l'intro (« Olivier Deslandes… ») → casting anglais.

## Phase 2 — Codec et voix en jeu (fait)

- `voxalign.py` : ancres du disque 2 par les noms `vc…`, reportées au disque 1 par MD5 de banque (banques communes aux deux disques) ; plus longue sous-suite croissante ; programmation dynamique entre ancres (durée audio, nb de sous-titres, Codec ou non) ; puis votes des VOICE de RADIO.DAT pour les banques FR restées seules. Résultat : disque 1 1101/1101, disque 2 733/735 (banque 159 = réplique allemande oubliée, 178 = sans équivalent UK → gardées en VF). Banque FR 81 du disque 1 : pas de bloc 0x03 côté UK → gardée en VF.
- `vox_vostfr.py` : banque UK + entrées FR (texte, nombre, police FR) ; horaires UK si même nombre d'entrées (~70 %), sinon déformation linéaire par morceaux calée sur les débuts proches (DP). Ordre du VOX.DAT FR conservé. Plus gros bloc produit : 3232 octets.
- `isorebuild.py` : décalage des fichiers suivants (MSF réécrite ; l'EDC/ECC Mode 2 ne couvre pas l'en-tête), répertoires ISO et taille du volume.
- Doublons FR (ex. banques 932 et 940 du disque 1 = même réplique) : deux banques FR peuvent pointer vers la même UK.

Tests faits (PCSX-Redux) : premier Codec du quai (dump RAM : le flux contient la banque UK, pas la FR), appel Campbell/Naomi au Snowfield (5 répliques, durées = horaires UK), Briefing (sous-titre FR dessiné sur voix UK), Game Over, démo d'attraction avec Codec, écran « Insérez le disque 2 », disque 2 lancé seul (Briefing : flux = banque UK, sous-titre FR accentué).
Changement de disque : PCSX-Redux refuse le disque 2 après le capot (« mauvais disque »), y compris le disque 2 FR d'origine, avec ou sans changement d'ISO à chaud → limite de l'émulateur, à vérifier sur Batocera (DuckStation/SwanStation, .m3u). La vérification du jeu appelle la même fonction que le démarrage (`FS_ResetCdFilePosition`), qui marche sur le disque 2 VOSTFR.
Pas testé : une voix en jeu de Meryl (trop loin sans sauvegarde adaptée).

## Patch « Carré » (option --carre, tools/carre.py)

EXE PAL France (MGS1.EXE = MGS2.EXE, mêmes octets sur les deux disques ; chargé à 0x80010000, en-tête 0x800). Boucle Codec (menu/radio.c) : fonction à 0x80042614, s0 = manette (`status` +0, `press` +2, `release` +4), s3 = MenuWork (+0x210 état, +0x212 anti-rebond, +0x218 appel en cours), appel : +0x14 bInExecBlock, +0x18 drapeaux u16 (1 = non coupable, 0x100 = voix coupée).
- État 5 (0x80042d10) : coupure de voix si X relâché (0x40) **ou Carré enfoncé (0x80)**.
- État 4 (0x80042bc0, 28 instructions réécrites en place) : Carré enfoncé → drapeaux |= 0x8100 ; 0x8000 posé → réplique suivante aussitôt. s1/s2 servent de temporaires (réécrits après le switch avant toute lecture). Le drapeau vit avec l'appel (`field_18` rechargé à chaque appel).
- Boutons GV : 0x20 Rond, 0x40 X, 0x10 Triangle, 0x80 Carré. Le patch vérifie les octets d'origine avant d'écrire (idempotent).
Testé : Snowfield, appel Campbell/Naomi de 6 répliques passé en ~1 s ; appel suivant normal ; X inchangé.

## Tests

`python tools/emu.py launch image.cue [--gui]` (arrière-plan) puis `python tools/emu.py cmd "press START 8\nwait 60\nshot s1" 5`. Pilote `tools/emu_drive.lua` : commandes en file, `wait N` en images. Harnais Lua et PCSX-Redux du projet RE1 Hotkey. Dans MGS PAL : **Rond = valider**, Croix = retour ; Codec : SELECT, Bas = MEMORY, Rond = appeler. Au départ du quai, Snake est dans l'eau : il se noie si on ne le sort pas.
Pas de commande Lua pour le capot dans cette version de Redux et l'exe portable n'est pas pilotable par le contrôle de l'ordinateur : changement de disque à la main (`--gui`, File > Open Lid / Open ISO / Close Lid).
Sauvegarde utile : carte DuckStation `D:\batocera\saves\psx\Metal Gear Solid (France) (Disc 1) [SLES_015.06]_1.mcd` (« Snowfield », fin du disque 1 ; avancer tout droit vers le haut → « Insérez le disque 2 »). La copier en `%APPDATA%\pcsx-redux\memcard1.mcd` (garder l'ancienne : partagée avec RE1). Les `.sav` Batocera sont des états DuckStation, illisibles par Redux.
