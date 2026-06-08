#!/usr/bin/env bash
# run_testnet_soak.sh — automate the live PoPC V15 testnet soak (docs/V15_POPC_SOAK_REPORT.md).
#
# SAFETY FIRST. This script:
#   * runs ONLY testnet: --profile testnet, a separate chain + wallet + ports;
#   * REFUSES to run against mainnet paths (chain.json / wallet.json) or a non-testnet build;
#   * NEVER deletes data without --reset-testnet;
#   * NEVER touches mainnet, the DTD gate, OTC/P2P, or any systemd service;
#   * has a --dry-run mode that prints the plan and exits.
#
# It is conservative by design: if the node rejects a carrier at the mempool, that is
# recorded as a NO-GO finding (NOT patched here — propose a separate fix).
#
# Usage:
#   scripts/run_testnet_soak.sh [--dry-run] [--reset-testnet] [--target-height N]
#                               [--rpc-user U] [--rpc-pass P]
set -euo pipefail

# ---------------------------------------------------------------------------
# Config (testnet-only; override via env or flags)
# ---------------------------------------------------------------------------
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-testnet}"
WORK="${WORK:-$ROOT/testnet_soak_data}"
CHAIN="${CHAIN:-$WORK/testnet_chain.json}"
WALLET="${WALLET:-$WORK/testnet_wallet.json}"
GENESIS="${GENESIS:-$ROOT/genesis_block.json}"
P2P_PORT="${P2P_PORT:-19334}"
RPC_PORT="${RPC_PORT:-18233}"
RPCUSER="${RPCUSER:-soak}"
RPCPASS="${RPCPASS:-soakpass}"
CROSS_V15=310            # cross V15_HEIGHT (testnet 300)
MATURE_AT=1010           # COINBASE_MATURITY=1000 → first spendable coins ≈ here
CROSS_ELI=1310           # cross DTD_POPC_ELIGIBILITY_HEIGHT (testnet 1300)
END_HEIGHT=130000        # commitment end (well past 1300)

DRY_RUN=0
RESET=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)        DRY_RUN=1; shift;;
    --reset-testnet)  RESET=1; shift;;
    --target-height)  CROSS_ELI="$2"; shift 2;;
    --rpc-user)       RPCUSER="$2"; shift 2;;
    --rpc-pass)       RPCPASS="$2"; shift 2;;
    -h|--help)        grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

NODE_LOG="$WORK/node.log"
MINER_LOG="$WORK/miner.log"
RESULTS="$WORK/results.txt"
NODE_PID=""; MINER_PID=""
declare -a VERDICTS=()

log(){ printf '[soak] %s\n' "$*"; }
die(){ printf '[soak] FATAL: %s\n' "$*" >&2; exit 1; }
record(){ # record <PASS|FAIL|SKIP> <step> <detail>
  VERDICTS+=("$1|$2|$3"); printf '[soak] %-4s %s — %s\n' "$1" "$2" "$3";
  [[ $DRY_RUN -eq 0 ]] && printf '%s\t%s\t%s\n' "$1" "$2" "$3" >> "$RESULTS" || true; }

# ---------------------------------------------------------------------------
# Safety guards — refuse anything that could touch mainnet
# ---------------------------------------------------------------------------
assert_safe(){
  case "$(basename "$CHAIN")" in
    chain.json|mainnet*.json) die "refusing: CHAIN '$CHAIN' looks like mainnet. Use a testnet chain file.";;
  esac
  case "$(basename "$WALLET")" in
    wallet.json) die "refusing: WALLET '$WALLET' is the mainnet default. Use a testnet wallet file.";;
  esac
  [[ "$RPC_PORT" == "18232" ]] && die "refusing: RPC_PORT 18232 is the mainnet default. Use a separate testnet port."
  [[ "$P2P_PORT" == "19333" ]] && die "refusing: P2P_PORT 19333 is the mainnet default. Use a separate testnet port."
  # Build must be a testnet build (low fork heights), or PoPC never activates at 300.
  if [[ -f "$BUILD_DIR/CMakeCache.txt" ]]; then
    grep -q '^SOST_TESTNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" \
      || die "refusing: $BUILD_DIR is NOT a -DSOST_TESTNET_FORKS=ON build (V15 would be at 20000, not 300)."
  fi
  log "safety OK — testnet profile, chain=$(basename "$CHAIN"), wallet=$(basename "$WALLET"), rpc=$RPC_PORT, p2p=$P2P_PORT"
}

