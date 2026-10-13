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
#         PASS = the client rejects block 1 at verify_cx_proof Phase 1
#         ("checkpoint_leaves empty"), i.e. the failure is reproduced.
#   reverify (heavy, ~8.4 GB RAM, ~20 s per block; not part of `all`): redoes
#         the full ConvergenceX work with cx-reverify for REVERIFY_HEIGHTS
#         (default: one block per profile class + 3300) or, with
#         REVERIFY_HEIGHTS=all, for the whole window (~18 h single-threaded).
#         The profile comes from the stored stab_* params via the legacy table.
#
# Local only: --noseed, the server's only peer is a dead 127.0.0.1:1, the client
# connects only to the server. Ports 23400-23499. Never touches CHAIN itself.
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
S_PID=""; C_PID=""
cleanup(){ for p in "$C_PID" "$S_PID"; do [[ -n "$p" ]] && kill "$p" 2>/dev/null; done; wait 2>/dev/null; rm -f "$WORK/server/chain.json"; true; }
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
  SP=23401; CP=23411
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
  grep -m4 -E 'BLOCK-V2\] Parsed|profile_index missing|CX-VERIFY\] Phase 1|REJECTED' "$WORK/client.log" || true
  if grep -q 'Phase 1 FAILED: checkpoint_leaves empty' "$WORK/client.log" \
     && grep -q 'REJECTED: CX Transcript V2 verification failed' "$WORK/client.log"; then
    ok "reproduced: --full-verify rejects block 1 at verify_cx_proof Phase 1 (checkpoint_leaves empty)"
  else
    bad "expected Phase 1 rejection of block 1 not observed (see $WORK/client.log)"
  fi
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
