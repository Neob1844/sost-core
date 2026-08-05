#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_failed_reorg.sh — FAILED-REORG ATOMICITY on DEVNET_FAST.
#
# Proves that a Historical-Jackpot reorg which FAILS midway through connecting the
# alternative branch rolls back to the ORIGINAL active branch BYTE-IDENTICALLY, with
# zero state drift, and leaves the node healthy and able to keep mining Branch A.
#
# Topology (same proven ancestor as run_v15_devnet_reorg.sh):
#     ancestor(23) ┬─ Branch A: A24=J_A → A25 → A26            (active)
#                  └─ Branch B: B24=J_B → B25 → B26 → B27       (longer → would win)
#
# Failure is injected by a STRICTLY DEV-only, one-shot, ordinal-precise reorg-connect
# failpoint (RPC devsetreorgfailpoint; compiled ONLY under SOST_DEVNET_FORKS and
# runtime-gated on Profile::DEV). It does NOT bypass PoW/validation/UTXO logic — it
# merely declines to connect the alternative block at a chosen ordinal, so the node's
# NORMAL try_reorganize rollback path executes.
#
# For each case: a FRESH nodeA is loaded from chainA.json (so Branch-B blocks are not yet
# known and the reorg can re-trigger), a canonical STATE MANIFEST is captured, the
# failpoint is armed, Branch-B blocks are submitted (triggering try_reorganize which
# disconnects all of Branch A, connects `ordinal` Branch-B blocks, then fails), and after
# rollback the manifest MUST equal the pre-attempt manifest. g_blocks/g_block_undos must
# stay aligned, the node must stay responsive, and one further Branch-A block must mine.
#
# Ordinals over fork_chain [B24,B25,B26,B27]:
#   F01 ord0 — fail before connecting B24 (the J block); 0 B-blocks connected
#   F02 ord1 — connect B24 (J), fail before B25; 1 connected  (partial J-branch undo)
#   F03 ord2 — connect B24,B25, fail before B26; 2 connected
#   F04 ord3 — connect B24,B25,B26, fail before B27/tip activation; 3 connected
#   F00      — DISARMED control: no failpoint → reorg SUCCEEDS to B27 (proves the
#              rollback in F01-F04 is caused by the injected failure, not a broken reorg)
# Coverage note for the order's F05-F07 under the DEV single-jackpot schedule (only J
# height is 24 = first fork block): "fail on a J-bearing block" is F01 (fails AT J24) and
# F02 (connects then undoes J24); "fail on an ordinary post-J block" is F03/F04; "fail
# after multiple Branch-A blocks disconnected" is EVERY case (fork_point=23 → all 3
# Branch-A blocks are always disconnected before connect). A natural connect-phase reorg
# failure is not constructible here because an invalid block cannot have validly-mined
# successors to give its branch more work; the valid-PoW noncanonical-J rejection is
# proven separately by run_v15_devnet_attacks.sh.
#
# Usage: tests/run_v15_devnet_failed_reorg.sh [--cycles N]
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any mismatch. Datadirs/logs preserved on failure.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
BASE_RPC=18972; BASE_P2P=19972; A_RPC=18974; A_P2P=19974; B_RPC=18976; B_P2P=19976
CYCLES=10
while [[ $# -gt 0 ]]; do case "$1" in
  --cycles) CYCLES="$2"; shift 2;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15failreorg.XXXXXX")"
FIRST_J=24; PRE_J=23; FAILED=0
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
declare -a PIDS=()
log(){ printf '[failreorg] %s\n' "$*"; }
ok(){ printf '[failreorg] PASS  %s\n' "$*"; }
bad(){ printf '[failreorg] FAIL  %s\n' "$*"; FAILED=1; }
cleanup(){
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  # Sweep by THIS run's unique mktemp work dir (present in every node/miner argv). Can
  # NEVER match the live mainnet miner/node — no bare pkill.
  if [[ -n "${WORK:-}" ]]; then
    for pid in $(pgrep -f -- "$WORK" 2>/dev/null); do [[ "$pid" == "$$" ]] && continue; kill "$pid" 2>/dev/null; done
  fi
  wait 2>/dev/null
}
die(){ printf '[failreorg] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

rpc(){ local port="$1" m="$2" p="${3:-[]}"; curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$m\",\"params\":$p,\"id\":1}" "http://127.0.0.1:$port/"; }
height(){ rpc "$1" getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
tiphash(){ rpc "$1" getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1; }
blockhash(){ rpc "$1" getblockhash "[$2]" | grep -oE '[a-f0-9]{64}' | head -1; }
txcount(){ rpc "$1" getblock "[\"$2\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+'; }
jtxid(){ rpc "$1" getblock "[\"$2\"]" | python3 -c 'import sys,json;d=json.load(sys.stdin);ids=d.get("result",{}).get("txids",[]);print(ids[1] if len(ids)>1 else "")'; }
utxos(){ rpc "$1" getaddressutxos "[\"$2\"]" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); r=d.get("result",[])
 print("\n".join(sorted("%s:%s:%s"%(u.get("txid"),u.get("vout"),u.get("amount_stocks")) for u in r)))
except Exception: pass'; }
reserve_tc(){ rpc "$1" getaddressutxos "[\"$2\"]" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
reserve(){ local gs gc ps pc; read -r gs gc < <(reserve_tc "$1" "$GOLD"); read -r ps pc < <(reserve_tc "$1" "$POPC"); echo "$((gs+ps)):$((gc+pc))"; }
devcs(){ rpc "$1" devchainstate | python3 -c 'import sys,json
d=json.load(sys.stdin).get("result",{})
if isinstance(d,str): d=json.loads(d)
print("cs h=%s blocks=%s undos=%s active=%s ids=%s"%(d.get("chain_height"),d.get("blocks_size"),d.get("undos_size"),d.get("active_index_count"),",".join(d.get("active_index_ids",[]))))'; }
# canonical consensus-state manifest → sha256 (order-stable)
manifest(){ local port="$1" h out
  h="$(height "$port")"
  out="TIP=$(tiphash "$port") H=$h"$'\n'
  local x; for x in $(seq 0 "$h"); do out+="B$x=$(blockhash "$port" "$x")"$'\n'; done
  out+="$(devcs "$port")"$'\n'
  local a; for a in "$WA" "$WB" "$WC" "$GOLD" "$POPC"; do out+="U[$a]:"$'\n'"$(utxos "$port" "$a")"$'\n'; done
  out+="MP=$(rpc "$port" getrawmempool | python3 -c 'import sys,json
try: print(",".join(sorted(json.load(sys.stdin).get("result",[]))))
except Exception: print("")')"
  printf '%s' "$out" | sha256sum | cut -d' ' -f1; }
manifest_dump(){ # same as manifest but prints the raw text (for debugging a mismatch)
  local port="$1" h; h="$(height "$port")"
  echo "TIP=$(tiphash "$port") H=$h"; local x
  for x in $(seq 0 "$h"); do echo "B$x=$(blockhash "$port" "$x")"; done
  devcs "$port"; local a
  for a in "$WA" "$WB" "$WC" "$GOLD" "$POPC"; do echo "U[$a]:"; utxos "$port" "$a"; done; }

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
submit_raw(){ rpc "$1" submitblock "[$(python3 -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$2")]" >/dev/null; }

# --- wallets ---
WA="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
WB="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
WC="$("$CLI" --wallet "$WORK/c.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
log "A=$WA B=$WB C=$WC  work=$WORK  cycles=$CYCLES"

# === 1. COMMON ANCESTOR (23) ===
log "building common ancestor to height $PRE_J…"
N0=$(start_node "$WORK/base.json" "$BASE_P2P" "$BASE_RPC" base)
mine_to "$BASE_RPC" "$WA" "$WORK/a.json" "$((FIRST_J-11))" 150
mine_to "$BASE_RPC" "$WB" "$WORK/b.json" "$PRE_J" 180
[[ "$(height "$BASE_RPC")" == "$PRE_J" ]] || die "ancestor height != $PRE_J"
ANCESTOR="$(blockhash "$BASE_RPC" "$PRE_J")"
kill "$N0" 2>/dev/null; sleep 2
ok "common ancestor at height $PRE_J (${ANCESTOR:0:16}…)"
cp "$WORK/base.json" "$WORK/chainA.json"; cp "$WORK/base.json" "$WORK/chainB.json"

# === 2. BRANCH A (active reference): A24=J_A, A25, A26 ===
NA=$(start_node "$WORK/chainA.json" "$A_P2P" "$A_RPC" branchA)
[[ "$(blockhash "$A_RPC" "$PRE_J")" == "$ANCESTOR" ]] || die "branchA ancestor mismatch"
mine_to "$A_RPC" "$WB" "$WORK/b.json" "$((FIRST_J+2))" 200
A_TIP="$(tiphash "$A_RPC")"; A24H="$(blockhash "$A_RPC" "$FIRST_J")"; JA_TXID="$(jtxid "$A_RPC" "$A24H")"
[[ "$(txcount "$A_RPC" "$A24H")" == "2" ]] && ok "Branch A: A24 carries J_A (${JA_TXID:0:16}…)" || bad "Branch A: A24 has no jackpot"
kill "$NA" 2>/dev/null; sleep 2   # flush chainA.json at tip 26 (canonical Branch-A snapshot)
log "Branch A snapshot: tip=${A_TIP:0:16}… height=$((FIRST_J+2))"

# === 3. BRANCH B (longer): B24=J_B .. B27 ; export raw blocks ===
NB=$(start_node "$WORK/chainB.json" "$B_P2P" "$B_RPC" branchB)
[[ "$(blockhash "$B_RPC" "$PRE_J")" == "$ANCESTOR" ]] || die "branchB ancestor mismatch"
mine_to "$B_RPC" "$WC" "$WORK/c.json" "$((FIRST_J+3))" 220
B_TIP="$(tiphash "$B_RPC")"; B24H="$(blockhash "$B_RPC" "$FIRST_J")"; JB_TXID="$(jtxid "$B_RPC" "$B24H")"
[[ "$(txcount "$B_RPC" "$B24H")" == "2" ]] && ok "Branch B: B24 carries J_B (${JB_TXID:0:16}…)" || bad "Branch B: B24 has no jackpot"
[[ "$A24H" != "$B24H" ]] && ok "A24 != B24 (distinct branches)" || bad "A24 == B24"
declare -a RAWB=()
for H in $(seq "$FIRST_J" "$((FIRST_J+3))"); do
  BHH="$(blockhash "$B_RPC" "$H")"
  RAW="$(rpc "$B_RPC" getrawblock "[\"$BHH\"]" | python3 -c 'import sys,json;d=json.load(sys.stdin);r=d.get("result","");print(r if isinstance(r,str) else "")')"
  [[ -n "$RAW" ]] || die "getrawblock empty for B h=$H"
  echo "$RAW" > "$WORK/rawB$H.json"; RAWB+=("$WORK/rawB$H.json")
done
kill "$NB" 2>/dev/null; sleep 2
ok "exported Branch-B raw blocks B$FIRST_J..B$((FIRST_J+3))"

# === helper: run one failed-reorg case on a FRESH Branch-A node ===
# run_case <label> <ordinal>   (ordinal <0 = disarmed control → reorg should SUCCEED)
run_case(){
  local label="$1" ord="$2" tag caseA cap NA2 mb ma h_before h_after
  tag="${label}_$RANDOM"
  caseA="$WORK/case_$tag.json"; cp "$WORK/chainA.json" "$caseA"
  cap="$WORK/case_$tag.log"
  NA2=$(start_node "$caseA" "$A_P2P" "$A_RPC" "case_$tag")
  h_before="$(height "$A_RPC")"
  [[ "$(tiphash "$A_RPC")" == "$A_TIP" ]] || { bad "$label: fresh node not at Branch-A tip"; kill "$NA2" 2>/dev/null; return; }
  mb="$(manifest "$A_RPC")"
  if [[ "$ord" -ge 0 ]]; then rpc "$A_RPC" devsetreorgfailpoint "[$ord]" >/dev/null; fi
  # submit Branch-B blocks → the last one (B27) triggers try_reorganize
  local f; for f in "${RAWB[@]}"; do submit_raw "$A_RPC" "$(cat "$f")"; sleep 1; done
  sleep 3
  h_after="$(height "$A_RPC")"
  local tip_after; tip_after="$(tiphash "$A_RPC")"
  if [[ "$ord" -ge 0 ]]; then
    # EXPECT: rollback → Branch A restored exactly
    grep -q 'DEV-FAILPOINT] Forcing connect failure' "$WORK/case_$tag.log" || bad "$label: failpoint did not fire (see case_$tag.log)"
    grep -q 'REORG] Rolled back to original tip' "$WORK/case_$tag.log" || bad "$label: no rollback logged"
    local connected; connected="$(grep -oE 'after [0-9]+ block\(s\) connected' "$WORK/case_$tag.log" | grep -oE '[0-9]+' | head -1)"
    ma="$(manifest "$A_RPC")"
    if [[ "$tip_after" == "$A_TIP" && "$h_after" == "$h_before" && "$ma" == "$mb" ]]; then
      ok "$label (ord=$ord, B-connected=$connected): rollback restored Branch A EXACTLY (state hash ${mb:0:16}…)"
    else
      bad "$label: STATE DRIFT after rollback (tip $tip_after vs $A_TIP, h $h_after vs $h_before, hash ${ma:0:12} vs ${mb:0:12})"
      { echo "== BEFORE =="; echo "$mb"; echo "== AFTER =="; manifest_dump "$A_RPC"; } > "$WORK/drift_$tag.txt"
    fi
    # invariant: g_blocks == g_block_undos, no stale ACTIVE fork ids
    local bs us; bs="$(devcs "$A_RPC" | grep -oE 'blocks=[0-9]+' | grep -oE '[0-9]+')"; us="$(devcs "$A_RPC" | grep -oE 'undos=[0-9]+' | grep -oE '[0-9]+')"
    [[ "$bs" == "$us" ]] && ok "$label: g_blocks==g_block_undos ($bs)" || bad "$label: g_blocks($bs) != g_block_undos($us)"
    # node responsive + can keep mining Branch A
    [[ -n "$(height "$A_RPC")" ]] || bad "$label: node unresponsive after rollback"
    mine_to "$A_RPC" "$WA" "$WORK/a.json" "$((h_before+1))" 60
    [[ "$(height "$A_RPC")" == "$((h_before+1))" ]] && ok "$label: mined one more Branch-A block post-rollback (h=$((h_before+1)))" || bad "$label: cannot continue mining Branch A"
  else
    # DISARMED control: reorg should SUCCEED to Branch B
    [[ "$tip_after" == "$B_TIP" ]] && ok "$label CONTROL (no failpoint): reorg SUCCEEDED to Branch-B tip" || bad "$label CONTROL: expected reorg to B ($B_TIP), got $tip_after"
  fi
  kill "$NA2" 2>/dev/null; sleep 2   # free the reused RPC/P2P port before the next case
}

# === 4. CONTROL: no failpoint → reorg succeeds (proves rollback is failure-driven) ===
log "F00 control: disarmed → reorg must succeed…"
run_case F00 -1

# === 5. FAILED-REORG MATRIX F01..F04 (ordinals 0..3) ===
log "failed-reorg matrix F01..F04…"
run_case F01 0
run_case F02 1
run_case F03 2
run_case F04 3

# === 6. REPEATABILITY: N cycles alternating failure points, fresh node each time ===
log "repeatability: $CYCLES rollback cycles alternating ordinals…"
ords=(0 1 2 3 2 1 3 0 1 2 3 0 1 2 3)
for ((i=0;i<CYCLES;i++)); do
  run_case "CYC$((i+1))" "${ords[$((i%${#ords[@]}))]}"
done

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — every failed reorg rolled back to Branch A byte-identically; g_blocks==g_block_undos; node healthy; control reorg succeeded"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi
