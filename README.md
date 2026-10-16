# Metal Gear Solid (PS1) — VOSTFR

🇬🇧 [English version](README.en.md) · 🇫🇷 Français

**▶ [La page du projet, avec les captures](https://soaresden.github.io/MGS1-VOSTFR/)**

<p align="center"><img src="docs/shots/codec-kurdes.png" width="400" alt="Codec : voix anglaise de Campbell, texte français"> <img src="docs/shots/demo-foxhound.png" width="400" alt="Cinématique d'intro sous-titrée en français"></p>

Patch « VOSTFR » pour **Metal Gear Solid** sur PlayStation : les **voix anglaises** d'origine avec les **textes et sous-titres français**.

Le dépôt ne contient **aucune donnée du jeu** : seulement les scripts qui fabriquent les images à partir de **tes propres** disques PAL France et PAL Europe (anglais).

## État

| Partie | État |
|---|---|
| Cinématiques (`DEMO.DAT`) : voix anglaises, sous-titres FR | ✅ fait, testé dans PCSX-Redux |
| Appels Codec (`VOX.DAT` + `RADIO.DAT`) : voix anglaises, texte FR calé sur la voix | ✅ fait, testé (premier Codec du quai, Campbell/Naomi au Snowfield) |
| Voix en jeu (dialogues pendant l'action, Briefing) | ✅ fait, testé sur le Briefing des deux disques (même mécanisme) |
| Disque 2 | ✅ démarre, voix anglaises et sous-titres FR (Briefing) |
| Changement de disque en cours de partie | ⚠️ à vérifier sur console ou DuckStation : PCSX-Redux le refuse, même avec les disques d'origine |
| Option `--carre` : Carré fait défiler les dialogues du Codec (comme dans MGS2) | ✅ fait, testé |
| Option `--m9` : M9 et PSG1-T tranquillisants (les gardes s'endorment, zzz) | ✅ fait, testé (quai, garde en ronde, en alerte, 2e tir, PSG1-T) |
| Option `--m9` : claymores zzz (« CLAY.ZZZ ») | ✅ fait, testé (quai : claymore zzz = garde endormi, claymore normale = garde tué) |
| Option `--psg1` : PSG1 (et PSG1-T) utilisable debout ou accroupi | ✅ fait, testé (quai : debout, accroupi, couché, tir sur un garde) |
| Crédits du doublage FR dans l'intro → casting anglais | 🔧 à faire |
| Version « 2 disques en 1 » | 💡 phase 3 |

## Disques nécessaires

| Version | Disque 1 | Disque 2 |
|---|---|---|
| France | SLES-01506 | SLES-11506 |
| Europe (anglais) | SLES-01370 | SLES-11370 |

En CHD (comme dans Batocera) ou en BIN/CUE. Pas besoin de chdman : le CHD est lu directement en Python, et le SHA-1 brut est vérifié.

## Utilisation

Python 3.10+ avec `numpy`.

```bash
cd tools
python build.py --fr1 "MGS (France) (Disc 1).chd" --uk1 "MGS (Europe) (Disc 1).chd" --fr2 "MGS (France) (Disc 2).chd" --uk2 "MGS (Europe) (Disc 2).chd" --out ../work/out
```

Résultat : `Metal Gear Solid (VOSTFR) (Disc 1).bin/.cue`, `(Disc 2)` et un `.m3u` pour l'échange de disque dans l'émulateur. Compter environ une minute et demie, et 2 Go de mémoire libre.

Option `--carre` : pendant un appel Codec, **Carré** coupe la voix et fait défiler toutes les répliques restantes d'un coup, comme si on martelait le bouton (X garde son rôle d'origine : il coupe la voix, puis une réplique par appui). Les choix (sauvegarde, oui/non) ne sont pas sautés. Le patch existe aussi seul, pour une image déjà construite :

```bash
python carre.py "Metal Gear Solid (VOSTFR) (Disc 1).bin" "Metal Gear Solid (VOSTFR) (Disc 2).bin"
```

Option `--m9` : un **M9 tranquillisant** (et un **PSG1-T**) pour finir le jeu sans tuer.
- On l'a en ramassant le SOCOM (message « SOCOM + M9 ») ; le PSG1-T vient avec le PSG1.
- Dans le menu des armes (R2), sur le SOCOM, **Triangle** passe au M9 (nom « M9 », icône bleutée) et inversement. Même chose sur le PSG1. Les quatre directions servent déjà à naviguer dans ce menu. R1 (équiper / ranger) garde le choix, qui est aussi enregistré dans la sauvegarde.
- Munitions communes avec l'arme d'origine : les munitions de SOCOM remplissent aussi le M9. Toujours silencieux, coup par coup, **une fléchette à la fois** (chargeur de 1). À l'écran, l'arme en main est celle du SOCOM avec silencieux.
- Garde en ronde : endormi en **1 tir**, pour de bon (il ne se réveille pas), avec des **zzz** au-dessus de lui. Pas de sang, pas de perte de vie, pas compté comme tué.
- Pendant une alerte ou une recherche : le 1er tir le **secoue** ; il s'endort **8 s** plus tard, ou tout de suite au 2e tir.
- Boss, caméras, etc. : mêmes dégâts que l'arme d'origine (Sniper Wolf au PSG1-T, par exemple).
- **Claymores zzz** : sur la case CLAYMORE, Triangle passe aux claymores zzz (nom « CLAY.ZZZ », icône bleutée) et inversement. Munitions communes (message « CLAYMORE + ZZZ » au ramassage). Le choix compte au moment où on **pose** la mine : une claymore zzz posée reste zzz. Un soldat qui la déclenche (ou qui prend l'explosion) s'endort tout de suite, même en alerte, pour de bon et sans perdre de vie. Les autres cibles (Raven, Snake...) prennent les dégâts normaux d'une claymore.
- Le code des soldats est retouché dans 33 des 36 stages qui en ont (3 stages sans soldat « au sol » reconnu : s03c, s12b, s12c).

```bash
python m9.py "Metal Gear Solid (VOSTFR) (Disc 1).bin" "Metal Gear Solid (VOSTFR) (Disc 2).bin"
```

Option `--psg1` : le **PSG1** (et le PSG1-T de `--m9`) s'utilise **debout ou accroupi**, sans que Snake se couche.
- Debout, Snake épaule le fusil et la lunette est à hauteur des yeux (comme la vue subjective Triangle). Accroupi, la lunette est plus basse. Couché, rien ne change par rapport au jeu d'origine.
- Snake garde la posture qu'il avait en sortant le PSG1. Pour viser couché : se coucher d'abord, puis sortir le PSG1. Pour changer de posture : ranger le PSG1 (R1), changer de posture, le ressortir (R1).
- Debout ou accroupi, on vise un peu plus haut et plus bas que couché, et la lunette **ne tremble pas** (dans le jeu, le tremblement est une animation couchée). Le cœur bat toujours dans la manette.
- Avec `--m9`, appliquer `m9.py` **avant** `psg1.py` (build.py le fait dans le bon ordre).

```bash
python psg1.py "Metal Gear Solid (VOSTFR) (Disc 1).bin" "Metal Gear Solid (VOSTFR) (Disc 2).bin"
```

Bon à savoir : en vue subjective (Triangle maintenu), **L1 et R1** font déjà pencher Snake à gauche et à droite pour regarder derrière un coin. L2 et R2 ne font rien dans cette vue.

Donne les **deux disques** : la table du test sonore du disque 2 sert aussi à apparier exactement les voix du disque 1.

## Comment ça marche

### Cinématiques

Dans les deux versions PAL, chaque cinématique de `DEMO.DAT` a **exactement la même suite de blocs audio** (même nombre, même taille) : le doublage FR a été calé sur la durée des scènes. On garde le `DEMO.DAT` français (sous-titres, animations) et on y recopie l'audio anglais bloc par bloc. Les sous-titres FR tombent pile sur les répliques anglaises.

### Codec et voix en jeu

Là, les doublages n'ont pas la même durée : `VOX.DAT` anglais fait 196 Mo contre 182 Mo en français (disque 1).

1. **Appariement des voix** : les deux `VOX.DAT` rangent leurs ~1100 banques dans le même ordre, avec quelques banques en plus côté anglais. Le jeu contient une table de test sonore (`vc000101` → banque) aux mêmes noms en FR et en UK : appariement exact sur le disque 2, reporté sur le disque 1 par les banques communes aux deux disques. Le reste est aligné par programmation dynamique (durée audio, nombre de sous-titres), puis vérifié par les appels Codec du script.
2. **Nouveau `VOX.DAT`** : chaque banque anglaise (voix et mouvements de lèvres) reçoit les sous-titres français (même nombre de répliques que la banque FR, police FR), avec les horaires de la version anglaise. Dans le Codec, chaque sous-titre fait passer à la réplique suivante du script `RADIO.DAT` français : le texte suit donc la voix anglaise.
3. **Renumérotation** : les codes VOX (position dans le fichier) des commandes VOICE de `RADIO.DAT` et des scripts de `STAGE.DIR` sont réécrits. Dans `STAGE.DIR`, un code n'est changé que si le même stage anglais contient le code correspondant (pas de faux positifs dans les textures).
4. **Image disque** : `VOX.DAT` grossit, donc `ZMOVIE.STR` et `DUMMY3M.DAT` sont décalés (secteurs bruts recopiés), les enregistrements de répertoire ISO 9660 et la taille du volume réécrits, EDC/ECC recalculés. Le jeu retrouve ses fichiers par leur nom au démarrage : aucune autre adresse à corriger.

Deux répliques du disque 2 n'existent qu'en français (dont une oubliée en allemand dans le disque FR) : elles restent en VF.

## Outils

| Script | Rôle |
|---|---|
| `tools/build.py` | Construit les images VOSTFR |
| `tools/chd2bin.py` | CHD v5 → BIN/CUE (cdlz, cdzl), vérification SHA-1 |
| `tools/psxiso.py` | Liste, extraction, vérification EDC d'une image PS1 |
| `tools/cdsector.py` | EDC/ECC Mode 2 Form 1 (numpy), réécriture d'un fichier en place |
| `tools/isorebuild.py` | Reconstruction d'une image avec des fichiers de taille différente |
| `tools/vox.py` | Banques de `VOX.DAT` / `DEMO.DAT` : blocs, sous-titres |
| `tools/voxalign.py` | Appariement des banques VOX françaises et anglaises |
| `tools/vox_vostfr.py` | Nouveau `VOX.DAT`, renumérotation de `RADIO.DAT` et `STAGE.DIR` |
| `tools/radio.py` | Script Codec `RADIO.DAT` (commandes TALK / VOICE) |
| `tools/demo_vostfr.py` | Remplacement de l'audio des cinématiques |
| `tools/carre.py` | Patch optionnel : Carré fait défiler le Codec |
| `tools/m9.py` | Patch optionnel : M9 et PSG1-T tranquillisants |
| `tools/psg1.py` | Patch optionnel : PSG1 debout ou accroupi |
| `tools/mips.py` | Petit assembleur MIPS (R3000) pour les patchs |
| `tools/emu.py`, `tools/emu_drive.lua` | Test automatique dans PCSX-Redux (captures d'écran) |
