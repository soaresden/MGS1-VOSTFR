// Généré par tools/mods.py à partir de mods/*/mod.json et versions/*.json - ne pas modifier à la main.
globalThis.MGS_MODS = {
 "versions": [
  {
   "id": "vostfr",
   "type": "base",
   "besoin": [
    "FR",
    "UK"
   ],
   "versions": [
    "FR"
   ],
   "fr": "VOSTFR : voix anglaises, textes français",
   "en": "VOSTFR: English voices, French text",
   "frS": "Il faut les disques français et anglais.",
   "enS": "Needs the French and English discs.",
   "shots": [
    [
     "docs/shots/demo-foxhound.png",
     "Intro · voix anglaise, sous-titre français",
     "Intro · English voice, French subtitle"
    ],
    [
     "docs/shots/codec-kurdes.png",
     "Codec · Campbell",
     "Codec · Campbell"
    ],
    [
     "docs/shots/codec-naomi.png",
     "Codec · Naomi",
     "Codec · Naomi"
    ],
    [
     "docs/shots/jeu-neige.png",
     "Snowfield",
     "Snowfield"
    ]
   ],
   "fl": [
    "Les voix de David Hayter, Jennifer Hale et de toute la distribution d'origine.",
    "Cinématiques, appels Codec et voix en jeu, sur les deux disques.",
    "Le texte du Codec suit la voix anglaise, réplique par réplique.",
    "Menus, objets et textes : ceux de la version française."
   ],
   "el": [
    "The voices of David Hayter, Jennifer Hale and the whole original cast.",
    "Cutscenes, Codec calls and in-game voices, on both discs.",
    "The Codec text follows the English voice, line by line.",
    "Menus, items and text: those of the French version."
   ],
   "version": true
  },
  {
   "id": "FR",
   "disques": {
    "1": "SLES_015.06",
    "2": "SLES_115.06"
   },
   "nomCourt": "VF",
   "langue": "fr",
   "disqueFr": "France",
   "disqueEn": "France",
   "fr": "Version française d'origine",
   "en": "Original French version",
   "frS": "Voix et textes français, avec tes mods. Disques français seulement.",
   "enS": "French voices and text, with your mods. French discs only.",
   "shots": [
    [
     "docs/shots/menu.png",
     "Menus en français",
     "French menus"
    ]
   ],
   "fl": [
    "Le jeu français tel quel (doublage français), avec les mods cochés."
   ],
   "el": [
    "The French game as it is (French dub), with the ticked mods."
   ],
   "version": true
  },
  {
   "id": "UK",
   "disques": {
    "1": "SLES_013.70",
    "2": "SLES_113.70"
   },
   "nomCourt": "EN",
   "langue": "en",
   "disqueFr": "Europe (anglais)",
   "disqueEn": "Europe (English)",
   "fr": "Version anglaise d'origine",
   "en": "Original English version",
   "frS": "Voix et textes anglais, avec tes mods. Disques européens seulement.",
   "enS": "English voices and text, with your mods. European discs only.",
   "shots": [
    [
     "docs/previews/m9_texte_en.png",
     "Menu R2 en anglais · M9",
     "R2 menu in English · M9"
    ],
    [
     "docs/previews/carre_on_en.png",
     "Codec en anglais",
     "Codec in English"
    ]
   ],
   "fl": [
    "Le jeu européen (anglais) tel quel, avec les mods cochés.",
    "Les textes ajoutés par les mods (menu des armes…) sont en anglais."
   ],
   "el": [
    "The European (English) game as it is, with the ticked mods.",
    "The text added by the mods (weapon menu…) is in English."
   ],
   "version": true
  }
 ],
 "mods": [
  {
   "id": "combine",
   "rang": 10,
   "type": "final",
   "need2": true,
   "fr": "CD Combiner",
   "en": "CD Combiner",
   "frS": "Les deux disques en un seul : plus de changement de disque. Son un peu allégé.",
   "enS": "Both discs in one: no more disc swap. Slightly lighter sound.",
   "shots": [
    [
     "docs/previews/combine_change.png",
     "Fin du disque 1 : on enchaîne sur le disque 2, sans rien faire",
     "End of disc 1: straight on to disc 2, nothing to do"
    ],
    [
     "docs/previews/combine_snowfield_d2.png",
     "Disque 2, sur la même image",
     "Disc 2, on the same image"
    ],
    [
     "docs/previews/combine_codec_d2.png",
     "Codec du disque 2",
     "Disc 2 Codec"
    ],
    [
     "docs/previews/combine_on.png",
     "Un seul disque",
     "A single disc"
    ]
   ],
   "audio": [
    [
     "docs/previews/combine_codec_original.wav",
     "Codec · d'origine (22 kHz)",
     "Codec · original (22 kHz)"
    ],
    [
     "docs/previews/combine_codec_allege.wav",
     "Codec · allégé (11 kHz)",
     "Codec · lighter (11 kHz)"
    ],
    [
     "docs/previews/combine_cinematique_original.wav",
     "Cinématique · d'origine (33 kHz)",
     "Cutscene · original (33 kHz)"
    ],
    [
     "docs/previews/combine_cinematique_allege.wav",
     "Cinématique · allégée (22 kHz)",
     "Cutscene · lighter (22 kHz)"
    ]
   ],
   "fl": [
    "En plus des deux disques, une seule image « (1 CD) » pour tout le jeu (environ 990 Mo), pour les émulateurs.",
    "Plus d'écran « insérez le disque 2 » : le jeu enchaîne tout seul.",
    "Pour que tout tienne sur un CD, les voix passent à 11 kHz et les cinématiques à 22 kHz : écoute la différence ci-dessous.",
    "Il faut les deux disques de la version choisie."
   ],
   "el": [
    "On top of the two discs, a single \"(1 CD)\" image for the whole game (about 990 MB), for emulators.",
    "No more \"insert disc 2\" screen: the game carries on by itself.",
    "To fit on one CD, voices go down to 11 kHz and cutscenes to 22 kHz: hear the difference below.",
    "Needs both discs of the chosen version."
   ]
  },
  {
   "id": "carre",
   "rang": 20,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "fr": "Carré fait défiler le Codec",
   "en": "Square skips through the Codec",
   "frS": "Pratique quand on refait le jeu ou qu'on appelle Mei Ling pour sauvegarder.",
   "enS": "Handy when replaying the game or calling Mei Ling to save.",
   "shots": [
    [
     "docs/previews/carre_on.png",
     "Codec en cours",
     "Codec call"
    ]
   ],
   "fl": [
    "Pendant un appel, <b>Carré</b> coupe la voix et fait défiler toutes les répliques d'un coup, comme dans MGS2.",
    "X garde son rôle d'origine : une réplique par appui.",
    "Les choix (sauvegarde, oui/non) ne sont jamais sautés."
   ],
   "el": [
    "During a call, <b>Square</b> cuts the voice and runs through all the lines at once, like in MGS2.",
    "X keeps its original role: one line per press.",
    "Choices (save, yes/no) are never skipped."
   ]
  },
  {
   "id": "m9",
   "rang": 30,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "fr": "Armes tranquillisantes",
   "en": "Tranquilizer weapons",
   "frS": "M9, PSG1-T et claymores zzz silencieuses : pour finir le jeu sans tuer.",
   "enS": "M9, PSG1-T and silent zzz claymores: to finish the game without killing.",
   "shots": [
    [
     "docs/previews/m9_texte.png",
     "Menu R2 · Triangle passe au M9",
     "R2 menu · Triangle switches to the M9"
    ],
    [
     "docs/previews/m9_zzz.png",
     "Garde endormi · zzz",
     "Guard asleep · zzz"
    ],
    [
     "docs/previews/clay_texte.png",
     "Menu R2 · CLAY.ZZZ",
     "R2 menu · CLAY.ZZZ"
    ],
    [
     "docs/previews/clay_pfft.png",
     "Claymore zzz : un « pfft », pas d'explosion",
     "zzz claymore: a \"pfft\", no blast"
    ],
    [
     "docs/previews/psg1t_texte.png",
     "Menu R2 · PSG1-T",
     "R2 menu · PSG1-T"
    ]
   ],
   "fl": [
    "Dans le menu des armes (R2), <b>Triangle</b> change le SOCOM en <b>M9</b>, le PSG1 en <b>PSG1-T</b> et les claymores en <b>CLAY.ZZZ</b>.",
    "Un tir endort un garde pour de bon, avec des zzz. En alerte, il s'endort 8 s plus tard.",
    "Les claymores zzz ne font aucun bruit : les autres gardes n'entendent rien.",
    "Boss : dégâts normaux."
   ],
   "el": [
    "In the weapon menu (R2), <b>Triangle</b> turns the SOCOM into the <b>M9</b>, the PSG1 into the <b>PSG1-T</b> and the claymores into <b>CLAY.ZZZ</b>.",
    "One shot puts a guard to sleep for good, with zzz. During an alert, he falls asleep 8 s later.",
    "zzz claymores make no noise: the other guards hear nothing.",
    "Bosses: normal damage."
   ]
  },
  {
   "id": "fps",
   "rang": 40,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "fr": "Viser en vue subjective",
   "en": "Aim in first-person view",
   "frS": "Tirer au SOCOM ou au M9 depuis la vue subjective, comme dans MGS2.",
   "enS": "Shoot the SOCOM or the M9 from the first-person view, like in MGS2.",
   "shots": [
    [
     "docs/previews/fps_on.png",
     "Carré maintenu : l'arme et son laser",
     "Square held: the weapon and its laser"
    ],
    [
     "docs/previews/fps_off.png",
     "Triangle seul : la vue subjective",
     "Triangle alone: the first-person view"
    ]
   ],
   "fl": [
    "<b>Triangle</b> maintenu : vue subjective.",
    "<b>Carré</b> maintenu : l'arme apparaît avec son laser rouge ; Carré relâché : le coup part là où tu regardes.",
    "Avec les armes tranquillisantes, le M9 endort aussi en vue subjective."
   ],
   "el": [
    "Hold <b>Triangle</b>: first-person view.",
    "Hold <b>Square</b>: the weapon shows with its red laser; release Square: the shot goes where you look.",
    "With the tranquilizer weapons, the M9 also puts guards to sleep in first-person view."
   ]
  },
  {
   "id": "l2r2",
   "rang": 50,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "fr": "Se pencher avec L2 / R2",
   "en": "Lean with L2 / R2",
   "frS": "En vue subjective, regarder derrière un coin ou par-dessus un obstacle.",
   "enS": "In first-person view, look around a corner or over an obstacle.",
   "shots": [
    [
     "docs/previews/l2r2_on.png",
     "Penché à gauche · L2",
     "Leaning left · L2"
    ]
   ],
   "fl": [
    "En vue subjective, <b>L2</b> penche Snake à gauche et <b>R2</b> à droite, comme dans MGS2.",
    "Penché, les flèches tournent toujours la vue.",
    "<b>L2 + R2</b> ensemble : Snake se met sur la pointe des pieds."
   ],
   "el": [
    "In first-person view, <b>L2</b> makes Snake lean left and <b>R2</b> right, like in MGS2.",
    "While leaning, the arrows still turn the view.",
    "<b>L2 + R2</b> together: Snake stands on tiptoe."
   ]
  },
  {
   "id": "psg1",
   "rang": 60,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "fr": "PSG1 debout ou accroupi",
   "en": "PSG1 standing or crouching",
   "frS": "Le fusil de précision sans avoir à se coucher.",
   "enS": "The sniper rifle without having to lie down.",
   "shots": [
    [
     "docs/previews/psg1_on.png",
     "Avec l'option : Snake reste debout avec le PSG1",
     "With the option: Snake stays standing with the PSG1"
    ],
    [
     "docs/previews/psg1_off.png",
     "Jeu d'origine : Snake doit se coucher",
     "Original game: Snake has to lie down"
    ]
   ],
   "fl": [
    "Snake garde sa posture en sortant le PSG1 ; couché, rien ne change.",
    "Dans la lunette, <b>X</b> passe de debout à accroupi.",
    "Debout ou accroupi, la lunette ne tremble pas."
   ],
   "el": [
    "Snake keeps his stance when drawing the PSG1; prone, nothing changes.",
    "In the scope, <b>X</b> switches between standing and crouching.",
    "Standing or crouching, the scope does not sway."
   ]
  },
  {
   "id": "bandana",
   "rang": 70,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "off": true,
   "fr": "Bandana visible, façon MGS2",
   "en": "Visible bandana, MGS2-style",
   "frS": "Un très long pan de bandana (1,30 m) flotte derrière Snake. Prototype.",
   "enS": "A very long (1.30 m) bandana tail flows behind Snake. Prototype.",
   "shots": [
    [
     "docs/previews/bandana_on.png",
     "Le pan du bandana derrière Snake",
     "The bandana tail behind Snake"
    ],
    [
     "docs/previews/bandana_dos.png",
     "Vu de dos (image éclaircie)",
     "Seen from behind (brightened)"
    ]
   ],
   "fl": [
    "Le bandana se voit, avec un pan de 1,30 m qui pend dans le dos, se soulève quand Snake court et ondule.",
    "C'est un modèle de pan prévu par Konami mais inutilisé, rallongé et animé.",
    "Prototype, décoché par défaut."
   ],
   "el": [
    "The bandana shows, with a 1.30 m tail hanging down the back, lifting when Snake runs and waving.",
    "It is a tail model planned by Konami but unused, lengthened and animated.",
    "Prototype, unticked by default."
   ]
  },
  {
   "id": "cartes",
   "rang": 80,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "fr": "Portes à carte sans équiper la carte",
   "en": "Card doors without equipping the card",
   "frS": "La carte dans l'inventaire suffit ; elle s'équipe toute seule quand la porte s'ouvre (son icône s'affiche).",
   "enS": "Having the card in your inventory is enough; it equips itself when the door opens (its icon shows).",
   "shots": [
    [
     "docs/previews/cartes_icone.png",
     "La porte s'ouvre et la carte s'équipe : son icône s'affiche",
     "The door opens and the card equips itself: its icon shows"
    ],
    [
     "docs/previews/cartes_on.png",
     "Avec l'option : la porte s'ouvre",
     "With the option: the door opens"
    ],
    [
     "docs/previews/cartes_off.png",
     "Jeu d'origine : il faut équiper la carte",
     "Original game: you have to equip the card"
    ]
   ],
   "fl": [
    "Une porte à carte s'ouvre dès que tu as la bonne carte (ou une meilleure) dans ton inventaire.",
    "À l'ouverture, la carte s'équipe toute seule : son icône, avec le niveau, s'affiche dans la case des objets (elle remplace l'objet que tu avais en main).",
    "Une carte trop faible donne tout de suite le voyant rouge, même sans l'équiper. 3 portes (s07b, s08a) s'ouvrent sans équiper la carte."
   ],
   "el": [
    "A card door opens as soon as you have the right card (or a better one) in your inventory.",
    "When it opens, the card equips itself: its icon, with the level, shows in the item box (it replaces the item you had in hand).",
    "A card that is too weak gets the red light at once, even unequipped. 3 doors (s07b, s08a) open without equipping the card."
   ]
  },
  {
   "id": "psg1loup",
   "rang": 90,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "off": true,
   "fr": "PSG1 dans la grotte",
   "en": "PSG1 in the cave",
   "frS": "Le PSG1 t'attend dans la grotte des chiens-loups, là où Meryl attendait : plus de détour par l'armurerie.",
   "enS": "The PSG1 waits for you in the wolf-dog cave, where Meryl was waiting: no more trip back to the armory.",
   "shots": [
    [
     "docs/previews/psg1loup_on.png",
     "Après le ramassage : appel de Campbell, puis le combat contre Sniper Wolf",
     "After the pickup: Campbell's call, then the fight against Sniper Wolf"
    ]
   ],
   "fl": [
    "Le PSG1 est dans la grotte des chiens-loups, à l'endroit où Meryl attendait avec le chien.",
    "En le ramassant, tu as 5 balles et l'appel de Campbell de l'armurerie ; de retour dans le passage, le combat contre Sniper Wolf commence.",
    "Marche aussi en Extreme. Décochée par défaut : coche-la si tu veux t'épargner le détour."
   ],
   "el": [
    "The PSG1 is in the wolf-dog cave, where Meryl was waiting with the dog.",
    "Picking it up gives 5 rounds and Campbell's armory call; back in the passage, the fight against Sniper Wolf starts.",
    "Also works on Extreme. Unticked by default: tick it if you want to skip the trip."
   ]
  },
  {
   "id": "titre",
   "rang": 100,
   "type": "option",
   "versions": [
    "FR",
    "UK"
   ],
   "fr": "Écran titre « Shadow Fixes »",
   "en": "\"Shadow Fixes\" title screen",
   "frS": "Le titre devient « METAL GEAR SOLID - SHADOW FIXES », by Soaresden, v1.0 : tu sais tout de suite que c'est la version moddée.",
   "enS": "The title becomes \"METAL GEAR SOLID - SHADOW FIXES\", by Soaresden, v1.0: you can tell right away it is the modded version.",
   "shots": [
    [
     "docs/previews/titre_on.png",
     "Écran « PRESS START BUTTON »",
     "\"PRESS START BUTTON\" screen"
    ]
   ],
   "fl": [
    "Sous « METAL GEAR », la bande « S O L I D » devient « SOLID - SHADOW FIXES », dans les couleurs du logo.",
    "« by Soaresden  v1.0 » s'affiche au-dessus du menu, sur le visage de Snake.",
    "Seul l'écran titre change : le reste du jeu n'est pas touché."
   ],
   "el": [
    "Under \"METAL GEAR\", the \"S O L I D\" band becomes \"SOLID - SHADOW FIXES\", in the logo colours.",
    "\"by Soaresden  v1.0\" shows above the menu, over Snake's face.",
    "Only the title screen changes: the rest of the game is untouched."
   ]
  },
  {
   "id": "life",
   "rang": 110,
   "type": "texte",
   "versions": [
    "FR",
    "UK"
   ],
   "text": true,
   "fr": "Barre de vie : ton texte",
   "en": "Life bar: your own text",
   "frS": "À la place de « LIFE » : SNAKE, ton pseudo… 15 caractères.",
   "enS": "Instead of \"LIFE\": SNAKE, your nickname… 15 characters.",
   "shots": [
    [
     "#live",
     "Aperçu en direct",
     "Live preview"
    ],
    [
     "docs/previews/life_snake.png",
     "En jeu : « SNAKE »",
     "In game: \"SNAKE\""
    ],
    [
     "docs/previews/life_max.png",
     "En jeu : « REVOLVER OCELOT » (15 caractères)",
     "In game: \"REVOLVER OCELOT\" (15 characters)"
    ]
   ],
   "fl": [
    "Lettres, chiffres, espace et . : ! ? + - = % ( ) ; les accents sont enlevés.",
    "Vide ou « LIFE » : la barre ne change pas.",
    "L'aperçu est dessiné comme dans le jeu."
   ],
   "el": [
    "Letters, digits, space and . : ! ? + - = % ( ); accents are removed.",
    "Empty or \"LIFE\": the bar does not change.",
    "The preview is drawn as in the game."
   ]
  }
 ],
 "ids": {
  "SLES_015.06": "FR1",
  "SLES_115.06": "FR2",
  "SLES_013.70": "UK1",
  "SLES_113.70": "UK2"
 }
};
