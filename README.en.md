# Metal Gear Solid (PS1) — VOSTFR

🇬🇧 English · 🇫🇷 [Version française](README.md)

A "VOSTFR" patch for **Metal Gear Solid** on PlayStation: the original **English voices** with **French text and subtitles**.

This repository contains **no game data**: only the scripts that build the images from **your own** PAL France and PAL Europe (English) discs.

## Status

| Part | Status |
|---|---|
| Cutscenes (`DEMO.DAT`): English voices, French subtitles | ✅ done, tested in PCSX-Redux |
| Codec calls (`VOX.DAT` + `RADIO.DAT`): English voices, French text timed to the voice | ✅ done, tested (first Codec call at the dock, Campbell/Naomi at the Snowfield) |
| In-game voices (dialogue during gameplay, Briefing) | ✅ done, tested on both discs' Briefing (same mechanism) |
| Disc 2 | ✅ boots, English voices and French subtitles (Briefing) |
| Disc swap during the game | ⚠️ to be checked on console or DuckStation: PCSX-Redux refuses it, even with the original discs |
| `--carre` option: Square fast-forwards Codec dialogue (like in MGS2) | ✅ done, tested |
| French dub credits in the intro → English cast | 🔧 to do |
| "2 discs in 1" version | 💡 phase 3 |

## Required discs

| Version | Disc 1 | Disc 2 |
|---|---|---|
| France | SLES-01506 | SLES-11506 |
| Europe (English) | SLES-01370 | SLES-11370 |

As CHD (like in Batocera) or BIN/CUE. No chdman needed: the CHD is read directly in Python, and its raw SHA-1 is checked.

## Usage

Python 3.10+ with `numpy`.

```bash
cd tools
python build.py --fr1 "MGS (France) (Disc 1).chd" --uk1 "MGS (Europe) (Disc 1).chd" --fr2 "MGS (France) (Disc 2).chd" --uk2 "MGS (Europe) (Disc 2).chd" --out ../work/out
```

Output: `Metal Gear Solid (VOSTFR) (Disc 1).bin/.cue`, `(Disc 2)` and an `.m3u` for disc swapping in emulators. It takes about a minute and a half and needs 2 GB of free memory.

`--carre` option: during a Codec call, **Square** cuts the voice and runs through all remaining lines at once, as if you were mashing the button (X keeps its original role: it cuts the voice, then one line per press). Choices (save, yes/no) are not skipped. The patch also works on its own, on an image you already built:

```bash
python carre.py "Metal Gear Solid (VOSTFR) (Disc 1).bin" "Metal Gear Solid (VOSTFR) (Disc 2).bin"
```

Give **both discs**: disc 2's sound test table is also used to pair disc 1's voices exactly.

## How it works

### Cutscenes

In both PAL versions, every cutscene in `DEMO.DAT` has **exactly the same sequence of audio blocks** (same count, same size): the French dub was fitted to the length of each scene. We keep the French `DEMO.DAT` (subtitles, animations) and copy the English audio into it block by block. The French subtitles land right on the English lines.

### Codec and in-game voices

Here the two dubs have different lengths: the English `VOX.DAT` is 196 MB against 182 MB in French (disc 1).

1. **Pairing the voices**: both `VOX.DAT` files store their ~1100 banks in the same order, with a few extra banks on the English side. The game contains a sound test table (`vc000101` → bank) with the same names in FR and UK: exact pairing on disc 2, carried over to disc 1 through the banks both discs share. The rest is aligned by dynamic programming (audio length, subtitle count), then checked against the Codec calls in the script.
2. **New `VOX.DAT`**: each English bank (voice and lip movements) gets the French subtitles (same number of lines as the French bank, French font), with the English version's timings. In the Codec, each subtitle moves on to the next line of the French `RADIO.DAT` script, so the text follows the English voice.
3. **Renumbering**: the VOX codes (position in the file) of the VOICE commands in `RADIO.DAT` and of the `STAGE.DIR` scripts are rewritten. In `STAGE.DIR`, a code is only changed if the same English stage holds the matching code (no false positives in textures).
4. **Disc image**: `VOX.DAT` grows, so `ZMOVIE.STR` and `DUMMY3M.DAT` are shifted (raw sectors copied), the ISO 9660 directory records and the volume size are rewritten, and EDC/ECC recomputed. The game finds its files by name at boot: no other address to fix.

Two lines on disc 2 only exist in French (one of them a German leftover on the French disc): they stay in French.

## Tools

| Script | Purpose |
|---|---|
| `tools/build.py` | Builds the VOSTFR images |
| `tools/chd2bin.py` | CHD v5 → BIN/CUE (cdlz, cdzl), SHA-1 check |
| `tools/psxiso.py` | List, extract, EDC-check a PS1 image |
| `tools/cdsector.py` | Mode 2 Form 1 EDC/ECC (numpy), in-place file rewrite |
| `tools/isorebuild.py` | Rebuilds an image with files of a different size |
| `tools/vox.py` | `VOX.DAT` / `DEMO.DAT` banks: blocks, subtitles |
| `tools/voxalign.py` | Pairs the French and English VOX banks |
| `tools/vox_vostfr.py` | New `VOX.DAT`, `RADIO.DAT` and `STAGE.DIR` renumbering |
| `tools/radio.py` | `RADIO.DAT` codec script (TALK / VOICE commands) |
| `tools/demo_vostfr.py` | Cutscene audio replacement |
| `tools/carre.py` | Optional patch: Square fast-forwards the Codec |
| `tools/emu.py`, `tools/emu_drive.lua` | Automated testing in PCSX-Redux (screenshots) |
