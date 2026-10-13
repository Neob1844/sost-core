#!/usr/bin/env bash
# =============================================================================
# full_verify_early_chain.sh — reproduce and bound the `--full-verify` failure
# on the real mainnet chain (docs/verification/FULL_VERIFY_EARLY_CHAIN.md).
#
#   CHAIN=<copy of mainnet chain.json> BUILD=<build dir> \
#     scripts/verification/full_verify_early_chain.sh [scan|node|reverify|all]
#
#   scan  (cheap, ~1 min): dumps every block of the transcript-less window
#         (1..3300) and runs test-full-verify-early-chain on all of them:
#         transcript absent, commit binds with the stab_*-derived profile,
#         stability basin + metric hold.
#   node  (~1 min): starts a local server node on a COPY of the chain and an
#         empty `sost-node --full-verify --verbose` that syncs from it only.
#         PASS = the client finds no Transcript V2 data in block 1, classifies
#         it UNVERIFIABLE_MISSING_HISTORICAL_DATA (after the transcript-free
#         checks pass) and rejects it: plain --full-verify stays strict.
#   classify (~30-60 min, not part of `all`): serves the chain truncated at
#         TIP (default 3500) from a local server node and syncs three empty
#         clients from it: (1) `--full-verify` (strict) must reject block 1 as
#         UNVERIFIABLE_MISSING_HISTORICAL_DATA after its transcript-free checks
#         pass; (2) `--full-verify-anchored-history` must reach TIP with
#         ASSUMED_FROM_HISTORICAL_RULE=3300 (all pinned to hard checkpoint 3300)
#         and VERIFIED=TIP-3300; (3) the default node must reach TIP too, with
#         the same block_id at every height as (2) and as the source chain,
#         and both persist a byte-identical chain.json. With BASE_NODE set to a
#         sost-node built from the parent commit, its default sync must persist
#         the same bytes and log the same [BLOCK] decisions.
#   reverify (heavy, ~8.4 GB RAM, ~20 s per block; not part of `all`): redoes
#         the full ConvergenceX work with cx-reverify for REVERIFY_HEIGHTS
#         (default: one block per profile class + 3300) or, with
#         REVERIFY_HEIGHTS=all, for the whole window (~18 h single-threaded).
#         The profile comes from the stored stab_* params via the legacy table.
#
# Local only: --noseed, the server's only peer is a dead 127.0.0.1:1, the client
# connects only to the server. Ports NODE_PORT_BASE (default 23400) +1..+12
# (node), CLASSIFY_PORT_BASE
# (default 24000) +1..+42 (classify). Never touches CHAIN itself.
# =============================================================================
set -Euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHAIN="${CHAIN:?set CHAIN to a COPY of the mainnet chain.json}"
BUILD="${BUILD:-$ROOT/build}"
MODE="${1:-all}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/fv-early.XXXXXX")"
FAILED=0
ok(){  printf '[fv-early] PASS  %s\n' "$*"; }
bad(){ printf '[fv-early] FAIL  %s\n' "$*"; FAILED=1; }
log(){ printf '[fv-early] %s\n' "$*"; }
S_PID=""; C_PID=""; A_PID=""; D_PID=""
cleanup(){ for p in "$C_PID" "$A_PID" "$D_PID" "$S_PID"; do [[ -n "$p" ]] && kill "$p" 2>/dev/null; done; wait 2>/dev/null; rm -f "$WORK/server/chain.json" "$WORK/cserver/chain.json"; true; }
trap cleanup EXIT

if [[ "$MODE" == scan || "$MODE" == all ]]; then
  log "dumping the transcript-less window from $CHAIN"
  python3 -I - "$CHAIN" "$WORK/window.txt" <<'PY'
import json, sys
bl = json.load(open(sys.argv[1]))['blocks']
last = 0
with open(sys.argv[2], 'w') as out:
    for b in bl[1:]:
        if b.get('checkpoint_leaves'):
            break
        last = b['height']
        out.write(' '.join(str(b[k]) for k in (
            'height', 'prev_hash', 'merkle_root', 'timestamp', 'bits_q', 'nonce',
            'extra_nonce', 'commit', 'checkpoints_root', 'segments_root',
            'final_state', 'x_bytes', 'stability_metric', 'stab_scale', 'stab_k',
            'stab_margin', 'stab_steps', 'stab_lr_shift')) + '\n')
print(last)
PY
  last=$(wc -l < "$WORK/window.txt")
  [[ "$last" == 3300 ]] && ok "transcript-less window is exactly 1..3300" || bad "window size $last (expected 3300)"
  if "$BUILD/test-full-verify-early-chain" "$WORK/window.txt" | tail -3; then
    ok "every block 1..3300: commit binding + stability basin + metric verify; transcript absent"
  else
    bad "window scan reported failures"
  fi
