#!/usr/bin/env bash
# =============================================================================
# run_v16_devnet_autohb.sh — NATIVE auto-heartbeat, end-to-end (PAID V2 jackpot).
# Same decisive scenario as run_v16_devnet_jackpot_v2_paid.sh, but the heartbeat
# is NOT sent by the CLI: the node is launched with --node-key and must emit the
# NODE_HEARTBEAT itself, once the bind confirms and >= block #18. Proves the
# native auto-heartbeat makes a bound node eligible with zero manual heartbeat.
# Build: build-devnet-v2e (HIST_JACKPOT_V2_HEIGHT=18). epoch=6, epoch0=[18,23].
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet-v2e}"
WORK="$(mktemp -d /tmp/v16autohb.XXXXXX)"
P2P_PORT=$(( (RANDOM % 20000) + 20000 )); RPC_PORT=$(( P2P_PORT + 1 ))
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
FAILED=0; FIRSTJ=24
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
log(){ printf '[autohb] %s\n' "$*"; }
ok(){  printf '[autohb] PASS  %s\n' "$*"; }
bad(){ printf '[autohb] FAIL  %s\n' "$*"; FAILED=1; }
NODE_PID=""; MINER_PID=""
stop_miner(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; true; }
cleanup(){ stop_miner; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; true; }
die(){ printf '[autohb] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || die "binaries missing in $BUILD_DIR"
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
getblk(){ local bh; bh="$(rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}')"; [[ -n "$bh" ]] && rpc getblock "[\"$bh\"]"; }
mpsize(){ rpc getmempoolinfo | grep -oE '"size":[0-9]+' | grep -oE '[0-9]+'; }
one_addr(){ rpc getaddressutxos "[\"$1\"]" | python3 -c 'import sys,json
try:
 d=json.load(sys.stdin); r=d.get("result",[]); print(sum(int(u.get("amount_stocks",0)) for u in r), len(r))
except Exception: print(0,0)'; }
resv(){ local gs gc ps pc; read -r gs gc < <(one_addr "$1"); read -r ps pc < <(one_addr "$2"); echo "$((gs+ps)) $((gc+pc))"; }
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  MINER_PID=$!
  while :; do local h; h="$(height)"; [[ -z "$h" ]] && { sleep 1; continue; }
    [[ "$h" -ge "$tgt" ]] && { stop_miner; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stop_miner; die "did not reach $tgt in ${dl}s"; }; sleep 2; done; }

# node key generated FIRST so we can hand it to the node for auto-heartbeat
NODEB="$(openssl rand -hex 32)"
log "work=$WORK rpc=$RPC_PORT (V2@18 build) firstJ=$FIRSTJ node-key=${NODEB:0:12}…"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --node-key "$NODEB" \
  --connect 127.0.0.1:1 >"$WORK/node.log" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node no RPC"
grep -q 'auto-heartbeat enabled' "$WORK/node.log" && ok "node started auto-heartbeat thread" || bad "auto-heartbeat thread not enabled"

A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
[[ -n "$A" && -n "$B" && "$A" != "$B" ]] || die "wallets"
log "A=$A (NOT bound)  B=$B (bind only; heartbeat is AUTOMATIC via --node-key)"

mine_to "$A" "$WORK/a.json" 8 120;  log "after A: $(height)"
mine_to "$B" "$WORK/b.json" 19 150; log "after B->19: $(height)"

# bind ONLY B — but the node key MUST match --node-key so the node auto-heartbeats it.
# createnodebind derives node_pubkey from the SAME NODEB the node holds.
BINDHEX="$("$CLI" --wallet "$WORK/b.json" createnodebind 1 "$NODEB" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
[[ ${#BINDHEX} -gt 200 ]] || die "createnodebind failed"
echo "$(rpc sendrawtransaction "[\"$BINDHEX\"]")" | grep -qiE '"result"|txid|accepted' && ok "NODE_BIND(B) accepted" || bad "bind rejected"
mine_to "$B" "$WORK/b.json" 21 150   # confirm the bind (effective #inc+1)

# NO manual heartbeat. Wait for the node to AUTO-emit it into its mempool.
log "waiting for native auto-heartbeat (mempool)…"
HB_SEEN=0
for _ in $(seq 1 20); do
  if grep -q 'emitted heartbeat for epoch 0' "$WORK/node.log"; then HB_SEEN=1; break; fi
  if [[ "$(mpsize)" -ge 1 ]]; then HB_SEEN=1; break; fi
  sleep 2
done
[[ "$HB_SEEN" == "1" ]] && ok "node auto-emitted NODE_HEARTBEAT (no CLI heartbeat used)" || bad "no auto-heartbeat appeared"
grep -q 'emitted heartbeat for epoch 0' "$WORK/node.log" && ok "node.log confirms auto-heartbeat epoch 0" || log "note: heartbeat seen via mempool"
mine_to "$B" "$WORK/b.json" 23 150   # mine the auto-heartbeat in (epoch0 closes at 23)

# eligibility should now be true for B (auto-heartbeat), false for A (unbound)
EB="$(rpc checkhistoricaljackpoteligibility "[\"$B\"]")"; log "RPC checkelig B: $EB"
EA="$(rpc checkhistoricaljackpoteligibility "[\"$A\"]")"; log "RPC checkelig A: $EA"
echo "$EB" | grep -q '"eligible":true'  && ok "B eligible via AUTO-heartbeat" || bad "B not eligible (auto-heartbeat failed)"
echo "$EA" | grep -q '"eligible":false' && ok "A eligible=false (node gate)" || bad "A eligible unexpectedly"

read -r RB RC < <(resv "$GOLD" "$POPC"); log "reserve_before=$RB ($RC UTXOs)"
mine_to "$B" "$WORK/b.json" "$FIRSTJ" 150
BLK="$(getblk $FIRSTJ)"
TXC="$(echo "$BLK" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' | head -1)"
# tx_count >= 2: coinbase + V2 jackpot tx; the jackpot block may ALSO carry the
# epoch auto-heartbeat (proves a jackpot block coexists with a node tx).
[[ "$TXC" -ge 2 ]] && ok "#$FIRSTJ paid V2 jackpot (coinbase + jackpot tx; tx_count=$TXC)" || bad "#$FIRSTJ tx_count=$TXC (want >=2)"
AUD="$(rpc getjackpotv2audit "[24]")"; log "audit #24: $AUD"
echo "$AUD" | grep -q '"is_v2_jackpot":true' && ok "audit: #24 is V2" || bad "audit not v2"
echo "$AUD" | grep -q "\"winner_address\":\"$B\"" && ok "audit winner == B (won via auto-heartbeat)" || bad "audit winner != B"
read -r RA RAC < <(resv "$GOLD" "$POPC"); log "reserve_after=$RA"
[[ "$RA" -lt "$RB" ]] && ok "reserve spent by V2 jackpot ($RB -> $RA)" || bad "reserve not spent"

if [[ "$FAILED" == "0" ]]; then
  echo "[autohb] RESULT: PASS — native auto-heartbeat made a bound node eligible and it won the PAID V2 jackpot, with NO manual heartbeat"
else
  echo "[autohb] RESULT: FAIL — see $WORK"; fi
cleanup
exit "$FAILED"
