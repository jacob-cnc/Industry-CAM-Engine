#!/bin/bash
# Build the offline X-vernier bench: the estimator core is extracted verbatim
# from rtcomp/xvernier.comp (CORE-BEGIN..CORE-END) so bench and RT module
# run the same code. No realtime, no HAL, no machine. usage: build_bench.sh OUTDIR
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
OUT=${1:-$HERE}
mkdir -p "$OUT"
sed -n '/CORE-BEGIN/,/CORE-END/p' "$HERE/../../rtcomp/xvernier.comp" > "$OUT/xv_core.h"
gcc -O2 -Wall -Wextra -std=gnu99 -Wno-misleading-indentation -I"$OUT" -o "$OUT/xv_bench" "$HERE/bench.c" -lm
echo "$OUT/xv_bench"
