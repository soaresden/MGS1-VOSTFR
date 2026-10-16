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
- État 7 (fin d'appel, 0x80042e80) : appel décroché par le joueur = type 1 (gp+0x814, gp = 0x800ac8e0) -> retour à l'écran des fréquences (état 1, « PRESS SELECT TO EXIT ») ; appel entrant forcé = type 2 -> fermeture (états 0x12, 0x13, 0x14). En martelant X, le dernier appui ferme l'écran des fréquences ; avec Carré on y restait (signalé par Denis au premier appel du quai). Correctif : code à 0x80045900-0x80045a08 (fin du menu de débogage) ; à la place de menu_radio_end_check (0x80042eb8) on note dans gp+0x828 (octet du menu de débogage, jamais lu) que l'appel avait le drapeau 0x8000 ; au test du type (0x80042ee8) ce drapeau fait prendre le chemin « type 2 » (registre seulement, la variable n'est pas modifiée).
Testé : Snowfield, appel Campbell/Naomi de 6 répliques passé en ~1 s ; appel suivant normal ; X inchangé. Quai (appel « tu devras ramper », sauvegarde d'état ~1900 images après work/emu/codec1.sstate, CALL – PUSH SELECT) : Carré -> retour au jeu ; X -> écran des fréquences comme à l'origine. MenuWork = 0x800be938.

## Patch « M9 » (option --m9, tools/m9.py, assembleur tools/mips.py)

Code ajouté dans le menu de débogage de l'EXE, jamais appelé (écrans mem/pow/ply/obj/tex + menu_viewer_act : 0x800447e4-0x80045c08 ; m9 prend 0x800447e4-0x80045900, SHA-1 vérifié ; 0x80045900 carre.py, 0x80045a08 psg1.py). Mode des armes dans la linkvar 83 (0x800b6426, sauvegardée, jamais lue par le jeu) : bit 0 = M9 (case SOCOM), bit 1 = PSG1-T (case PSG1), bit 2 = claymore zzz (case CLAYMORE, id 5).
Adresses PAL FR : linkvarbuf 0x800b6380 (GM_Weapon 0x800b639c, GM_Weapons 0x800b63a2, GM_WeaponsMax 0x800b63b6, GM_SilencerFlag 0x800b63f8), GM_AlertMode 0x800acfe8 (2 = évasion, 3 = alerte), GM_WeaponChanged 0x800acfc0, GM_DisableWeapon 0x800acfcc, GM_TargetDatas 0x800b7ab8 (pas 0x48), overlay de stage chargé à 0x800c47d8 (1er fichier « s/b » du stage dans STAGE.DIR, au secteur suivant l'en-tête).
Retouches de l'EXE :
- menu : get_weapon_rpk_info 0x8003ef30 (M9 = icône du SOCOM silencieux), dessin d'une case 0x8003f0a8 (nom via s7, couleur du sprite = teinte), navigation 0x8003fb04 (Triangle bascule le mode). Les 4 directions naviguent dans ce menu.
- SOCOM GetResources 0x80066a28 : M9 = modèle « socom2 » sans toucher au silencieux. Teinte du modèle abandonnée (Denis : pas utile).
- NewBullet 0x800779ec : balle du joueur au SOCOM/PSG1 en mode tranquillisant -> TARGET.a_mode = 0x19 (balle +0x44).
- GM_PowerTarget 0x8002e264 : cible saisissable (TARGET_CAPTURE, les soldats) -> sommeil ; autre cible -> a_mode 1, dégâts normaux.
- chargeur du M9 = 1 : NewSOCOM 0x80066da0 (max 12/13 et chargeur) et SOCOM Act 0x8006697c (max remis à 12 après un tir) ; le rechargement (0x80058b90…) prend min(max, munitions).
- objet ramassé 0x80034a7c (acteur item.c : type +0x113, id +0x114, nom +0x118) : « SOCOM + M9 », « PSG1 + PSG1-T ».
Sommeil : TARGET.damaged |= 4, a_mode 9 (le soldat s'effondre comme sous grenade incapacitante), faint = -32000, field_18 = 0x4D395A5A. Alerte (mode >= 2) : 1er tir = a_mode 3 (secoué), field_18 = 0x4D39AAAA + acteur minuteur (200 images de jeu = 8 s, PAL 25 images/s ; 1 image de jeu = 2 VSync) ; 2e tir ou fin du minuteur = sommeil. field_18 (pointeur de saisie) n'est remis à NULL qu'à l'init du soldat (GM_SetCaptureTarget).
Overlays (36 avec soldats, 33 retouchés) : mode « au sol » repéré par `lh v0,DELAI(s0); nop; slt v0,v0,s1; beqz; nop; lw v1,CIBLE(s0)` (DELAI 0xb5a/0xaf6/0xaea, CIBLE 0x900/0x8fc/0x8f0) : test de réveil -> relais wake_CIBLE (jamais de réveil, zzz toutes les 64 images, copie d'AN_Sleep dans l'EXE, script recopié de STAGE.DIR) ; appel d'AN_Piyopiyo (texture 0xcafe) -> relais piyo_ADR_CIBLE (pas d'étoiles). Les textures zzz/étoiles sont résidentes (stage init). Ancienne variante (s07c, s09a, coups 1-4 seulement) : coup 9 redirigé vers le coup 3. Pas de soldat reconnu : s03c, s12b, s12c.
Testé (PCSX-Redux, quai, sauvegarde d'état + écriture de l'EXE patché en RAM) : bascule Triangle SOCOM/M9 et PSG1/PSG1-T, R1, garde en ronde endormi en 1 tir et toujours au sol 20 s après avec zzz, alerte : secoué puis endormi ~8 s après, 2e tir = endormi tout de suite, PSG1-T, message « SOCOM + M9 ». Pas testé : boss (code simple : a_mode 1).
Claymores zzz (décomp : weapon/mine.c, bullet/jirai.c, okajima/claymore.c) : mine.c Act appelle NewJirai 0x8006c4f8 (hook 0x80068578 : si bit 2, marque 0x4D39CCCC dans JiraiWork +0x110, champ inutilisé, mis à zéro par GV_NewActor ; JiraiWork 0x154 octets, Act 0x8006bb98). Explosion dans jirai Act (s0 = mine) : souffle = TARGET local GM_SetPowerTarget(POWER_DECREASE, a_mode 2, 128) puis GM_PowerTarget (hook 0x8006bfc0 : a_mode 0x1A si marquée) ; éclats = NewClaymore 0x80074eb0 (8 appels de 2 éclats, hook 0x8006c010 : drapeau global clay_flag pendant l'appel), cible de l'éclat posée dans claymore_loader 0x80074c4c (TARGET en +0x3c, POWER_ONCE a_mode 2, 256 ; hook 0x80074cec sur `weapon = 5` : a_mode 0x1A si clay_flag). cave_power : a_mode 0x19 (fléchette) ou 0x1A (claymore) ; soldat = TARGET_CAPTURE **et** side 2 (Snake est aussi saisissable, side 1) ; claymore = knock tout de suite, même en alerte ; autre cible -> a_mode 1 (balle) ou 2 (claymore). Soldat déjà endormi (field_18 = SLEEP et faint < 0) : ignoré (éclats suivants, fléchette de trop). Raven : classe 0x15, pas saisissable -> dégâts normaux.
Testé (quai) : menu (« CLAY.ZZZ », icône bleutée, Triangle bascule le bit 2), claymore zzz posée (marque en +0x110, munitions -1), garde 2 placé sur la mine (mov 0x80169fe8 et copie +0x24) : explosion, garde endormi (vie 192 intacte, faint -32000, a_mode 9) et toujours au sol avec zzz 25 s après ; claymore normale : garde tué (vie -448). M9 refait après la retouche de cave_power : garde endormi en 1 tir. Pas testé : Raven, message « CLAYMORE + ZZZ » (pas de claymore à ramasser au quai), Snake pris dans une claymore zzz.
Pièges de test : **un état d'émulateur contient l'EXE de l'image qui l'a créé** (dockup.sstate = vieille version du M9, sans claymores) : après une nouvelle image, repartir d'une sauvegarde de carte mémoire, ou écrire le nouvel EXE en RAM ; **le recompilateur de PCSX-Redux garde l'ancien code compilé** : après un `poke` de code, faire `save` puis `load` de cet état (sinon le jeu exécute en partie l'ancien code, voire plante) ; le pilote Lua plante (« stack overflow ») vers 32 000 images après le lancement -> relancer l'émulateur ; tourner Snake en écrivant turn.vy pendant la visée le pousse (il peut tomber à l'eau) : l'orienter (rot.vy + turn.vy) avant d'équiper ; `load` d'un état s'applique à l'image suivante (attendre avant d'écrire en RAM) ; l'émulateur tourne entre deux commandes (une alerte peut tuer Snake) ; la commande `near` du pilote place Snake (mov 0x8016cac8 sur la sauvegarde du quai) près d'une cible.

## Patch « PSG1 debout » (option --psg1, tools/psg1.py)

Travail de Snake (sna_init, s0 ; décalages PAL = Integral − 4) : +0x9b0 actpack, +0xa22 posture (0 debout, 1 accroupi, 2 couché), +0xa36 état de la visée (field_A3A), +0xaa action en cours, +0x9cc tableau de visée (field_9D0). Sur la sauvegarde du quai : travail à 0x8016caa8 (mov 0x8016cac8, rot.vy 0x8016cad2, turn.vy 0x8016cb16, action 0x8016cb52, posture 0x8016d4ca, état 0x8016d4de, actpack 0x8016d458, caméra field_A60 0x8016d504). GM_Magazine 0x800acfd4.
Tables : gSnakeWeapons 0x800a0560 (PSG1 : NewRifle 0x80069158, sna_anim_psg1 0x80057fc0 ; Stinger 0x80058290), weapon_actions 0x800a03b8 (pas 28 ; PSG1 0x800a04b4, move = NULL, attack 0x800a0368 = {44, 136...}), FamasMove 0x800a02a8, GM_WeaponTypes 0x8009eb98 (PSG1 0x9220 : 0x20 = l'état d'attaque démarre dès qu'on équipe). Fonction de visée PSG1 (field_9C8) 0x800590dc.
Pourquoi Snake se couche : sna_anim_psg1, image 0, posture debout -> accroupi (état 0-1) -> couché (état 2) -> visée (état 3, action attack->aim = 44, couchée). Sauter seulement les états 0-2 ne suffit pas : l'animation 44 garde la caméra au ras du sol (mesuré : 189 contre 1371 en vue Triangle debout).
Patch (grotte 0x80045a08-0x80045bb8, fin du menu de débogage ; m9.py vérifie tout le menu -> appliquer m9 avant psg1) :
- 0x80058014 : état 3 tout de suite quelle que soit la posture ; actpack = copie du PSG1 avec attack->aim 5 (set_up_famas) debout, 15 (squat_socom) accroupi, move = FamasMove ; couché : actpack d'origine.
- 0x800581a8 : état 3, accroupi -> ne pas effacer PLAYER_SQUAT (0x20).
- 0x800581e4 : état 4 et suivants (visée en cours), caméra field_A60 = main (os 4) + (5,500,80) seulement couché ; sinon la tête (os 6), comme la vue Triangle.
- 0x800592a4 : limite de visée verticale 0x78 couché, 0x200 sinon (bornée ensuite par le jeu : −188..+222 mesuré debout).
- 0x80059418 : animation de tremblement 122 (couchée) seulement couché.
- 0x80059108 (fonction de visée, chaque image) : X (press 0x40) -> posture 0 <-> 1, actpack, PLAYER_SQUAT (GM_PlayerStatus 0x800ad038), SetAction(aim), son 8 (SE_CHANGE_STANCE). Couché : rien.
- 0x80055f50, 0x800562b0, 0x80056b8c : « arme = PSG1 -> posture = couché » après une scène (sna_init.c, réglage d'arme/objet par message, cf. Integral l. 4565/4708/5067) -> nop. Pas testé en jeu (pas de scène sous la main) ; c'est sans doute ce que Denis a vu avec le PSG1-T (le menu, lui, marche : testé sur out_complet).
Grotte du PSG1 : 0x80045a08-0x80045bb8 (428 octets utilisés), puis l2r2.
Testé (PCSX-Redux, quai, poke en RAM) : debout (caméra 1362), accroupi (816), tir sur un garde (vie 192 -> −64), touché en visant (reste debout), couché identique à l'original (44 puis 122), R1 range / ressort, marche après rangement.

## Patch « L2/R2 » (option --l2r2, tools/l2r2.py)

Jeu d'origine : Triangle maintenu, **L1/R1** penchent Snake à gauche/droite (sna_80051BA4, PAL 0x8005726c, aussi dos au mur) ; L2/R2 ne font rien dans cette vue (pas de menu non plus) ; X s'accroupit / se relève (déjà dans le jeu PAL : vue subjective sna_fn_80052120 = 0x800577ec). Penché, la vue subjective sort avant la rotation (0x800578b0 : bnez -> retour).
Patch (Denis, comme MGS2) : 5 andi élargis (status 0xc -> 0xf, R1 8 -> 0xa, L1 4 -> 5, en press et release) ; 0x800578b0 : penché -> sna_80051DA0 (0x8005746c) + sna_80051FD0 (0x800576a0) puis retour ; 0x800573ac (choix du côté) : un bouton gauche (0x5) et un droit (0xa) tenus -> field_A60.vy (+0xa5e, caméra, y vers le haut) += 200 au lieu du décalage latéral (pointe des pieds). Grotte 0x80045bb8-0x80045c08 (80 octets, tout pris).
Testé (quai) : L2 / R2 / L1 = caméra ±830 en x ; penché + Droite : rot.vy 0 -> −1239, la vue tourne ; L2+R2 : caméra centrée, y 1371 -> 1571, retour à 1371 au relâchement. Arme toujours en main, pas de menu.

## Tests

`python tools/emu.py launch image.cue [--gui]` (arrière-plan) puis `python tools/emu.py cmd "press START 8\nwait 60\nshot s1" 5`. Pilote `tools/emu_drive.lua` : commandes en file, `wait N` en images (VSync), aussi r16/r32, w16/w32, `poke fichier`, `near cible position dz`. Harnais Lua et PCSX-Redux du projet RE1 Hotkey. Dans MGS PAL : **Rond = valider**, Croix = retour ; Codec : SELECT, Bas = MEMORY, Rond = appeler. Au départ du quai, Snake est dans l'eau : il se noie si on ne le sort pas.
Pas de commande Lua pour le capot dans cette version de Redux et l'exe portable n'est pas pilotable par le contrôle de l'ordinateur : changement de disque à la main (`--gui`, File > Open Lid / Open ISO / Close Lid).
Sauvegarde utile : carte DuckStation `D:\batocera\saves\psx\Metal Gear Solid (France) (Disc 1) [SLES_015.06]_1.mcd` (« Snowfield », fin du disque 1 ; avancer tout droit vers le haut → « Insérez le disque 2 »). La copier en `%APPDATA%\pcsx-redux\memcard1.mcd` (garder l'ancienne : partagée avec RE1). Les `.sav` Batocera sont des états DuckStation, illisibles par Redux.
