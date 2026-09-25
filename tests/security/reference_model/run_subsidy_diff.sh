#!/usr/bin/env bash
# Phase C differential test: independent Python model vs the real C++ subsidy.cpp.
# Exits non-zero on ANY divergence. Usage: ./run_subsidy_diff.sh [repo_root]
set -euo pipefail
ROOT="${1:-$(cd "$(dirname "$0")/../../.." && pwd)}"
TMP=$(mktemp -d)
g++ -std=c++17 -O2 -I "$ROOT/include" "$ROOT/tests/security/reference_model/subsidy_dump.cpp" "$ROOT/src/subsidy.cpp" -o "$TMP/dump"
python3 - > "$TMP/heights.txt" <<'PY'
E=131553; hs=set(range(0,30001))
for k in range(0,60):
    for d in (-2,-1,0,1,2):
        h=k*E+d
        if h>=0: hs.add(h)
for h in (100000,500000,1000000,2000000,5000000,7000000,7500000,7900000,7900001,10000000,50000000): hs.add(h)
for h in sorted(hs): print(h)
PY
"$TMP/dump" < "$TMP/heights.txt" > "$TMP/cpp.out"
python3 "$ROOT/tests/security/reference_model/subsidy_model.py" --batch < "$TMP/heights.txt" > "$TMP/py.out"
n=$(wc -l < "$TMP/heights.txt")
if diff -q "$TMP/cpp.out" "$TMP/py.out" >/dev/null; then
  echo "PASS: subsidy/cumulative identical C++ vs reference model over $n heights"; rm -rf "$TMP"; exit 0
else
  echo "FAIL: divergence"; diff "$TMP/cpp.out" "$TMP/py.out" | head; rm -rf "$TMP"; exit 1
fi
