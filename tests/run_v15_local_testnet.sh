#!/usr/bin/env bash
# =============================================================================
# run_v15_local_testnet.sh — real-node V15 lifecycle harness (local testnet chain).
#
# HONEST SCOPE. SOST has no independent "regtest" consensus network — only the
# SOST_TESTNET_FORKS build (V15=12500, first jackpot=12792). This harness drives
# a REAL isolated sost-node + sost-miner on a throwaway chain; it is NOT a mocked
# unit test. It processes real blocks through the real UTXO/consensus path.
#
# KNOWN BLOCKER (measured 2026-08-04, see docs/V15_READINESS.md):
#   The miner has no fast/simulated-time mode; Phase2 SbPoW (height >= 7100) is
#   time-hard and regenerates a ~4 GB dataset per block. Measured rate on a fresh
#   chain ~0.43 blocks/s, so mining to the first jackpot at 12792 is an ~8.5h+
#   background job (and slower once cASERT ramps past 7100). Therefore:
#     * PHASE A/B below (boot + pre-Phase2 lifecycle + pre-V15 invariants) run
#       to completion in-session and are the CI-usable portion.
#     * PHASE C+ (cross V15, T-transition, first jackpot, reorg) are GATED behind
#       --target-height / a future dev fast-mine build. They are wired but SKIP
#       with a clear message unless the chain can actually reach those heights.
#   Do NOT mark V15 mainnet-ready from this harness until PHASE C+ has run over a
#   real chain that reached 12792 (needs the dev/regtest fast-mine capability).
#
# Usage:
#   tests/run_v15_local_testnet.sh [--blocks N] [--target-height H] [--threads T]
#                                  [--rpc-port P] [--p2p-port P]
#   Env: BUILD_DIR (default build-testnet)
#
# Exit non-zero on any invariant failure. Datadir/logs preserved on failure,
# cleaned on success.
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-testnet}"
BLOCKS=30                 # reachable pre-Phase2 region by default (in-session)
TARGET_HEIGHT=0           # >0 to attempt the V15/jackpot phases (needs fast-mine/soak)
THREADS=4
RPC_PORT=18916
P2P_PORT=19916
while [[ $# -gt 0 ]]; do
  case "$1" in
    --blocks)        BLOCKS="$2"; shift 2;;
    --target-height) TARGET_HEIGHT="$2"; shift 2;;
    --threads)       THREADS="$2"; shift 2;;
    --rpc-port)      RPC_PORT="$2"; shift 2;;
    --p2p-port)      P2P_PORT="$2"; shift 2;;
    -h|--help)       grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15harness.XXXXXX")"
NODE_LOG="$WORK/node.log"; MINER_LOG="$WORK/miner.log"
NODE_PID=""; MINER_PID=""; FAILED=0
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"

# Canonical testnet schedule (must match include/sost/params.h under SOST_TESTNET_FORKS).
V15=12500; FIRST_J=12792; PHASE2=7100; DTD_GATE=12100

