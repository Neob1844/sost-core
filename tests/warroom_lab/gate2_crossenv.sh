#!/usr/bin/env bash
set -uo pipefail
SRC=/home/sost/SOST/sostcore/d1-p2p-autonomy
ENVB=/tmp/envB_src
OUT=/home/sost/SOST/sostcore/lab/gate12
echo "=== ENV B: copia a ruta distinta ($ENVB), entorno scrubbed, prefix-mapped ==="
rm -rf "$ENVB"; mkdir -p "$ENVB"
# copiar fuentes + vendor (sin build dirs) a una ruta totalmente distinta
rsync -a --exclude 'build*' --exclude '.git' "$SRC/" "$ENVB/" 2>/dev/null || cp -r "$SRC"/{src,include,tests,vendor,CMakeLists.txt,cmake} "$ENVB/" 2>/dev/null
BDIR="$ENVB/build-envb"; mkdir -p "$BDIR"
MAP="-ffile-prefix-map=$ENVB=/sost -ffile-prefix-map=$BDIR=/build"
FLAGS="-DCMAKE_BUILD_TYPE=Release -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF"
# scrubbed env: only PATH; drop SOURCE_DATE_EPOCH, PWD-derived vars, etc.
( cd "$BDIR" && env -i PATH=/usr/bin:/bin HOME="$ENVB" \
    cmake $FLAGS -DCMAKE_C_FLAGS="$MAP" -DCMAKE_CXX_FLAGS="$MAP" "$ENVB" >/tmp/envb_cfg.log 2>&1 \
    && env -i PATH=/usr/bin:/bin HOME="$ENVB" cmake --build . --target sost-node sost-miner sost-cli -j"$(nproc)" >/tmp/envb_build.log 2>&1 )
rc=$?
[[ $rc -ne 0 ]] && { echo "ENVB BUILD FAILED rc=$rc"; tail -20 /tmp/envb_build.log; exit 1; }
echo "ENV B build OK"
echo "=== cross-ENV comparison (ENV A = gate12 CAND  vs  ENV B scrubbed+diff-path) ==="
for b in sost-node sost-miner sost-cli; do
  ha=$(sha256sum "$OUT/${b}.CAND" 2>/dev/null|cut -d' ' -f1)
  hb=$(sha256sum "$BDIR/$b" 2>/dev/null|cut -d' ' -f1)
  echo "  $b"; echo "     ENV A: ${ha:-MISSING}"; echo "     ENV B: ${hb:-MISSING}"
  [[ -n "$ha" && "$ha" == "$hb" ]] && echo "     => REPRODUCIBLE cross-env" || echo "     => DIFFERS"
done
