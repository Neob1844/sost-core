#!/usr/bin/env bash
# =============================================================================
# run_v15_devnet_reindex.sh — Historical-Jackpot load_chain/reindex equivalence + hardening.
#
# Two properties on DEVNET_FAST, isolated ports (independent of the reorg/restart/soak
# harnesses so it can run alongside them):
#
#   A. CLEAN REPLAY EQUIVALENCE — a node that mines a chain through the first live jackpot
#      payout, stopped and reloaded from its on-disk chain via load_chain (the same replay
#      path a reindex uses), reproduces byte-identical consensus state (chain + reserve +
#      UTXOs + g_blocks/g_block_undos sizes).
#
#   B. TAMPERED-JACKPOT REJECTION — if the persisted jackpot block is altered on disk
#      (its TX_TYPE_JACKPOT transaction replaced by a non-canonical one), load_chain MUST
#      reject it: the node stops replaying BEFORE the bad block, so the reserve is NEVER
#      spent and no partial jackpot state survives. A tampered datadir cannot inject a
#      fraudulent reserve spend on load. (Same single keyless authorization as
#      process_block/reorg — validate_live_jackpot runs on every load.)
#
# Usage: tests/run_v15_devnet_reindex.sh
#   Env: BUILD_DIR (default build-devnet)
# Exit non-zero on any mismatch. Datadirs/logs preserved on failure.
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
RPC=18994; P2P=19994
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/v15reindex.XXXXXX")"
FIRST_J=24; FAILED=0
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
declare -a PIDS=()
log(){ printf '[reindex] %s\n' "$*"; }
ok(){ printf '[reindex] PASS  %s\n' "$*"; }
bad(){ printf '[reindex] FAIL  %s\n' "$*"; FAILED=1; }
cleanup(){
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  if [[ -n "${WORK:-}" ]]; then
    for pid in $(pgrep -f -- "$WORK" 2>/dev/null); do [[ "$pid" == "$$" ]] && continue; kill "$pid" 2>/dev/null; done
  fi
  wait 2>/dev/null
}
die(){ printf '[reindex] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "not a DEVNET build"

rpc(){ curl -s --max-time 15 -H 'content-type: application/json' \
       --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
tiphash(){ rpc getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1; }
blockhash(){ rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}' | head -1; }
utxos(){ rpc getaddressutxos "[\"$1\"]" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); r=d.get("result",[])
 print("\n".join(sorted("%s:%s:%s"%(u.get("txid"),u.get("vout"),u.get("amount_stocks")) for u in r)))
except Exception: pass'; }
reserve_tc(){ rpc getaddressutxos "[\"$1\"]" | python3 -c 'import sys,json
try: d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
reserve(){ local gs gc ps pc; read -r gs gc < <(reserve_tc "$GOLD"); read -r ps pc < <(reserve_tc "$POPC"); echo "$((gs+ps)):$((gc+pc))"; }
bu(){ rpc devchainstate | python3 -c 'import sys,json
d=json.load(sys.stdin).get("result",{})
if isinstance(d,str): d=json.loads(d)
print(d.get("blocks_size"),d.get("undos_size"))'; }
manifest(){ local h out x a; h="$(height)"; out="TIP=$(tiphash) H=$h"$'\n'
  for x in $(seq 0 "$h"); do out+="B$x=$(blockhash "$x")"$'\n'; done
  for a in "$WA" "$WB" "$GOLD" "$POPC"; do out+="U[$a]:"$'\n'"$(utxos "$a")"$'\n'; done
  printf '%s' "$out" | sha256sum | cut -d' ' -f1; }
start(){ "$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$1" --port "$P2P" --rpc-port "$RPC" \
    --rpc-noauth --connect 127.0.0.1:1 >"$WORK/$2.log" 2>&1 &
  PIDS+=($!); NODE_PID=$!
  for _ in $(seq 1 40); do sleep 1; [[ -n "$(height)" ]] && return 0; done; return 1; }
stop(){ [[ -n "${NODE_PID:-}" ]] && kill "$NODE_PID" 2>/dev/null; sleep 2; NODE_PID=""; }
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  local mp=$!; PIDS+=("$mp")
  while :; do local h; h="$(height)"; [[ "$h" -ge "$tgt" ]] && { kill "$mp" 2>/dev/null; sleep 1; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { kill "$mp" 2>/dev/null; die "stuck reaching $tgt (CPU contention? deadline $dl)"; }; sleep 2; done; }

WA="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
WB="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
log "A=$WA B=$WB work=$WORK (rpc=$RPC)"

# === build a chain through the first jackpot payout (h24) ===
start "$WORK/chain.json" boot || die "node did not boot"
mine_to "$WA" "$WORK/a.json" "$((FIRST_J-11))" 300
mine_to "$WB" "$WORK/b.json" "$((FIRST_J-1))" 300
RES_PREJ="$(reserve)"
mine_to "$WB" "$WORK/b.json" "$FIRST_J" 300
[[ "$(height)" == "$FIRST_J" ]] || die "did not reach jackpot height"
GOLDEN="$(manifest)"; RES_POSTJ="$(reserve)"
BH="$(blockhash "$FIRST_J")"; TC="$(rpc getblock "[\"$BH\"]" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+')"
[[ "$TC" == "2" ]] && ok "built chain through jackpot h$FIRST_J (payout applied; reserve $RES_PREJ -> $RES_POSTJ)" || bad "no jackpot at h$FIRST_J"
stop

# === A. CLEAN REPLAY EQUIVALENCE (load_chain replay == original) ===
cp "$WORK/chain.json" "$WORK/clean.json"
start "$WORK/clean.json" clean_reload || die "clean reload did not boot"
[[ "$(height)" == "$FIRST_J" ]] && ok "clean reload replays to h$FIRST_J" || bad "clean reload height=$(height) != $FIRST_J"
M2="$(manifest)"; read -r bs us < <(bu)
[[ "$M2" == "$GOLDEN" ]] && ok "REPLAY EQUIVALENCE: reloaded state == original (${GOLDEN:0:16}…)" || bad "replay drift (${GOLDEN:0:12} vs ${M2:0:12})"
[[ "$bs" == "$us" ]] && ok "g_blocks==g_block_undos ($bs) after replay" || bad "g_blocks($bs)!=g_block_undos($us)"
stop

# === B. TAMPERED-JACKPOT REJECTION ===
# Replace the jackpot block's TX_TYPE_JACKPOT tx (transactions[1]) with a copy of its
# coinbase (transactions[0]) — a valid-deserializing but NON-canonical jackpot. load_chain
# must reject it via validate_live_jackpot and stop BEFORE the reserve is spent.
python3 - "$WORK/chain.json" "$WORK/tampered.json" "$FIRST_J" <<'PY'
import json,sys
src,dst,hj=sys.argv[1],sys.argv[2],int(sys.argv[3])
d=json.load(open(src))
blks=d.get("blocks",[])
n=0
for b in blks:
    if b.get("height")==hj:
        txs=b.get("transactions",[])
        if len(txs)>=2:
            txs[1]=txs[0]   # non-canonical jackpot: a duplicate coinbase in the jackpot slot
            b["transactions"]=txs; n+=1
json.dump(d,open(dst,"w"))
print("tampered blocks:",n)
PY
start "$WORK/tampered.json" tampered || log "tampered chain: node refused to boot (also acceptable)"
TH="$(height)"
RES_TAMPERED="$(reserve)"
if [[ -z "$TH" || "$TH" -lt "$FIRST_J" ]]; then
  ok "tampered jackpot REJECTED on load: node did not reach h$FIRST_J (height=${TH:-none})"
else
  bad "tampered jackpot ACCEPTED on load (height=$TH) — SECURITY ISSUE"
fi
if grep -qiE 'Historical Jackpot mismatch|jackpot.*mismatch|FATAL.*[Jj]ackpot' "$WORK/tampered.log"; then
  ok "load logged the jackpot mismatch rejection"
else
  log "note: no explicit jackpot-mismatch log line (rejection may be via merkle/deserialize — still rejected)"
fi
# The decisive property: the reserve was NOT spent by the tampered jackpot.
if [[ "$RES_TAMPERED" == "$RES_PREJ" ]]; then
  ok "reserve INTACT after tampered load ($RES_TAMPERED == pre-jackpot $RES_PREJ) — no fraudulent spend"
else
  # still acceptable if the node refused to boot entirely (reserve unqueryable)
  [[ -z "$TH" ]] && ok "node refused to boot on tampered chain (reserve never exposed)" \
    || bad "reserve changed after tampered load ($RES_TAMPERED vs pre-jackpot $RES_PREJ)"
fi
stop

echo
if [[ "$FAILED" -eq 0 ]]; then
  log "RESULT: PASS — load_chain replay is byte-identical; a tampered persisted jackpot is rejected with the reserve never spent"
  trap - EXIT; cleanup; rm -rf "$WORK"; exit 0
else
  log "RESULT: FAIL (see $WORK)"; trap - EXIT; cleanup; exit 1
fi
