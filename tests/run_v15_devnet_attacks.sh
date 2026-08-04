#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_attacks.sh — VALID-POW node-level jackpot attack + atomicity.
#
# Proves that a fully-formed block with VALID DEV PoW but a NON-CANONICAL Historical
# Jackpot is rejected by the real node, with ZERO consensus-state mutation. No PoW
# bypass: the devnet miner (--attack-jackpot, compiled ONLY under SOST_DEVNET_FORKS)
# mutates the canonical jackpot, then its NORMAL path recomputes the merkle root and
# mines a valid DEV PoW, and submits via ordinary submitblock. The node must reject and
# the active tip + reserve must be byte-identical before and after every attempt.
#
# Usage: tests/run_v15_devnet_attacks.sh [--rpc-port P] [--p2p-port P]
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any accepted malicious block or any state mutation.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
RPC_PORT=18980; P2P_PORT=19980
while [[ $# -gt 0 ]]; do case "$1" in
  --rpc-port) RPC_PORT="$2"; shift 2;; --p2p-port) P2P_PORT="$2"; shift 2;;
  -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;; *) echo "unknown arg: $1" >&2; exit 2;; esac; done

NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15attack.XXXXXX")"
FIRST_J=24; PRE_J=$((FIRST_J-1)); FAILED=0; NODE_PID=""; MINER_PID=""
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
log(){ printf '[attack] %s\n' "$*"; }
ok(){ printf '[attack] PASS  %s\n' "$*"; }
bad(){ printf '[attack] FAIL  %s\n' "$*"; FAILED=1; }
stop_miner(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; }
cleanup(){ stop_miner; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; }
die(){ printf '[attack] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
one_addr(){ rpc getaddressutxos "[\"$1\"]" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
reserve_state(){ local gs gc ps pc; read -r gs gc < <(one_addr "$GOLD"); read -r ps pc < <(one_addr "$POPC"); echo "$((gs+ps)):$((gc+pc))"; }

"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 >"$WORK/node.log" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node down"
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
mine_honest(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  MINER_PID=$!
  while :; do local h; h="$(height)"; [[ "$h" -ge "$tgt" ]] && { stop_miner; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stop_miner; die "stuck reaching $tgt"; }; sleep 2; done; }

log "building pre-J state (A mines early, B mines to $PRE_J)…"
mine_honest "$A" "$WORK/a.json" "$((FIRST_J-11))" 120
mine_honest "$B" "$WORK/b.json" "$PRE_J" 150
[[ "$(height)" == "$PRE_J" ]] || die "expected pre-J height $PRE_J, got $(height)"
TIP0="$(rpc getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1)"
RES0="$(reserve_state)"
ok "pre-J fixture at height $PRE_J (tip ${TIP0:0:16}…, reserve $RES0)"

# --- run one attack: valid-PoW block carrying a mutated jackpot, expect rejection + zero mutation ---
run_attack(){ # run_attack <mutation>
  local m="$1" t0 h reject
  local subj_before; subj_before="$(grep -c 'REJECTED by process_block' "$WORK/node.log" 2>/dev/null)"; subj_before="${subj_before:-0}"
  # devnet miner mutates the canonical jackpot, mines VALID DEV PoW, and submits repeatedly.
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$B" --wallet "$WORK/b.json" \
    --mining-key-label default --attack-jackpot "$m" --blocks 100000 --threads 3 >>"$WORK/attack_${m}.log" 2>&1 &
  MINER_PID=$!
  t0=$(date +%s)
  # wait until the node logs at least one new process_block rejection (a valid-PoW block reached
  # validation and was rejected), or a timeout.
  while :; do
    local subj_now; subj_now="$(grep -c 'REJECTED by process_block' "$WORK/node.log" 2>/dev/null)"; subj_now="${subj_now:-0}"
    [[ "$subj_now" -gt "$subj_before" ]] && { reject=1; break; }
    [[ $(($(date +%s)-t0)) -ge 40 ]] && { reject=0; break; }
    sleep 2
  done
  stop_miner
  h="$(height)"; local tip res; tip="$(rpc getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1)"; res="$(reserve_state)"
  # Core invariants: the malicious block was NOT accepted (tip/height/reserve unchanged),
  # and a valid-PoW block actually reached process_block validation (submit-reject observed).
  # A block was accepted (height advanced) — either the mutation was an ineffective no-op
  # OR a malicious block was accepted (a real consensus issue). Abort loudly either way:
  # the fixture is broken and continuing would give false results.
  if [[ "$h" != "$PRE_J" ]]; then
    die "$m — HEIGHT ADVANCED to $h during attack (a block was accepted). Either a no-op mutation or a SECURITY ISSUE — inspect $WORK. Aborting."
  fi
  if [[ "$tip" == "$TIP0" && "$res" == "$RES0" && "$reject" == "1" ]]; then
    ok "$m — valid-PoW block REJECTED; tip/height/reserve unchanged (atomicity holds)"
  elif [[ "$reject" != "1" ]]; then
    bad "$m — no process_block rejection observed within 40s (miner may not have submitted; see attack_${m}.log)"
  else
    bad "$m — STATE MUTATED after rejection (h=$h tip=${tip:0:16} res=$res vs pre h=$PRE_J res=$RES0)"
  fi
}

log "running valid-PoW adversarial jackpot matrix…"
# NOTE: two mutations are NOT in this list because they cannot form a submittable block via
# the miner (an even stronger guarantee — the malicious block cannot be CONSTRUCTED):
#   * remove-winner-output → a jackpot with 0 outputs fails Transaction::Serialize ("no outputs"),
#     so the miner cannot build/merkle/mine it. A jackpot must have >=1 output by construction.
#   * move-jackpot → a DEV jackpot block has exactly [coinbase, jackpot] (2 txs); there is no
#     tx[2] to swap with, so it is a no-op. (Position is already covered: the validator requires
#     J at index 1, proven by remove-jackpot and dup-jackpot.)
for M in wrong-winner winner-self payout-plus payout-minus payout-zero reverse-inputs \
         remove-input dup-input extra-output dup-jackpot remove-jackpot coinbase-mutate; do
  run_attack "$M"
done

# --- control: an HONEST block 24 must still be accepted (proves only mutations are rejected) ---
log "control: honest block $FIRST_J must be accepted…"
mine_honest "$B" "$WORK/b.json" "$FIRST_J" 120
if [[ "$(height)" == "$FIRST_J" ]]; then
  BH="$(rpc getblockhash "[$FIRST_J]" | grep -oE '[a-f0-9]{64}')"
  TC="$(rpc getblock "[\"$BH\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+')"
  [[ "$TC" == "2" ]] && ok "honest block $FIRST_J accepted with canonical jackpot (tx_count=2)" \
    || bad "honest block $FIRST_J accepted but tx_count=$TC (expected 2)"
else
  bad "honest block $FIRST_J NOT accepted after the attacks (height $(height)) — setup broken"
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — every valid-PoW non-canonical jackpot rejected with zero state mutation; honest block accepted"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi
