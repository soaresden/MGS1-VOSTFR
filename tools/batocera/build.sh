#!/bin/bash
# build.sh - Port Batocera / Linux du recomp PC (alexbeavs, psxrecomp) : bin/x86_64 et bin/aarch64.
#
#   bash tools/batocera/build.sh [x86_64|aarch64|all]      (dans WSL Ubuntu)
#
# Source : le projet recomp généré en local (work/recomp/mgs : code C tiré du disque USA, psxrecomp),
# copié dans ~/mgs-port/src (disque Linux : bien plus rapide que /mnt/d). Rien n'est versionné :
# le code généré vient du jeu.
#   x86_64  : gcc de WSL ; SDL3 3.4.10 téléchargé et lié en statique par le projet (en-têtes X11,
#             Wayland, GL, ALSA, PulseAudio de WSL) ; glibc 2.43 = celle de Batocera 44.
#   aarch64 : chaîne et sysroot Batocera sm8250 (Retroid Pocket 5, ~/bato/batocera.linux/output/sm8250,
#             variable BATOCERA_SM8250) ; SDL3 du système (celle de Batocera).
# Assistant de première installation coupé ; l'interface (recomp-ui) reste pour le menu en jeu
# (Select + L3 : disques, options) ; run.sh lance le jeu avec --no-launcher (pas de lanceur).
# Sortie : work/batocera/bin/<processeur>/ (exécutable + ce qui doit être à côté).
set -eu
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
unset MAKEFLAGS MAKELEVEL MFLAGS
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SRC_WIN="$REPO/work/recomp/mgs"
W="$HOME/mgs-port"
TC="${BATOCERA_SM8250:-$HOME/bato/batocera.linux/output/sm8250/host}"
OUT="$REPO/work/batocera/bin"
EXE=Metal_Gear_Solid_Recompiled
ARCHS="${1:-all}"
[ "$ARCHS" = all ] && ARCHS="x86_64 aarch64"

mkdir -p "$W"
echo "== copie des sources ($(date +%T))"
rsync -a --exclude 'build-*' --exclude 'cache/' --exclude 'saves/' --exclude 'mods/' \
    --exclude 'disc/' --exclude '*.bak' --exclude 'diagnostics-*' "$SRC_WIN/" "$W/src/"
# produit sans interface : le jeu seul (le lanceur et l'assistant de première installation sont
# pour la version PC, ici c'est run.sh qui donne le disque, le BIOS et les mods)
sed -i -E 's/^set\(PSX_SETUP_WIZARD ON /set(PSX_SETUP_WIZARD OFF /' "$W/src/CMakeLists.txt"
sed -i -E '/^\s*ENABLE_SETUP_WIZARD\s*$/d' "$W/src/CMakeLists.txt"

# glslc (shaders Vulkan en SPIR-V) : pas dans la chaîne Batocera, qui a glslangValidator (hôte) ;
# petit adaptateur pour les arguments qu'emploie psxrecomp/tools/embed_spirv.py
# (--target-env=vulkan1.1 -O shader -o sortie)
GLSLANG="$TC/bin/glslangValidator"
GLSLC="$W/glslc"
cat > "$GLSLC" <<EOF2
#!/bin/bash
args=(); out=""; env=vulkan1.1
while [ \$# -gt 0 ]; do
    case "\$1" in
        --target-env=*) env="\${1#--target-env=}" ;;
        -O) ;;
        -o) out="\$2"; shift ;;
        *) args+=("\$1") ;;
    esac
    shift
done
LD_LIBRARY_PATH="$TC/lib" exec "$GLSLANG" -V --target-env "\$env" "\${args[@]}" -o "\$out"
EOF2
chmod +x "$GLSLC"

for A in $ARCHS; do
    B="$W/build-$A"
    echo "== $A : configuration ($(date +%T))"
    case "$A" in
        x86_64)
            cmake -S "$W/src" -B "$B" -G Ninja -DCMAKE_BUILD_TYPE=Release \
                -DGLSLC_EXE="$GLSLC" > "$W/configure-$A.log" 2>&1 || { tail -40 "$W/configure-$A.log"; exit 1; }
            ;;
        aarch64)
            [ -x "$TC/bin/cmake" ] || { echo "chaîne Batocera sm8250 introuvable : $TC"; exit 1; }
            export BR_NO_CCACHE=1
            "$TC/bin/cmake" -S "$W/src" -B "$B" -G Ninja -DCMAKE_MAKE_PROGRAM="$TC/bin/ninja" \
                -DCMAKE_TOOLCHAIN_FILE="$TC/share/buildroot/toolchainfile.cmake" \
                -DCMAKE_BUILD_TYPE=Release -DGLSLC_EXE="$GLSLC" \
                -DCCACHE_PROGRAM=CCACHE_PROGRAM-NOTFOUND -DCMAKE_C_COMPILER_LAUNCHER= -DCMAKE_CXX_COMPILER_LAUNCHER= \
                > "$W/configure-$A.log" 2>&1 || { tail -40 "$W/configure-$A.log"; exit 1; }
            ;;
        *) echo "processeur inconnu : $A"; exit 1 ;;
    esac
    echo "== $A : compilation ($(date +%T))"
    CM=cmake; [ "$A" = aarch64 ] && CM="$TC/bin/cmake"
    "$CM" --build "$B" --target psx-runtime > "$W/build-$A.log" 2>&1 || { grep -m20 -E "error|Error" "$W/build-$A.log"; tail -20 "$W/build-$A.log"; exit 1; }
    echo "== $A : copie vers $OUT/$A ($(date +%T))"
    rm -rf "$OUT/$A"
    mkdir -p "$OUT/$A"
    cp "$B/$EXE" "$OUT/$A/"
    [ -d "$B/overlay_toolchain" ] && cp -r "$B/overlay_toolchain" "$OUT/$A/"
    # commun aux deux processeurs (à la racine du port) : config du jeu, images, polices, licences
    C="$REPO/work/batocera/common"
    mkdir -p "$C"
    for f in game.toml assets licenses psx_game_version.txt; do
        [ -e "$B/$f" ] && rm -rf "$C/$f" && cp -r "$B/$f" "$C/"
    done
    file "$OUT/$A/$EXE"
done
echo "== fini ($(date +%T))"
