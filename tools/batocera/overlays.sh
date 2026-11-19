#!/bin/bash
# overlays.sh - Pre-compiles MGS's overlays (the code of each area, loaded from the disc) into native ARM code for
# the Batocera port, in WSL.
#
#   bash tools/batocera/overlays.sh [captures.json ...]
#
# Without a compiler, the aarch64 build runs the overlays in its interpreter: slow on the Retroid (sound breaks up).
# The recomp's own overlay toolchain (Python + TinyCC) only exists for Windows. So the overlays are compiled here,
# with the gcc of the Batocera toolchain, from overlay_captures.json: the runtime records in that file each overlay it
# meets ([runtime] overlay_cache = true), on any machine (the bytes come from the disc, they are the same everywhere).
#   default inputs: work/recomp/mgs/build-diagnostic/overlay_captures.json (PC) and work/batocera/captures/*.json
#                   (copies of "Metal Gear Solid.sh/overlay_captures.json" from the consoles)
#   output        : work/batocera/cache/SLUS-00594/gcc/linux-arm64/<tag>/  -> make_port.py puts it in the port
# compile_overlays.py loads each shard to check it, with a Python of the target's architecture: the Python of the
# Batocera target, run by the toolchain's qemu-aarch64. Incremental: the shards already built are kept.
set -e
TC="${TC:-$HOME/bato/batocera.linux/output/sm8250/host}"
TARGET="${TARGET:-$HOME/bato/batocera.linux/output/sm8250/target}"
W="${W:-$HOME/mgs-port}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PORT="$REPO/work/batocera/Metal Gear Solid.sh"
SRC="$W/src/psxrecomp"
OUT="$REPO/work/batocera/cache"
[ -f "$PORT/game.toml" ] || { echo "lancer d'abord make_port.py (il faut $PORT/game.toml)"; exit 1; }
[ -d "$SRC" ] || { echo "sources absentes : lancer d'abord build.sh"; exit 1; }

# The recompiler, for this machine (it only writes C).
if [ ! -x "$W/recompiler-host/psxrecomp-game" ] || [ "$SRC/recompiler" -nt "$W/recompiler-host/psxrecomp-game" ]; then
    cmake -S "$SRC/recompiler" -B "$W/recompiler-host" -G Ninja -DCMAKE_BUILD_TYPE=Release > "$W/recompiler-host.log" 2>&1
    cmake --build "$W/recompiler-host" --target psxrecomp-game -j"$(nproc)" >> "$W/recompiler-host.log" 2>&1
fi
# game.toml and the EXE of the port (the cache name hashes the game config; the EXE gives the cross-image calls).
G="$W/ovl/game"; mkdir -p "$G/disc" "$W/ovl/cache"
cp "$PORT/game.toml" "$G/"; cp "$PORT/disc/SLUS_005.94" "$PORT/disc/SYSTEM.CNF" "$G/disc/"

CAPS=("$@")
if [ ${#CAPS[@]} -eq 0 ]; then
    for f in "$REPO/work/recomp/mgs/build-diagnostic/overlay_captures.json" "$REPO"/work/batocera/captures/*.json; do
        [ -f "$f" ] && CAPS+=("$f")
    done
fi
[ ${#CAPS[@]} -gt 0 ] || { echo "aucune capture d'overlays"; exit 1; }
PY=("$TC/bin/qemu-aarch64" -L "$TARGET" "$TARGET/usr/bin/python3")
for c in "${CAPS[@]}"; do
    echo "== $c"
    cp "$c" "$W/ovl/captures.json"
    "${PY[@]}" "$SRC/tools/compile_overlays.py" --captures "$W/ovl/captures.json" --game-toml "$G/game.toml" \
        --recompiler "$W/recompiler-host/psxrecomp-game" --runtime-include "$SRC/runtime/include" \
        --out-dir "$W/ovl/cache" --gcc "$TC/bin/aarch64-buildroot-linux-gnu-gcc" \
        --target-os linux --arch-abi linux-arm64 --cps --jobs "$(nproc)" > "$W/ovl/compile.log" 2>&1 \
        || { tail -30 "$W/ovl/compile.log"; exit 1; }
    grep -E '^  (built OK|skipped|FAILED)' "$W/ovl/compile.log" || true
done
# the cache without the build's lock files
mkdir -p "$OUT"
(cd "$W/ovl/cache" && find . -type f ! -name '.*' -print0 | tar --null -cf - -T -) | (cd "$OUT" && tar -xf -)
echo "cache : $OUT ($(find "$OUT" -name '*.so' | wc -l) zones)"
