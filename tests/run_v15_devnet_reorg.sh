#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_reorg.sh — TRUE multi-branch Historical Jackpot reorg on DEVNET_FAST.
#
# Builds two competing branches from the SAME height-23 ancestor:
#     ancestor(23) ┬─ Branch A: A24=J_A → A25 → A26          (active first)
#                  └─ Branch B: B24=J_B → B25 → B26 → B27     (longer)
# then feeds Branch-B's raw blocks (exported via getrawblock) into the Branch-A node
# through ordinary submitblock, letting the node's normal try_reorganize + BlockUndo
# activate Branch B. Proves J_A is fully undone and J_B is freshly connected, and that
# the reorganised node ends in the SAME state as a clean node that only ever saw Branch B.
# No PoW bypass, no manual chainstate/UTXO editing, no custom jackpot undo.
#
# Usage: tests/run_v15_devnet_reorg.sh [--base-rpc P] [--a-rpc P] [--b-rpc P]
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any mismatch. Datadirs/logs preserved on failure.
# =============================================================================
# FINDING (2026-08-05, first run): this harness EXPOSED A CRITICAL DEADLOCK — try_reorganize
# freezes when a reorg crosses Historical-Jackpot blocks. The fork/work selection is correct
# (B27 triggers "Attempting reorg"), but the node then blocks forever: all threads wait on
# g_chain_mu (the reorg thread holds it, 0%% CPU = lock deadlock, not a spin). Must be fixed
# before V15 mainnet — a reorg across a jackpot would freeze every node that sees it. Next:
# capture the holder-thread backtrace (thread inside try_reorganize) to pinpoint the exact
# lock it blocks on — likely a lock-ordering/self-deadlock in the jackpot-reorg connect path.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
BASE_RPC=18962; BASE_P2P=19962; A_RPC=18964; A_P2P=19964; B_RPC=18966; B_P2P=19966
while [[ $# -gt 0 ]]; do case "$1" in
  --base-rpc) BASE_RPC="$2"; shift 2;; --a-rpc) A_RPC="$2"; shift 2;; --b-rpc) B_RPC="$2"; shift 2;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15reorg.XXXXXX")"