fi

if [[ "$MODE" == node || "$MODE" == all ]]; then
  NODE="$BUILD/sost-node"; GEN="$ROOT/genesis_block.json"
  mkdir -p "$WORK/server" "$WORK/client"
  cp "$CHAIN" "$WORK/server/chain.json"
  SP=$(( ${NODE_PORT_BASE:-23400} + 1 )); CP=$(( ${NODE_PORT_BASE:-23400} + 11 ))
  ( cd "$WORK/server" && exec "$NODE" --profile mainnet --genesis "$GEN" --chain chain.json \
      --connect 127.0.0.1:1 --noseed --port $SP --rpc-port $((SP+1)) --rpc-noauth ) >"$WORK/server.log" 2>&1 &
  S_PID=$!
  for _ in $(seq 1 300); do grep -q '^Chain:' "$WORK/server.log" && break; sleep 1; done
  grep '^Chain:' "$WORK/server.log" || { bad "server did not load the chain"; exit 1; }
  ( cd "$WORK/client" && exec "$NODE" --profile mainnet --genesis "$GEN" --chain chain.json \
      --connect 127.0.0.1:$SP --noseed --port $CP --rpc-port $((CP+1)) --rpc-noauth \
      --full-verify --verbose ) >"$WORK/client.log" 2>&1 &
  C_PID=$!
  for _ in $(seq 1 120); do grep -q 'CX Transcript V2 verification failed' "$WORK/client.log" && break; sleep 1; done
  grep -m4 -E 'BLOCK-V2\] Parsed|FULL-VERIFY\]|REJECTED' "$WORK/client.log" || true
  if grep -q 'cp_leaves=0 seg_proofs=0 rw=0' "$WORK/client.log" \
     && grep -q 'h=1 class=UNVERIFIABLE_MISSING_HISTORICAL_DATA' "$WORK/client.log" \
     && grep -q 'REJECTED: CX Transcript V2 verification failed' "$WORK/client.log"; then
    ok "reproduced: plain --full-verify finds no Transcript V2 data in block 1, runs the transcript-free checks, classifies it UNVERIFIABLE_MISSING_HISTORICAL_DATA and rejects it"
  else
    bad "expected UNVERIFIABLE rejection of block 1 not observed (see $WORK/client.log)"
  fi
fi

if [[ "$MODE" == classify ]]; then
  NODE="$BUILD/sost-node"; GEN="$ROOT/genesis_block.json"
  TIP="${TIP:-3500}"; BASE="${CLASSIFY_PORT_BASE:-24000}"
  mkdir -p "$WORK/cserver" "$WORK/strict" "$WORK/anchored" "$WORK/default"
  python3 -I - "$CHAIN" "$WORK/cserver/chain.json" "$TIP" <<'PY'
