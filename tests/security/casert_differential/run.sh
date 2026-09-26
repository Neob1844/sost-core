#!/usr/bin/env bash
# Bit-exact differential of the ACTIVE cASERT regime (next_height>=5270 + slingshot V11/V12)
# vs an independent Python reimplementation. 0 divergences = PASS.
set -e
ROOT="${1:-$(git rev-parse --show-toplevel)}"
HERE="$(cd "$(dirname "$0")" && pwd)"
g++ -std=c++17 -O2 -I"$ROOT/include" "$HERE/dump.cpp" "$ROOT/src/pow/casert.cpp" -o "$HERE/dump"
"$HERE/dump" > "$HERE/dump.csv"
cd "$HERE" && python3 model.py
