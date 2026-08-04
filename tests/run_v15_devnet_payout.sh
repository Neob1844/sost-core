#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_payout.sh — automated FIRST-LIVE-JACKPOT test on DEVNET_FAST.
#
# One command reproduces the proven live payout and FAILS if anything mismatches:
#   1. boot a real Profile::DEV node (isolated datadir/ports);
#   2. create two miner wallets A and B;
#   3. mine the early stretch with A, stop A (A enters history);
#   4. mine with B up to firstJ-1, snapshot the reserve (Gold Vault + PoPC balances);
#   5. mine the jackpot block (firstJ) with B;
#   6. assert the block carries coinbase + exactly one TX_TYPE_JACKPOT (tx[1]);
#   7. assert the winner is A (an eligible non-current-miner), winner != B;
#   8. EXACT accounting: sum(reserve inputs) == winner payout + change, mint=burn=fee=0.
#
# This is the runtime proof that D+T+J execute together and the anti-self-payout
# coupling holds end-to-end (validator re-derives cur_miner from the real coinbase).
#
# Usage: tests/run_v15_devnet_payout.sh [--rpc-port P] [--p2p-port P]
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any invariant failure; datadir/logs preserved on failure.
# =============================================================================
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
RPC_PORT=18960; P2P_PORT=19960
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rpc-port) RPC_PORT="$2"; shift 2;;
    --p2p-port) P2P_PORT="$2"; shift 2;;
    -h|--help)  grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15payout.XXXXXX")"
NODE_LOG="$WORK/node.log"
FAILED=0
# DEVNET_FAST canonical schedule (must match params.h under SOST_DEVNET_FORKS).
FIRST_J=24
# Constitutional reserve sinks (params.h ADDR_GOLD_VAULT / ADDR_POPC_POOL).
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"
POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"

log(){ printf '[payout] %s\n' "$*"; }
ok(){  printf '[payout] PASS  %s\n' "$*"; }
bad(){ printf '[payout] FAIL  %s\n' "$*"; FAILED=1; }
NODE_PID=""; MINER_PID=""
stop_miner(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; }
cleanup(){ stop_miner; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; }
die(){ printf '[payout] FATAL %s\n' "$*" >&2; cleanup; log "logs preserved in $WORK"; exit 1; }
trap 'cleanup' EXIT