import json, sys
d = json.load(open(sys.argv[1])); t = int(sys.argv[3])
d['blocks'] = d['blocks'][:t + 1]; d['chain_height'] = t; d['tip'] = d['blocks'][-1]['block_id']
json.dump(d, open(sys.argv[2], 'w'))
PY
  SP=$((BASE+1))
  ( cd "$WORK/cserver" && exec nice -n 19 "$NODE" --profile mainnet --genesis "$GEN" --chain chain.json \
      --connect 127.0.0.1:1 --noseed --port $SP --rpc-port $((SP+1)) --rpc-noauth ) >"$WORK/cserver.log" 2>&1 &
  S_PID=$!
  for _ in $(seq 1 300); do grep -q '^Chain:' "$WORK/cserver.log" && break; sleep 1; done
  grep '^Chain:' "$WORK/cserver.log" || { bad "server did not load the chain"; exit 1; }
  start_client(){ # dir port flags...
    local dir=$1 port=$2; shift 2
    ( cd "$WORK/$dir" && exec nice -n 19 "$NODE" --profile mainnet --genesis "$GEN" --chain chain.json \
        --connect 127.0.0.1:$SP --noseed --port $port --rpc-port $((port+1)) --rpc-noauth "$@" ) >"$WORK/$dir.log" 2>&1 &
  }
  rpc(){ curl -s --max-time 20 -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":[$3]}" http://127.0.0.1:$1/ ; }
  # (1) strict --full-verify
  start_client strict $((BASE+11)) --full-verify; C_PID=$!
  for _ in $(seq 1 120); do grep -q 'REJECTED: CX Transcript V2 verification failed' "$WORK/strict.log" && break; sleep 1; done
  kill "$C_PID" 2>/dev/null; wait "$C_PID" 2>/dev/null; C_PID=""
  grep -m3 -E 'FULL-VERIFY\]|REJECTED' "$WORK/strict.log" || true
  if grep -q 'h=1 class=UNVERIFIABLE_MISSING_HISTORICAL_DATA' "$WORK/strict.log" \
     && ! grep -q 'class=ASSUMED_FROM_HISTORICAL_RULE' "$WORK/strict.log"; then
    ok "strict --full-verify: block 1 classified UNVERIFIABLE_MISSING_HISTORICAL_DATA and rejected"
  else
    bad "strict --full-verify did not classify block 1 as UNVERIFIABLE (see $WORK/strict.log)"
  fi
  # (2) anchored and (3) default, concurrently
  start_client anchored $((BASE+21)) --full-verify-anchored-history; A_PID=$!
  start_client default  $((BASE+31)); D_PID=$!
  t0=$(date +%s)
  while :; do
    ha=$(rpc $((BASE+22)) getblockcount "" | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("result",-1))' 2>/dev/null || echo -1)
    hd=$(rpc $((BASE+32)) getblockcount "" | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("result",-1))' 2>/dev/null || echo -1)
    [[ "$ha" == "$TIP" && "$hd" == "$TIP" ]] && break
    if ! kill -0 "$A_PID" 2>/dev/null || ! kill -0 "$D_PID" 2>/dev/null; then bad "a client exited early"; break; fi
    (( $(date +%s) - t0 > ${CLASSIFY_TIMEOUT:-10800} )) && { bad "timeout (anchored=$ha default=$hd)"; break; }
    sleep 20
  done
  log "anchored client at $ha, default client at $hd after $(( $(date +%s) - t0 )) s"
  for port in $((BASE+22)) $((BASE+32)); do
    : > "$WORK/ids.$port"
    for h in $(seq 0 "$TIP"); do
      rpc $port getblockhash "$h" | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("result"))' >> "$WORK/ids.$port"
    done
  done
  python3 -I - "$CHAIN" "$TIP" > "$WORK/ids.src" <<'PY'
