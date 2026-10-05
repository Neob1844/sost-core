#!/usr/bin/env bash
set -uo pipefail
OUT=/home/sost/SOST/sostcore/lab/gate12; rm -rf "$OUT"; mkdir -p "$OUT"
V30=/home/sost/SOST/sostcore/lab-old-v30000
CAND=/home/sost/SOST/sostcore/d1-p2p-autonomy
FLAGS="-DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF"
build(){
  local src="$1"; local tag="$2"; local bdir="$src/build-gate12"
  local map="-ffile-prefix-map=${src}=/sost -ffile-prefix-map=${bdir}=/build"
  rm -rf "$bdir"; mkdir -p "$bdir"
  ( cd "$bdir" && cmake $FLAGS -DCMAKE_C_FLAGS="$map" -DCMAKE_CXX_FLAGS="$map" "$src" >"$OUT/cfg_$tag.log" 2>&1 \
      && cmake --build . -j"$(nproc)" >"$OUT/build_$tag.log" 2>&1 )
  local rc=$?
  if [[ $rc -ne 0 ]]; then echo "BUILD $tag FAILED rc=$rc"; tail -15 "$OUT/build_$tag.log"; return 1; fi
  local b
  for b in sost-node sost-miner sost-cli; do [[ -f "$bdir/$b" ]] && cp "$bdir/$b" "$OUT/${b}.$tag"; done
  return 0
}
echo "=== GATE 1+2 — identical-env build of v30000 vs candidate (prefix-mapped) ==="
echo "flags: $FLAGS + -ffile-prefix-map (source path neutralized to /sost)"
echo "--- V30000 (c9e0d629) at $V30 ---"; build "$V30" V30 || exit 1
echo "--- CANDIDATE (9e6223dc) at $CAND ---"; build "$CAND" CAND || exit 1
echo; echo "=== HASHES (both built identical flags/toolchain, path-neutralized) ==="
for b in sost-node sost-miner sost-cli; do
  hv=$(sha256sum "$OUT/${b}.V30" 2>/dev/null|cut -d' ' -f1); hc=$(sha256sum "$OUT/${b}.CAND" 2>/dev/null|cut -d' ' -f1)
  echo "  $b"; echo "     V30000   : ${hv:-MISSING}"; echo "     CANDIDATE: ${hc:-MISSING}"
  if [[ -n "$hv" && "$hv" == "$hc" ]]; then echo "     => IDENTICAL"
  else echo "     => DIFFERS ($(cmp "$OUT/${b}.V30" "$OUT/${b}.CAND" 2>&1|head -1))"; fi
done
echo; echo "=== GATE 1 VERDICT ==="
mv=$(sha256sum "$OUT/sost-miner.V30" 2>/dev/null|cut -d' ' -f1); mc=$(sha256sum "$OUT/sost-miner.CAND" 2>/dev/null|cut -d' ' -f1)
cv=$(sha256sum "$OUT/sost-cli.V30" 2>/dev/null|cut -d' ' -f1); cc=$(sha256sum "$OUT/sost-cli.CAND" 2>/dev/null|cut -d' ' -f1)
nv=$(sha256sum "$OUT/sost-node.V30" 2>/dev/null|cut -d' ' -f1); nc=$(sha256sum "$OUT/sost-node.CAND" 2>/dev/null|cut -d' ' -f1)
[[ "$mv" == "$mc" ]] && echo "  MINER SOURCE FUNCTIONAL DIFF: NO (byte-identical same-env)" || echo "  MINER: DIFFERS"
[[ "$cv" == "$cc" ]] && echo "  CLI SOURCE FUNCTIONAL DIFF:   NO (byte-identical same-env)" || echo "  CLI: DIFFERS"
[[ "$nv" != "$nc" ]] && echo "  NODE: DIFFERS (expected — sost-node.cpp +310/-36 is the only source delta)" || echo "  NODE: identical (unexpected!)"