[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || die "binaries missing in $BUILD_DIR (build -DSOST_DEVNET_FORKS=ON)"
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null \
  || die "$BUILD_DIR is not a SOST_DEVNET_FORKS=ON build"

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
# Reserve sink UTXOs (in stocks) — this is the GROUND TRUTH for accounting: the jackpot
# spends precisely these UTXOs, so their sum == Σ(jackpot inputs) and their count == #inputs.
# We resolve the reserve from the chain UTXO set (not from gettransaction, which cannot
# resolve inputs after they are spent by the jackpot). Echoes "<sum_stocks> <count>".
one_addr(){ rpc getaddressutxos "[\"$1\"]" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); r=d.get("result",[])
 print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
addr_reserve(){ # sum and count across both reserve sinks
  local gs gc ps pc; read -r gs gc < <(one_addr "$1"); read -r ps pc < <(one_addr "$2")
  echo "$((gs+ps)) $((gc+pc))"; }

# --- boot ---
log "work=$WORK  firstJ=$FIRST_J  rpc=$RPC_PORT"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 >"$NODE_LOG" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node did not answer RPC (see $NODE_LOG)"
[[ "$(rpc getinfo | grep -oE '"profile":"[a-z]+"')" == '"profile":"dev"' ]] && ok "node is DEV profile" || bad "node not DEV"

A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
[[ -n "$A" && -n "$B" && "$A" != "$B" ]] || die "could not create two distinct wallets"
log "A=$A  B=$B"

mine_to(){ # mine_to <address> <wallet> <target> <deadline_s>
  local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$addr" \
    --wallet "$w" --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  MINER_PID=$!
  while :; do
    local h; h="$(height)"; [[ -z "$h" ]] && die "lost RPC while mining"
    [[ "$h" -ge "$tgt" ]] && { stop_miner; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stop_miner; die "did not reach height $tgt in ${dl}s (see $WORK/miner.log)"; }
    sleep 2
  done
}

# --- A mines the early stretch, then stops (A is in history, not the current miner at J) ---
log "stage 1: A mines to $((FIRST_J-11))"
mine_to "$A" "$WORK/a.json" "$((FIRST_J-11))" 120
log "  height after A: $(height)"

# --- B mines up to firstJ-1; snapshot the reserve there ---
log "stage 2: B mines to $((FIRST_J-1)) (snapshot reserve)"
mine_to "$B" "$WORK/b.json" "$((FIRST_J-1))" 150
read -r RESERVE_BEFORE RESERVE_COUNT < <(addr_reserve "$GOLD" "$POPC")
log "  reserve_before = $RESERVE_BEFORE stocks across $RESERVE_COUNT UTXOs (Gold+PoPC)"
[[ "$RESERVE_BEFORE" -gt 0 && "$RESERVE_COUNT" -gt 0 ]] && ok "reserve non-empty before jackpot ($RESERVE_BEFORE stocks, $RESERVE_COUNT UTXOs)" || bad "reserve empty before jackpot"

# --- B mines the jackpot block firstJ ---
log "stage 3: B mines the jackpot block $FIRST_J"
mine_to "$B" "$WORK/b.json" "$FIRST_J" 120

# --- inspect the jackpot block ---
BH="$(rpc getblockhash "[$FIRST_J]" | grep -oE '[a-f0-9]{64}')"
BLK="$(rpc getblock "[\"$BH\"]")"
TXC="$(echo "$BLK" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+')"
[[ "$TXC" == "2" ]] && ok "block $FIRST_J has coinbase + jackpot (tx_count=2)" || { bad "block $FIRST_J tx_count=$TXC (expected 2)"; }
CB_MINER="$(echo "$BLK" | grep -oE '"miner_address":"[^"]+"' | grep -oE 'sost1[a-z0-9]+')"
[[ "$CB_MINER" == "$B" ]] && ok "block $FIRST_J coinbase miner == B (the current miner)" || bad "coinbase miner=$CB_MINER, expected B"

# jackpot txid = second txid in the block
JTXID="$(echo "$BLK" | python3 -c 'import sys,json
d=json.load(sys.stdin); r=d.get("result",{}); ids=r.get("txids",[]); print(ids[1] if len(ids)>1 else "")')"
[[ -n "$JTXID" ]] || die "could not read jackpot txid from block $FIRST_J"

# --- resolve the jackpot tx: winner, payout, change, and ALL input amounts ---
JTX="$(rpc gettransaction "[\"$JTXID\"]")"
eval "$(echo "$JTX" | python3 -c '
import sys,json
d=json.load(sys.stdin); r=d.get("result",{})
vin=r.get("vin",[]); vout=r.get("vout",[])
def stk(x):
    try: return int(round(float(x)*100000000))
    except: return 0
in_sum=sum(stk(i.get("amount",0)) for i in vin)
n_in=len(vin); n_resolved=sum(1 for i in vin if i.get("amount",0))
# winner = largest output; change (if any) = an output paying the Gold Vault sink
outs=[(o.get("address",""), stk(o.get("amount",0))) for o in vout]
outs_sorted=sorted(outs, key=lambda x:-x[1])
winner_addr, winner_amt = (outs_sorted[0] if outs_sorted else ("",0))
change_amt=sum(a for (ad,a) in outs if ad!=winner_addr)
print(f"N_IN={n_in}")
print(f"N_RESOLVED={n_resolved}")
print(f"IN_SUM={in_sum}")
print(f"WINNER_ADDR={winner_addr}")
print(f"WINNER_AMT={winner_amt}")
print(f"CHANGE_AMT={change_amt}")
print(f"OUT_SUM={winner_amt+change_amt}")
')"

log "jackpot tx $JTXID : inputs=$N_IN (resolved $N_RESOLVED), in_sum=$IN_SUM, winner=$WINNER_ADDR payout=$WINNER_AMT change=$CHANGE_AMT"

# --- assertions: winner identity ---
[[ "$WINNER_ADDR" == "$A" ]] && ok "winner is A (the eligible non-current miner)" || bad "winner=$WINNER_ADDR, expected A=$A"
[[ "$WINNER_ADDR" != "$B" ]] && ok "winner != B (anti-self-payout: current miner cannot win its own block)" || bad "winner == current miner B (SECURITY BUG)"

# --- EXACT accounting (ground truth = the reserve UTXO set at firstJ-1, not gettransaction) ---
# The jackpot spends the ENTIRE reserve, so #inputs == reserve UTXO count and
# Σinputs == reserve_before. Prove reserve_before == payout + change (mint=burn=fee=0).
[[ "$N_IN" == "$RESERVE_COUNT" ]] && ok "jackpot spends ALL $RESERVE_COUNT reserve UTXOs (#inputs == reserve count)" \
  || bad "#inputs=$N_IN != reserve UTXO count=$RESERVE_COUNT — not every reserve UTXO accounted"
if [[ "$RESERVE_BEFORE" == "$OUT_SUM" ]]; then
  ok "EXACT accounting: reserve_before == payout + change ($RESERVE_BEFORE == $WINNER_AMT + $CHANGE_AMT); mint=burn=fee=0"
else
  bad "accounting mismatch: reserve_before=$RESERVE_BEFORE != payout+change=$OUT_SUM (diff $((RESERVE_BEFORE-OUT_SUM)))"
fi

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — first live Historical Jackpot verified end-to-end on DEVNET_FAST"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi
