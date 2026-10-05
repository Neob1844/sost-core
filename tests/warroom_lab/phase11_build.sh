#!/usr/bin/env bash
set -uo pipefail
SRC=/home/sost/SOST/sostcore/d1-p2p-autonomy
BR=$SRC/build-repro          # SAME path both builds (isolates temporal non-determinism)
OUT=/home/sost/SOST/sostcore/lab/repro; mkdir -p "$OUT"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF"
build_once(){
  local tag=$1
  rm -rf "$BR"; mkdir -p "$BR"
  ( cd "$BR" && cmake $FLAGS "$SRC" >"$OUT/cfg_$tag.log" 2>&1 && cmake --build . -j"$(nproc)" >"$OUT/build_$tag.log" 2>&1 )
  local rc=$?
  if [[ $rc -ne 0 ]]; then echo "BUILD $tag FAILED rc=$rc"; tail -20 "$OUT/build_$tag.log"; return 1; fi
  for b in sost-node sost-miner sost-cli; do
    [[ -f "$BR/$b" ]] && { sha256sum "$BR/$b" | awk -v t="$tag" -v n="$b" '{print n" "t" "$1}'; cp "$BR/$b" "$OUT/${b}.$tag"; }
  done
}
echo "=== PHASE 11 — reproducible build (same path, same flags, back-to-back) ==="
echo "flags: $FLAGS"
echo "--- BUILD A ---"; build_once A || exit 1
echo "--- BUILD B ---"; build_once B || exit 1
echo "=== HASH COMPARISON ==="
for b in sost-node sost-miner sost-cli; do
  ha=$(sha256sum "$OUT/${b}.A" 2>/dev/null|cut -d' ' -f1); hb=$(sha256sum "$OUT/${b}.B" 2>/dev/null|cut -d' ' -f1)
  if [[ -n "$ha" && "$ha" == "$hb" ]]; then echo "  REPRODUCIBLE  $b  $ha"
  else echo "  DIFFERS       $b"; echo "     A=$ha"; echo "     B=$hb"; fi
done