import json, sys
for b in json.load(open(sys.argv[1]))['blocks'][:int(sys.argv[2]) + 1]: print(b['block_id'])
PY
  if cmp -s "$WORK/ids.src" "$WORK/ids.$((BASE+22))" && cmp -s "$WORK/ids.src" "$WORK/ids.$((BASE+32))"; then
    ok "block_id identical at every height 0..$TIP: source chain = --full-verify-anchored-history = default (tip $(tail -1 "$WORK/ids.src"))"
  else
    bad "block_id lists differ (ids.src / ids.$((BASE+22)) / ids.$((BASE+32)) in $WORK)"
  fi
  # Stop both clients (they persist chain.json on shutdown) and compare.
  kill "$A_PID" "$D_PID" 2>/dev/null; wait "$A_PID" "$D_PID" 2>/dev/null; A_PID=""; D_PID=""
  if cmp -s "$WORK/anchored/chain.json" "$WORK/default/chain.json"; then
    ok "persisted chain.json byte-identical: --full-verify-anchored-history = default ($(sha256sum < "$WORK/default/chain.json" | cut -c1-16)…)"
  else
    bad "persisted chain.json differs between the anchored and the default client"
  fi
  # Optional: the default path of a baseline binary (e.g. built from the
  # parent commit) must persist the very same bytes.
  if [[ -n "${BASE_NODE:-}" ]]; then
    mkdir -p "$WORK/basedefault"
    ( cd "$WORK/basedefault" && exec nice -n 19 "$BASE_NODE" --profile mainnet --genesis "$GEN" --chain chain.json \
        --connect 127.0.0.1:$SP --noseed --port $((BASE+41)) --rpc-port $((BASE+42)) --rpc-noauth ) >"$WORK/basedefault.log" 2>&1 &
    D_PID=$!
    t0=$(date +%s)
    until [[ "$(rpc $((BASE+42)) getblockcount "" | python3 -I -c 'import json,sys; print(json.load(sys.stdin).get("result",-1))' 2>/dev/null)" == "$TIP" ]]; do
      (( $(date +%s) - t0 > 3600 )) && { bad "baseline default client timeout"; break; }
      sleep 10
    done
    kill "$D_PID" 2>/dev/null; wait "$D_PID" 2>/dev/null; D_PID=""
    if cmp -s "$WORK/basedefault/chain.json" "$WORK/default/chain.json"; then
      ok "default path unchanged: baseline binary and this binary persist byte-identical chain.json at tip $TIP"
    else
      bad "baseline default chain.json differs from this binary's default chain.json"
    fi
    if diff <(grep -vE '^\[(P2P|P2PDBG|NET|RPC)' "$WORK/basedefault.log" | grep -E '^\[BLOCK\]' | sed 's/ (txs=.*//' | sort -u) \
            <(grep -vE '^\[(P2P|P2PDBG|NET|RPC)' "$WORK/default.log" | grep -E '^\[BLOCK\]' | sed 's/ (txs=.*//' | sort -u) >/dev/null; then
      ok "default path unchanged: identical [BLOCK] decision log (baseline vs this binary)"
    else
      bad "default [BLOCK] decision log differs (baseline vs this binary)"
    fi
  fi
  A=$(grep -c 'class=ASSUMED_FROM_HISTORICAL_RULE' "$WORK/anchored.log")
  V=$(grep -c '^\[BLOCK\] CX Transcript V2 verified' "$WORK/anchored.log")
  U=$(grep -c 'class=UNVERIFIABLE_MISSING_HISTORICAL_DATA' "$WORK/anchored.log")
  F=$(grep -c 'fast-sync height=' "$WORK/anchored.log")
  log "anchored client log: ASSUMED_FROM_HISTORICAL_RULE=$A VERIFIED=$V UNVERIFIABLE=$U fast-sync-skips=$F"
  grep -E 'FULL-VERIFY\] (summary|hard checkpoint)' "$WORK/anchored.log" | tail -16
  grep -m1 'FULL-VERIFY\] summary (end of transcript-less window)' "$WORK/anchored.log" \
    | grep -q 'VERIFIED=0 ASSUMED_FROM_HISTORICAL_RULE=3300 UNVERIFIABLE_MISSING_HISTORICAL_DATA=0 assumed_anchored_through=3300 assumed_unanchored_from=-1' \
    && ok "1..3300: 3300 ASSUMED_FROM_HISTORICAL_RULE, all pinned through hard checkpoint 3300, 0 VERIFIED, 0 UNVERIFIABLE" \
    || bad "window summary line not as expected"
  [[ "$A" == 3300 && "$V" == $((TIP-3300)) && "$U" == 0 && "$F" == 0 ]] \
    && ok "3301..$TIP: $V blocks VERIFIED (full Transcript V2), 0 fast-sync skips" \
    || bad "unexpected counts A=$A V=$V U=$U F=$F"
  log "derived non-B0 profiles in the window: $(grep -c 'derived from stored stab_\*' "$WORK/anchored.log") profile lines, $(grep 'derived from stored stab_' "$WORK/anchored.log" | grep -vc 'profile B0') non-B0"
fi

if [[ "$MODE" == reverify ]]; then
  HEIGHTS="${REVERIFY_HEIGHTS:-1 2 339 931 1001 3300}"
  python3 -I - "$CHAIN" "$WORK/reverify.txt" $HEIGHTS <<'PY'
import json, sys
from itertools import count
# Legacy (pre-V8) table rows (scale, steps, k, margin), index -4 (E4) .. +4 (H4).
LEG = [(1,2,3,280),(1,3,3,240),(1,4,3,225),(1,4,4,205),(1,4,4,185),
       (1,5,4,170),(1,5,5,160),(1,6,5,150),(1,6,6,145)]
bl = json.load(open(sys.argv[1]))['blocks']
hs = sys.argv[3:]
if hs == ['all']:
    hs = [b['height'] for b in bl[1:] if not b.get('checkpoint_leaves')]
with open(sys.argv[2], 'w') as out:
    for h in map(int, hs):
        b = bl[h]
        pi = LEG.index((b['stab_scale'], b['stab_steps'], b['stab_k'], b['stab_margin'])) - 4
        out.write(' '.join(map(str, (f"h{h}", h, b['prev_hash'], b['merkle_root'], b['timestamp'],
            b['bits_q'], b['nonce'], b['extra_nonce'], pi, b['stab_scale'], b['stab_k'],
            b['stab_margin'], b['stab_steps'], b['stab_lr_shift'], b['commit'],
            b['checkpoints_root'], b['segments_root'], b['final_state'],
            b['stability_metric']))) + '\n')
PY
  if "$BUILD/cx-reverify" < "$WORK/reverify.txt"; then
    ok "full ConvergenceX recompute matches commit/roots/final_state/metric for: $HEIGHTS"
  else
    bad "cx-reverify reported a mismatch"
  fi
fi

log "work dir: $WORK"
exit $FAILED
