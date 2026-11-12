#!/bin/bash
# Build the offline vernier replay tool: the estimator core is extracted verbatim
# from rtcomp/xvernier.comp (CORE-BEGIN..CORE-END), same as tests/xvernier/build_bench.sh.
# No realtime, no HAL, no machine.  usage: build_replay.sh [OUTDIR]  (default: a temp dir)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$(mktemp -d)}
mkdir -p "$OUT"
sed -n '/CORE-BEGIN/,/CORE-END/p' "$HERE/../../rtcomp/xvernier.comp" > "$OUT/xv_core.h"
gcc -O2 -Wall -Wextra -std=gnu99 -Wno-misleading-indentation -Wno-unused-function \
    -I"$OUT" -o "$OUT/xv_replay" "$HERE/replay.c" -lm
echo "$OUT/xv_replay"
