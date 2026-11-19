#!/bin/bash
# Metal Gear Solid (PS1 recompiled, alexbeavs / psxrecomp) - Batocera "Ports" launcher, with the mods of
# MGS1-VOSTFR (French texts, Square scrolls the Codec, M9, bandana...).
#
#   /userdata/roms/ports/Metal Gear Solid.sh/run.sh    EmulationStation lists a folder with the .sh extension as a
#                                                      game and runs its run.sh; the quit keys are its padto.keys.
#
# One folder for both kinds of machine: bin/aarch64/ (Retroid Pocket 5 & co) and bin/x86_64/ (PC) hold the
# executable; the rest is shared: disc/ (the two USA Rev 1 discs, .cue + .bin), mods/ (the .psxmod packages,
# installed, and state.toml: which mods are on), saves/ (memory cards), game.toml, assets/, the settings.
# The recomp anchors all of that on the folder of $APPIMAGE (its AppImage support): it is set to this folder, so
# both executables read the same files.
HERE="$(cd "$(dirname "$0")" && pwd)"
GAMEDIR="$HERE"
ROMNAME="$(basename "$HERE")"
cd "$GAMEDIR" || exit 1
EXE=Metal_Gear_Solid_Recompiled
LOG="$GAMEDIR/mgs-stdout.log"
MACHINE="$(uname -m)"
EXEDIR="$GAMEDIR/bin/$MACHINE"
say() { echo "[batocera] $(date '+%F %T') $*" | tee -a "$LOG" >&2; }
: > "$LOG"

if [ ! -x "$EXEDIR/$EXE" ] && [ ! -f "$EXEDIR/$EXE" ]; then
    say "pas de version $MACHINE dans ce dossier (presentes : $(ls "$GAMEDIR/bin" 2>/dev/null | tr '\n' ' '))"
    exit 1
fi
chmod +x "$EXEDIR/$EXE" 2>/dev/null

# ---- Options from EmulationStation (ADVANCED GAME OPTIONS > METAL GEAR SOLID) ----
ES_CFG_DIR="${MGS_ES_CFG_DIR:-/userdata/system/configs/emulationstation}"
[ -f "$GAMEDIR/es_features_mgs.cfg.txt" ] && mv -f "$GAMEDIR/es_features_mgs.cfg.txt" "$GAMEDIR/es_features_mgs.cfg"
if [ -f "$GAMEDIR/es_features_mgs.cfg" ] && [ -d "$ES_CFG_DIR" ] && \
   ! cmp -s "$GAMEDIR/es_features_mgs.cfg" "$ES_CFG_DIR/es_features_mgs.cfg"; then
    cp "$GAMEDIR/es_features_mgs.cfg" "$ES_CFG_DIR/es_features_mgs.cfg"
fi
CONF="${MGS_BATOCERA_CONF:-/userdata/system/batocera.conf}"
conf_get() {
    local v=""
    [ -f "$CONF" ] || return 0
    v=$(grep -F "ports[\"$ROMNAME\"].$1=" "$CONF" | tail -1 | cut -d= -f2-)
    [ -z "$v" ] && v=$(grep -E "^ports\.$1=" "$CONF" | tail -1 | cut -d= -f2-)
    echo "$v"
}

# Disc: 1 or 2 from the menu; "auto" (default) = the one of the last start (disc.txt). The mods of each disc are a
# separate package (soaresden.mgs1-mods.disc1 / disc2): the game reloads its EXE when the disc changes, the mods
# are then off until the next start; so at the end of disc 1, quit and start again on disc 2 (DISQUE in the menu).
DISC="$(conf_get mgs_disc)"
case "$DISC" in
    1|2) ;;
    *) DISC="$(cat "$GAMEDIR/disc.txt" 2>/dev/null | tr -dc 12 | head -c1)"; [ -n "$DISC" ] || DISC=1 ;;
esac
echo "$DISC" > "$GAMEDIR/disc.txt"
CUE="$(ls "$GAMEDIR"/disc/*"(Disc $DISC)"*.cue 2>/dev/null | head -1)"
if [ -z "$CUE" ]; then
    say "disque $DISC introuvable : mettez Metal Gear Solid (USA) (Disc $DISC) (Rev 1).cue et .bin dans $GAMEDIR/disc/"
    exit 1
fi

# Mods: the package of the disc, the features as left in mods/state.toml; French texts from the menu.
STATE="$GAMEDIR/mods/state.toml"
if [ -f "$STATE" ]; then
    sed -i -E "s/soaresden\.mgs1-mods\.disc[12]/soaresden.mgs1-mods.disc$DISC/" "$STATE"
    case "$(conf_get mgs_french)" in
        off) FR=false ;;
        *) FR=true ;;
    esac
    # enabled line of the codec-fr feature
    awk -v v="$FR" '
        /^\[\[feature\]\]/ { f = 0 }
        /^id = "codec-fr"/ { f = 1 }
        f && /^enabled = / { $0 = "enabled = " v }
        { print }' "$STATE" > "$STATE.tmp" && mv -f "$STATE.tmp" "$STATE"
fi

# BIOS: the build accepts SCPH-5501 (US); Batocera keeps the BIOS in /userdata/bios.
BIOS=""
for f in "$GAMEDIR/bios/scph5501.bin" /userdata/bios/scph5501.bin /userdata/bios/SCPH5501.BIN; do
    [ -f "$f" ] && BIOS="$f" && break
done
[ -n "$BIOS" ] || { say "BIOS scph5501.bin introuvable dans /userdata/bios"; exit 1; }

# SDL3 picks Wayland under Batocera's compositor, otherwise KMS/DRM or X11.
export SDL_VIDEO_DRIVER="${SDL_VIDEO_DRIVER:-wayland,kmsdrm,x11}"
command -v batocera-mouse >/dev/null 2>&1 && batocera-mouse hide >/dev/null 2>&1
export MESA_SHADER_CACHE_DIR="$GAMEDIR/cache/mesa"
mkdir -p "$MESA_SHADER_CACHE_DIR" "$GAMEDIR/saves"
export APPIMAGE="$GAMEDIR/$EXE"
RENDERER="$(conf_get mgs_renderer)"
ARGS=(--no-launcher --game "$GAMEDIR/game.toml" --disc "$CUE" --bios "$BIOS" --memcard-dir "$GAMEDIR/saves")
[ -n "$RENDERER" ] && [ "$RENDERER" != auto ] && ARGS+=(--renderer "$RENDERER")
{
    echo "[batocera] $(date '+%F %T') $(cat /usr/share/batocera/batocera.version 2>/dev/null) $(uname -r) bin/$MACHINE"
    echo "[batocera] disc $DISC: $CUE ; BIOS $BIOS ; french texts ${FR:-?} ; renderer ${RENDERER:-auto}"
    echo "[batocera] WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} DISPLAY=${DISPLAY:-} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}"
} >> "$LOG"
exec "$EXEDIR/$EXE" "${ARGS[@]}" >> "$LOG" 2>&1