ensure_build(){
  if [[ -f "$BUILD_DIR/sost-node" && -f "$BUILD_DIR/sost-miner" && -f "$BUILD_DIR/sost-cli" && -f "$BUILD_DIR/popc15-carrier" ]]; then
    log "testnet binaries present in $BUILD_DIR"; return; fi
  log "building testnet binaries (-DSOST_TESTNET_FORKS=ON) into $BUILD_DIR"
  [[ $DRY_RUN -eq 1 ]] && { log "(dry-run) would: cmake -S '$ROOT' -B '$BUILD_DIR' -DCMAKE_BUILD_TYPE=Release -DSOST_TESTNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON && cmake --build '$BUILD_DIR' -j sost-node sost-miner sost-cli popc15-carrier"; return; }
  cmake -S "$ROOT" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release -DSOST_TESTNET_FORKS=ON -DSOST_ENABLE_PHASE2_SBPOW=ON
  cmake --build "$BUILD_DIR" -j"$(nproc)" sost-node sost-miner sost-cli popc15-carrier
}

# ---------------------------------------------------------------------------
# RPC helpers (curl + python3 for robust JSON)
# ---------------------------------------------------------------------------
rpc(){ # rpc <method> [json-params]
  local m="$1" p="${2:-[]}"
  curl -s --max-time 15 --user "$RPCUSER:$RPCPASS" -H 'content-type: application/json' \
    --data "{\"method\":\"$m\",\"params\":$p,\"id\":1}" "http://127.0.0.1:$RPC_PORT/"
}
rpc_field(){ python3 -c 'import sys,json;
try:
    d=json.load(sys.stdin); r=d.get("result")
    if isinstance(r,dict): print(r.get(sys.argv[1],""))
    else: print(r if r is not None else "")
except Exception: print("")' "$1"; }
height(){ rpc getblockcount | rpc_field; }

CLI(){ "$BUILD_DIR/sost-cli" --wallet "$WALLET" --node "127.0.0.1:$RPC_PORT" --rpc-user "$RPCUSER" --rpc-pass "$RPCPASS" "$@"; }
CARRIER(){ "$BUILD_DIR/popc15-carrier" "$@"; }

stop_all(){
  [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null || true
  [[ -n "$NODE_PID"  ]] && kill "$NODE_PID"  2>/dev/null || true
}
trap stop_all EXIT

start_node(){
  log "starting testnet node (rpc $RPC_PORT, p2p $P2P_PORT) → $NODE_LOG"
  # ISOLATION: pass --connect to a dead local port so the node does NOT fall back
  # to the default mainnet seed (seed.sostcore.com:19333) and start ingesting the
  # mainnet chain. A single-node soak must stay isolated; for the 2-node reorg
  # test the operator points the second node's --connect at this one instead.
  "$BUILD_DIR/sost-node" --profile testnet --genesis "$GENESIS" --chain "$CHAIN" \
    --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-user "$RPCUSER" --rpc-pass "$RPCPASS" \
    --connect 127.0.0.1:1 \
    >"$NODE_LOG" 2>&1 &
  NODE_PID=$!
  for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && { log "node up at height $(height)"; return; }; done
  die "node did not answer RPC within 30s (see $NODE_LOG)"
}
start_miner(){ # start_miner <address>
  log "starting testnet miner → $MINER_LOG"
  "$BUILD_DIR/sost-miner" --profile testnet --rpc "127.0.0.1:$RPC_PORT" \
    --rpc-user "$RPCUSER" --rpc-pass "$RPCPASS" --address "$1" --blocks 1000000 --threads 2 \
    >"$MINER_LOG" 2>&1 &
  MINER_PID=$!
}
mine_to(){ # mine_to <height> <label>
  local target="$1" label="$2" h
  log "mining to height >= $target ($label) — this can take a while on testnet"
  while :; do
    h="$(height)"; [[ -z "$h" ]] && die "lost RPC while mining (see $NODE_LOG)"
    [[ "$h" -ge "$target" ]] && { log "reached height $h ($label)"; return; }
    sleep 10
  done
}
# emit a carrier; echoes the broadcast result line; returns CLI exit code
emit(){ # emit <carrier-args...>  (must include --privkey, --event, --end)
  local payload
  payload="$(CARRIER "$@" | sed -n 's/^.*--popc-carrier //p' | tail -1)"
  [[ -z "$payload" ]] && { echo "CARRIER_GEN_FAILED"; return 1; }
  CLI send "$MINER_ADDR" 0.00000001 --popc-carrier "$payload" --yes 2>&1
}

# ---------------------------------------------------------------------------
# Plan / dry-run
# ---------------------------------------------------------------------------
print_plan(){
  cat <<EOF
=== PoPC V15 testnet soak — PLAN ===
 build dir : $BUILD_DIR  (must be -DSOST_TESTNET_FORKS=ON)
 work dir  : $WORK   (logs + results)
 chain     : $CHAIN     wallet: $WALLET     genesis: $GENESIS
 ports     : rpc $RPC_PORT  p2p $P2P_PORT   profile: testnet
 steps:
  A  start node + miner; mine to >= $CROSS_V15  (cross V15_HEIGHT 300 → PoPC live)
     mine to >= $MATURE_AT (coinbase maturity 1000 → first spendable coins)
  B  owner1=miner: Register + Activate (valid)         → getpopcv15status owner1 = ACTIVE
  C  owner2=fresh: Register ONLY (no Activate)         → getpopcv15status owner2 = NOT active
  D  forged: Register with --forge-owner (bad owner)   → that owner = NOT active; active_count unchanged
  E  mine to >= $CROSS_ELI (cross eligibility 1300)    → eligibility_enforced = false (flag off); A still ACTIVE
  F  reorg / G replay  → MANUAL (see docs/V15_POPC_TESTNET_SOAK_GUIDE.md §3 F/G)
 destructive: deletes $WORK only with --reset-testnet (currently: $([[ $RESET -eq 1 ]] && echo YES || echo no))
 NEVER touches: mainnet, chain.json/wallet.json, DTD_POPC_GATE_CONSENSUS_ACTIVE, OTC/P2P, systemd.
EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
assert_safe
if [[ $DRY_RUN -eq 1 ]]; then print_plan; ensure_build; log "(dry-run) no node/miner started, no tx sent."; exit 0; fi

# reset only on explicit request
if [[ -e "$CHAIN" || -e "$WALLET" ]]; then
  if [[ $RESET -eq 1 ]]; then log "--reset-testnet: removing $WORK"; rm -rf "$WORK";
  else log "reusing existing testnet data in $WORK (pass --reset-testnet to wipe)"; fi
fi
mkdir -p "$WORK"; : > "$RESULTS"
print_plan
ensure_build

start_node

# wallet + miner address (owner1)
CLI newwallet >/dev/null 2>&1 || true
MINER_ADDR="$(CLI getnewaddress soak-miner 2>/dev/null | tail -1 | tr -d '[:space:]')"
[[ -z "$MINER_ADDR" ]] && die "could not create/read a testnet wallet address"
log "owner1 (miner) address: $MINER_ADDR"
OWNER1_SK="$(CLI dumpprivkey "$MINER_ADDR" 2>/dev/null | grep -oE '[0-9a-fA-F]{64}' | head -1)"
[[ -z "$OWNER1_SK" ]] && die "could not read owner1 private key"
OWNER1_PKH="$(CARRIER --event register --privkey "$OWNER1_SK" --end "$END_HEIGHT" | sed -n 's/^owner_pkh *: *//p' | grep -oE '^[0-9a-f]{40}')"

# owner2: a fresh key used only to SIGN a register-only carrier (no funds needed)
OWNER2_ADDR="$(CLI getnewaddress soak-owner2 2>/dev/null | tail -1 | tr -d '[:space:]')"
OWNER2_SK="$(CLI dumpprivkey "$OWNER2_ADDR" 2>/dev/null | grep -oE '[0-9a-fA-F]{64}' | head -1)"
OWNER2_PKH="$(CARRIER --event register --privkey "$OWNER2_SK" --end "$END_HEIGHT" | sed -n 's/^owner_pkh *: *//p' | grep -oE '^[0-9a-f]{40}')"
FORGED_PKH="aabbccddeeff00112233445566778899aabbccdd"

start_miner "$MINER_ADDR"

# A — cross 300, then mine to maturity so carrier txs can be funded
mine_to "$CROSS_V15" "V15_HEIGHT"
[[ "$(rpc getpopcv15status | rpc_field v15_active)" == "true" ]] \
  && record PASS A "PoPC V15 active at height $(height)" \
  || record FAIL A "PoPC V15 NOT active after crossing 300 (see $NODE_LOG)"
mine_to "$MATURE_AT" "coinbase-maturity"

# B — valid Register + Activate (owner1). Same owner+end ⇒ generator derives the same commitment id.
RB1="$(emit --event register --privkey "$OWNER1_SK" --model A --end "$END_HEIGHT" || true)"
sleep 2
RB2="$(emit --event activate --privkey "$OWNER1_SK" --model A --end "$END_HEIGHT" --balance 311035 --attest-height "$(height)" || true)"
log "B register: $RB1"; log "B activate: $RB2"
mine_to "$(( $(height) + 3 ))" "confirm-B"
if [[ "$(rpc getpopcv15status "[\"$OWNER1_PKH\"]" | rpc_field queried_owner_active)" == "true" ]]; then
  record PASS B "owner1 Active after valid Register+Activate"
else
  record FAIL B "owner1 NOT active after Register+Activate (mempool/lifecycle — txids above; see $NODE_LOG)"
fi

# C — register-only (owner2): must stay Pending / not active
RC="$(emit --event register --privkey "$OWNER2_SK" --model A --end "$END_HEIGHT" || true)"
log "C register-only: $RC"
mine_to "$(( $(height) + 3 ))" "confirm-C"
[[ "$(rpc getpopcv15status "[\"$OWNER2_PKH\"]" | rpc_field queried_owner_active)" == "true" ]] \
  && record FAIL C "register-only owner2 became ACTIVE (BUG — register must not count)" \
  || record PASS C "register-only owner2 not active (Pending), as required"

# D — forged/unauthorized carrier: must be ignored
RD="$(emit --event register --privkey "$OWNER1_SK" --model A --end "$END_HEIGHT" --forge-owner "$FORGED_PKH" || true)"
log "D forged: $RD"
mine_to "$(( $(height) + 3 ))" "confirm-D"
[[ "$(rpc getpopcv15status "[\"$FORGED_PKH\"]" | rpc_field queried_owner_active)" == "true" ]] \
  && record FAIL D "forged owner became ACTIVE (BUG — unauthorized carrier accepted)" \
  || record PASS D "forged/unauthorized carrier ignored, as required"

# E — cross 1300 with the flag false
mine_to "$CROSS_ELI" "eligibility-height"
ENF="$(rpc getpopcv15status | rpc_field eligibility_enforced)"
GATE="$(rpc getpopcv15status | rpc_field gate_active)"
A_STILL="$(rpc getpopcv15status "[\"$OWNER1_PKH\"]" | rpc_field queried_owner_active)"
if [[ "$GATE" == "false" && "$ENF" == "false" ]]; then
  record PASS E "past 1300, DTD-PoPC gate still OFF (gate_active=false, eligibility_enforced=false)"
else
  record FAIL E "DTD-PoPC gate unexpectedly enforced past 1300 (gate=$GATE enforced=$ENF) — MUST stay off"
fi
[[ "$A_STILL" == "true" ]] \
  && record PASS E2 "owner1 still Active across 1300 (within first audit interval)" \
  || record FAIL E2 "owner1 lost Active status across 1300 (investigate auto-slash timing)"

record SKIP F "reorg around 300/1300 — run MANUALLY with a 2nd node (guide §3F)"
record SKIP G "mainnet replay byte-identity — run MANUALLY (guide §3G, --dry-run-replay)"

# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------
echo; echo "================= SOAK SUMMARY ================="
fail=0
for v in "${VERDICTS[@]}"; do
  IFS='|' read -r st step det <<<"$v"; printf '  %-4s %-3s %s\n' "$st" "$step" "$det"
  [[ "$st" == "FAIL" ]] && fail=1
done
echo "------------------------------------------------"
if [[ $fail -eq 0 ]]; then
  echo "  AUTOMATED VERDICT: GO (automated steps passed; complete F+G manually, then sign off the report)"
else
  echo "  AUTOMATED VERDICT: NO-GO (a step FAILED — record it in docs/V15_POPC_SOAK_REPORT.md; do NOT flip)"
fi
echo "  results: $RESULTS    node log: $NODE_LOG    miner log: $MINER_LOG"
echo "================================================"
exit $fail