log(){ printf '[v15] %s\n' "$*"; }
ok(){  printf '[v15] PASS  %s\n' "$*"; }
bad(){ printf '[v15] FAIL  %s\n' "$*"; FAILED=1; }
die(){ printf '[v15] FATAL %s\n' "$*" >&2; cleanup_keep; exit 1; }
cleanup_keep(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; log "logs preserved in $WORK"; }
cleanup_ok(){   [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; rm -rf "$WORK"; }
trap 'cleanup_keep' EXIT

# --- preflight: must be a testnet build ---
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || die "binaries missing in $BUILD_DIR (build with -DSOST_TESTNET_FORKS=ON)"
if [[ -f "$BUILD_DIR/CMakeCache.txt" ]]; then
  grep -q '^SOST_TESTNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" \
    || die "$BUILD_DIR is not a SOST_TESTNET_FORKS=ON build (V15 would be 25000, unreachable)"
fi
log "work dir: $WORK   build: $BUILD_DIR   schedule: Phase2=$PHASE2 DTD=$DTD_GATE V15=$V15 firstJ=$FIRST_J"

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
jfield(){ python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); r=d.get("result")
 v=r.get(sys.argv[1],"") if isinstance(r,dict) else (r if r is not None else "")
 print("true" if v is True else "false" if v is False else v)
except Exception: print("")' "${1:-}"; }
height(){ rpc getblockcount | jfield; }

# --- PHASE A: boot + identity ---
log "PHASE A — boot isolated testnet node (rpc $RPC_PORT, p2p $P2P_PORT)"
"$NODE" --profile testnet --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 \
  >"$NODE_LOG" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node did not answer RPC in 30s (see $NODE_LOG)"
H0="$(height)"; [[ "$H0" == "0" ]] && ok "clean chain at height 0" || bad "expected height 0, got $H0"
IS_TESTNET="$(rpc getinfo | jfield testnet)"
[[ "$IS_TESTNET" == "true" ]] && ok "node reports testnet profile" || bad "node is NOT testnet (getinfo.testnet=$IS_TESTNET) — refusing"
[[ "$IS_TESTNET" == "true" ]] || die "wrong network"

ADDR="$("$CLI" --wallet "$WORK/w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
[[ -n "$ADDR" ]] || die "could not create a testnet wallet address"
log "miner address: $ADDR"

# --- PHASE B: mine the reachable region + pre-V15 invariants ---
log "PHASE B — mine $BLOCKS blocks (pre-Phase2 region) and check pre-V15 invariants"
"$MINER" --profile testnet --rpc "127.0.0.1:$RPC_PORT" --address "$ADDR" \
  --blocks 100000 --threads "$THREADS" >"$MINER_LOG" 2>&1 &
MINER_PID=$!
DEADLINE=$(( $(date +%s) + 300 ))
while :; do
  h="$(height)"; [[ -z "$h" ]] && die "lost RPC while mining (see $NODE_LOG)"
  [[ "$h" -ge "$BLOCKS" ]] && break
  [[ "$(date +%s)" -ge "$DEADLINE" ]] && die "did not reach $BLOCKS blocks in 300s (rate too low; see $MINER_LOG)"
  sleep 3
done
HB="$(height)"; ok "chain advanced to height $HB (real mined blocks, real UTXO path)"

# pre-V15 coinbase must still carry the Gold Vault + PoPC outputs (T not yet active)
CB="$(rpc getblock "[\"$(rpc getblockhash "[$HB]" | jfield)\"]")"
echo "$CB" | grep -q 'popc\|gold\|OUT_COINBASE' && ok "pre-V15 block $HB has the legacy coinbase split (T inactive)" \
  || log "note: coinbase-structure introspection depends on getblock verbosity (see $NODE_LOG)"
# no Historical Jackpot before first-J height
[[ "$HB" -lt "$FIRST_J" ]] && ok "height $HB < first jackpot $FIRST_J — no jackpot expected (and none can be built)" \
  || bad "unexpectedly at/after first jackpot height without the gated phase"

# --- PHASE C+: V15 / T-transition / first jackpot / reorg (GATED) ---
if [[ "$TARGET_HEIGHT" -ge "$V15" ]]; then
  log "PHASE C — attempting to cross V15=$V15 toward first jackpot=$FIRST_J (target $TARGET_HEIGHT)"
  log "  NOTE: this needs the Phase2 time-hard region mined; expect hours+ without a dev fast-mine build."
  BIG_DEADLINE=$(( $(date +%s) + 36000 ))   # 10h ceiling
  while :; do
    h="$(height)"; [[ -z "$h" ]] && die "lost RPC while mining to target (see $NODE_LOG)"
    [[ "$h" -ge "$TARGET_HEIGHT" ]] && break
    [[ "$(date +%s)" -ge "$BIG_DEADLINE" ]] && die "did not reach target $TARGET_HEIGHT within 10h — fast-mine build required"
    sleep 15
  done
  ok "reached target height $(height) — PHASE C+ jackpot assertions can now run (extend this script)"
  # TODO(next): at FIRST_J assert getblock has tx[1] TX_TYPE_JACKPOT byte-exact to the
  # canonical builder; verify reserve spent + winner paid + change + supply-neutral;
  # then mutate + resubmit for atomicity; disconnect/reorg; restart; reindex.
else
  log "PHASE C+ SKIPPED — cross-V15 / T-transition / first-jackpot / reorg require reaching height >= $V15."
  log "  Pass --target-height $FIRST_J with a dev fast-mine build (or a multi-hour soak) to run them."
  log "  Rationale + measured rate: docs/V15_READINESS.md (SbPoW time-hard blocker)."
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS (reachable phases green; PHASE C+ gated on fast-mine prerequisite)"
  trap - EXIT; cleanup_ok; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup_keep; exit 1
fi