FIRST_J=24; PRE_J=23; FAILED=0
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
declare -a PIDS=()
log(){ printf '[reorg] %s\n' "$*"; }
ok(){ printf '[reorg] PASS  %s\n' "$*"; }
bad(){ printf '[reorg] FAIL  %s\n' "$*"; FAILED=1; }
cleanup(){ for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done; pkill -P $$ sost-miner 2>/dev/null; pkill -P $$ sost-node 2>/dev/null; wait 2>/dev/null; }
die(){ printf '[reorg] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

rpc(){ local port="$1" m="$2" p="${3:-[]}"; curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$m\",\"params\":$p,\"id\":1}" "http://127.0.0.1:$port/"; }
height(){ rpc "$1" getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
tiphash(){ rpc "$1" getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1; }
blockhash(){ rpc "$1" getblockhash "[$2]" | grep -oE '[a-f0-9]{64}' | head -1; }
txcount(){ rpc "$1" getblock "[\"$2\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+'; }
jtxid(){ rpc "$1" getblock "[\"$2\"]" | python3 -c 'import sys,json;d=json.load(sys.stdin);ids=d.get("result",{}).get("txids",[]);print(ids[1] if len(ids)>1 else "")'; }
one_addr(){ rpc "$1" getaddressutxos "[\"$2\"]" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
reserve(){ local gs gc ps pc; read -r gs gc < <(one_addr "$1" "$GOLD"); read -r ps pc < <(one_addr "$1" "$POPC"); echo "$((gs+ps)):$((gc+pc))"; }
start_node(){ # start_node <chainfile> <p2p> <rpc> <logtag>
  "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$1" --port "$2" --rpc-port "$3" \
    --rpc-noauth --connect 127.0.0.1:1 >"$WORK/$4.log" 2>&1 &
  PIDS+=($!); local n=$!
  for _ in $(seq 1 30); do sleep 1; [[ -n "$(height "$3")" ]] && { echo "$n"; return; }; done; die "node $4 did not boot"; }
mine_to(){ # mine_to <rpc> <addr> <wallet> <target> <deadline>
  local port="$1" addr="$2" w="$3" tgt="$4" dl="$5" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$port" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner_$port.log" 2>&1 &
  local mp=$!; PIDS+=("$mp")
  while :; do local h; h="$(height "$port")"; [[ "$h" -ge "$tgt" ]] && { kill "$mp" 2>/dev/null; sleep 1; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { kill "$mp" 2>/dev/null; die "stuck reaching $tgt on :$port"; }; sleep 2; done; }

# --- wallets: A/B (share the 0-23 history), C (branch-B miner) ---
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
C="$("$CLI" --wallet "$WORK/c.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
log "A=$A"; log "B=$B"; log "C=$C  work=$WORK"

# === 1. COMMON ANCESTOR at height 23 (A mines early, B mines later) ===
log "building common ancestor to height $PRE_J…"
N0=$(start_node "$WORK/base.json" "$BASE_P2P" "$BASE_RPC" base)
mine_to "$BASE_RPC" "$A" "$WORK/a.json" "$((FIRST_J-11))" 150
mine_to "$BASE_RPC" "$B" "$WORK/b.json" "$PRE_J" 180
[[ "$(height "$BASE_RPC")" == "$PRE_J" ]] || die "ancestor height != $PRE_J"
ANCESTOR="$(blockhash "$BASE_RPC" "$PRE_J")"
kill "$N0" 2>/dev/null; sleep 2   # clean stop → flush base.json
ok "common ancestor at height $PRE_J (hash ${ANCESTOR:0:16}…)"
cp "$WORK/base.json" "$WORK/chainA.json"; cp "$WORK/base.json" "$WORK/chainB.json"; cp "$WORK/base.json" "$WORK/chainBref.json"

# === 2. BRANCH A: A24=J_A, A25, A26  (B mines) ===
log "Branch A: B mines to $((FIRST_J+2))…"
NA=$(start_node "$WORK/chainA.json" "$A_P2P" "$A_RPC" nodeA)
[[ "$(blockhash "$A_RPC" "$PRE_J")" == "$ANCESTOR" ]] || die "nodeA ancestor mismatch"
mine_to "$A_RPC" "$B" "$WORK/b.json" "$((FIRST_J+2))" 200
A24H="$(blockhash "$A_RPC" "$FIRST_J")"; JA_TXID="$(jtxid "$A_RPC" "$A24H")"; A_TIP="$(tiphash "$A_RPC")"; A_RES="$(reserve "$A_RPC")"
[[ "$(txcount "$A_RPC" "$A24H")" == "2" ]] && ok "Branch A: A24 carries J_A (txid ${JA_TXID:0:16}…)" || bad "Branch A: A24 has no jackpot"
log "  Branch A tip=${A_TIP:0:16}… height=$(height "$A_RPC") reserve=$A_RES"

# === 3. BRANCH B (clean reference): B24=J_B, B25, B26, B27  (C mines) — LONGER ===
log "Branch B: C mines to $((FIRST_J+3))…"
NB=$(start_node "$WORK/chainB.json" "$B_P2P" "$B_RPC" nodeB)
[[ "$(blockhash "$B_RPC" "$PRE_J")" == "$ANCESTOR" ]] || die "nodeB ancestor mismatch"
mine_to "$B_RPC" "$C" "$WORK/c.json" "$((FIRST_J+3))" 220
B24H="$(blockhash "$B_RPC" "$FIRST_J")"; JB_TXID="$(jtxid "$B_RPC" "$B24H")"; B_TIP="$(tiphash "$B_RPC")"; B_RES="$(reserve "$B_RPC")"
[[ "$(txcount "$B_RPC" "$B24H")" == "2" ]] && ok "Branch B: B24 carries J_B (txid ${JB_TXID:0:16}…)" || bad "Branch B: B24 has no jackpot"
[[ "$A24H" != "$B24H" ]] && ok "A24 != B24 — genuinely different branches from the same ancestor" || bad "A24 == B24 (not distinct)"
log "  Branch B tip=${B_TIP:0:16}… height=$(height "$B_RPC") reserve=$B_RES"

# === 4-5. EXPORT B24..B27 and IMPORT into the Branch-A node ===
log "exporting Branch-B blocks via getrawblock and submitting to the Branch-A node…"
for H in $(seq "$FIRST_J" "$((FIRST_J+3))"); do
  BHH="$(blockhash "$B_RPC" "$H")"
  RAW="$(rpc "$B_RPC" getrawblock "[\"$BHH\"]" | python3 -c 'import sys,json;d=json.load(sys.stdin);r=d.get("result","");print(r if isinstance(r,str) else "")')"
  [[ -n "$RAW" ]] || die "getrawblock returned empty for B height $H"
  rpc "$A_RPC" submitblock "[$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$RAW")]" >/dev/null
  sleep 1
done
sleep 3

# === 6. VERIFY THE REORG ===
NEW_TIP="$(tiphash "$A_RPC")"; NEW_H="$(height "$A_RPC")"; NEW_RES="$(reserve "$A_RPC")"
NEW_24="$(blockhash "$A_RPC" "$FIRST_J")"; NEW_24_TXID="$(jtxid "$A_RPC" "$NEW_24")"
log "after import: nodeA tip=${NEW_TIP:0:16}… height=$NEW_H reserve=$NEW_RES  block24=${NEW_24:0:16}…"
[[ "$NEW_TIP" == "$B_TIP" ]] && ok "REORG happened: nodeA tip == Branch-B tip (B27)" || bad "no reorg: nodeA tip=${NEW_TIP:0:16} != B_tip=${B_TIP:0:16}"
[[ "$NEW_24" == "$B24H" ]] && ok "J_A disconnected: block 24 is now B24 (J_B), not A24 (J_A)" || bad "block 24 still A24 (J_A not replaced)"
[[ "$NEW_24_TXID" == "$JB_TXID" ]] && ok "J_B connected: block-24 jackpot txid == J_B" || bad "block-24 jackpot txid != J_B ($NEW_24_TXID vs $JB_TXID)"

# === 7. CLEAN-BRANCH-B EQUIVALENCE ===
if [[ "$NEW_RES" == "$B_RES" && "$NEW_TIP" == "$B_TIP" ]]; then
  ok "EQUIVALENCE: reorganised nodeA state == clean Branch-B state (tip $NEW_H, reserve $NEW_RES)"
else
  bad "state differs: nodeA(reorg) tip=${NEW_TIP:0:16} res=$NEW_RES  vs  cleanB tip=${B_TIP:0:16} res=$B_RES"
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — A→B reorg fully undid J_A and connected J_B; reorganised state == clean Branch B"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi
