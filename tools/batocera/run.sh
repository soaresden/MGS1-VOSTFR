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

# Mods: the package of the disc; each feature (mod) of mods/state.toml from the menu: French texts in the first
# submenu, the other mods in METAL GEAR SOLID - MODS (mgs_mod_<id>: on / off; for the life bar, its text or off).
# An option left on its default keeps what state.toml says: the game's own menu (Select + L3 > Mods) writes it
# too (the port ships the French texts on and the test mod "armes" off).
STATE="$GAMEDIR/mods/state.toml"
if [ -f "$STATE" ]; then
    sed -i -E "s/soaresden\.mgs1-mods\.disc[12]/soaresden.mgs1-mods.disc$DISC/" "$STATE"
    case "$(conf_get mgs_french)" in
        off) FR=false ;;
        on) FR=true ;;
        *) FR="" ;;
    esac
    SET=""
    [ -n "$FR" ] && SET="codec-fr=$FR"
    LIFE_TEXT=""
    for id in $(sed -n -E 's/^id = "([a-z0-9-]+)"$/\1/p' "$STATE"); do
        [ "$id" = codec-fr ] && continue
        v="$(conf_get "mgs_mod_${id//-/_}")"
        case "$v" in
            on) SET="$SET $id=true" ;;
            off) SET="$SET $id=false" ;;
            "") ;;
            *) [ "$id" = life ] && { SET="$SET life=true"; LIFE_TEXT="$v"; } ;;
        esac
    done
    awk -v set="$SET" -v life="$LIFE_TEXT" '
        BEGIN { n = split(set, a, " "); for (i = 1; i <= n; i++) { split(a[i], kv, "="); want[kv[1]] = kv[2] } }
        /^\[\[feature\]\]/ { id = "" }
        /^id = "/ { id = $0; sub(/^id = "/, "", id); sub(/"$/, "", id) }
        /^enabled = / && (id in want) { $0 = "enabled = " want[id] }
        /^life_text = / && life != "" { $0 = "life_text = \"" life "\"" }
        { print }' "$STATE" > "$STATE.tmp" && mv -f "$STATE.tmp" "$STATE"
    MODS_ON="$(awk '/^id = "/ { id = $3 } /^enabled = true/ { gsub(/"/, "", id); printf "%s ", id }' "$STATE")"
fi

# Player settings (settings.toml next to the "exe", i.e. this folder; the in-game menu writes it too): the keys
# below are set at each start from the menu, the others are left as the player set them in game.
SETTINGS="$GAMEDIR/settings.toml"
toml_set() {  # toml_set <section> <key> <value as TOML>: replace or add the key in [section]
    [ -f "$SETTINGS" ] || printf 'settings_format = 2\n' > "$SETTINGS"
    awk -v s="[$1]" -v k="$2" -v v="$3" '
        function put() { if (!done) { print k " = " v; done = 1 } }
        /^\[/ { if (in_s) put(); in_s = ($0 == s); seen = seen || in_s }
        in_s && $0 ~ "^" k "[ \t]*=" { put(); next }
        { print }
        END { if (in_s) put(); else if (!seen) { print ""; print s; print k " = " v } }' \
        "$SETTINGS" > "$SETTINGS.tmp" && mv -f "$SETTINGS.tmp" "$SETTINGS"
}
grep -q '^settings_format' "$SETTINGS" 2>/dev/null || { [ -f "$SETTINGS" ] && sed -i '1i settings_format = 2' "$SETTINGS"; }
toml_set video fullscreen 1                        # borderless, the size of the screen
case "$(conf_get mgs_ratio)" in                    # IMAGE: 16/9 (default: the screen of the Retroid) or 4/3
    4/3|4:3) RATIO="4:3" ;;
    *) RATIO="16:9" ;;
esac
toml_set video aspect_ratio "\"$RATIO\""
case "$(conf_get mgs_bios_logo)" in                # LOGO PLAYSTATION: skipped by default
    on) toml_set video fast_boot false ;;
    *) toml_set video fast_boot true ;;
esac
case "$(conf_get mgs_render_thread)" in          # RENDU EN PARALLELE: the GL drawing on another core (OpenGL)
    off) toml_set video render_thread false ;;
    *) toml_set video render_thread true ;;
esac
# Player 1 = the first controller (the recomp's own default is the keyboard: its launcher, off here, picks the pad).
grep -Eq '^p1_device = "(none|keyboard)?"$' "$SETTINGS" && sed -i -E '/^p1_device = /d' "$SETTINGS"
grep -q '^p1_device = ' "$SETTINGS" || toml_set controller p1_device '"auto"'

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
# The underwater / heat-haze filters of the intro redraw the image over itself (tools/recomp-patches,
# widescreen-underwater-filter.patch): carried into the 16:9 bands too.
export PSX_WS_FEEDBACK_QUADS=1
# A handheld cannot hold full speed in every scene: the sound stretches a little (up to 10 %, lower pitch)
# instead of breaking up (runtime-audio-drc-env.patch; the recomp's own default is 0.5 %).
export PSX_AUDIO_MAX_CORRECTION="${PSX_AUDIO_MAX_CORRECTION:-0.10}"
export PSX_AUDIO_KP="${PSX_AUDIO_KP:-0.20}"
export PSX_AUDIO_SLEW="${PSX_AUDIO_SLEW:-20}"
# Diagnostics: a debug.env next to run.sh is read if present (e.g. export PSX_RUNTIME_PERF_DIAG=1).
[ -f "$GAMEDIR/debug.env" ] && . "$GAMEDIR/debug.env"
RENDERER="$(conf_get mgs_renderer)"
ARGS=(--no-launcher --game "$GAMEDIR/game.toml" --disc "$CUE" --bios "$BIOS" --memcard-dir "$GAMEDIR/saves")
[ -n "$RENDERER" ] && [ "$RENDERER" != auto ] && ARGS+=(--renderer "$RENDERER")
{
    echo "[batocera] $(date '+%F %T') $(cat /usr/share/batocera/batocera.version 2>/dev/null) $(uname -r) bin/$MACHINE"
    echo "[batocera] disc $DISC: $CUE ; BIOS $BIOS ; french texts ${FR:-(state.toml)} ; renderer ${RENDERER:-auto} ; image $RATIO"
    echo "[batocera] mods: ${MODS_ON:-?}"
    echo "[batocera] settings.toml:"; sed 's/^/    /' "$SETTINGS"
    echo "[batocera] WAYLAND_DISPLAY=${WAYLAND_DISPLAY:-} DISPLAY=${DISPLAY:-} XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-}"
} >> "$LOG"
exec "$EXEDIR/$EXE" "${ARGS[@]}" >> "$LOG" 2>&1
