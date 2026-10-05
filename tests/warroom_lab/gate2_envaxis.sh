#!/usr/bin/env bash
set -uo pipefail
SRC=/home/sost/SOST/sostcore/d1-p2p-autonomy
OUT=/home/sost/SOST/sostcore/lab/gate12
BDIR="$SRC/build-gate12"   # SAME path as the gate12 CAND build (same vendor, same source)
MAP="-ffile-prefix-map=$SRC=/sost -ffile-prefix-map=$BDIR=/build"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF"
echo "=== ENV-AXIS: rebuild candidate SAME path, env -i scrubbed (only env differs vs gate12 CAND) ==="
rm -rf "$BDIR"; mkdir -p "$BDIR"
( cd "$BDIR" && env -i PATH=/usr/bin:/bin HOME=/root \
    cmake $FLAGS -DCMAKE_C_FLAGS="$MAP" -DCMAKE_CXX_FLAGS="$MAP" "$SRC" >/tmp/ea_cfg.log 2>&1 \
    && env -i PATH=/usr/bin:/bin HOME=/root cmake --build . --target sost-node sost-miner sost-cli -j"$(nproc)" >/tmp/ea_build.log 2>&1 )
[[ $? -ne 0 ]] && { echo "FAILED"; tail -15 /tmp/ea_build.log; exit 1; }
echo "build OK (scrubbed env, same path)"
for b in sost-node sost-miner sost-cli; do
  ha=$(sha256sum "$OUT/${b}.CAND"|cut -d' ' -f1); hb=$(sha256sum "$BDIR/$b"|cut -d' ' -f1)
  echo "  $b: gate12(normal env)=$ha  scrubbed=$hb"
  if [[ "$ha" == "$hb" ]]; then echo "     => IDENTICAL (env-independent at same path)"
  else echo "     => DIFFERS at same path — locating..."; cmp "$OUT/${b}.CAND" "$BDIR/$b" 2>&1|head -1|sed 's/^/        /'; fi
done
# if miner differs even same-path/different-env, find WHERE (strings diff of the sections)
if ! cmp -s "$OUT/sost-miner.CAND" "$SRC/build-gate12/sost-miner"; then
  echo "=== localizar divergencia en miner (readelf sections + strings) ==="
  comm -3 <(strings "$OUT/sost-miner.CAND"|sort -u) <(strings "$SRC/build-gate12/sost-miner"|sort -u) 2>/dev/null | grep -iE "/home|/root|/tmp|gcc|GNU|build|/sost" | head -10
fi
