#!/usr/bin/env bash
# =============================================================================
# run_v16_devnet_jackpot_v2.sh — Historical Jackpot V2 end-to-end on DEVNET_FAST.
# HIST_JACKPOT_V2_HEIGHT=42, epoch=6. Node txs are only valid at h>=42, so:
#   * #42 (first V2 jackpot): no bind can exist yet  -> 0 eligible -> ROLLOVER.
#   * #48 (next V2 jackpot):  bootstrap requires 1 heartbeat (epoch 0=[42,47]).
# Decisive V2 proof: bind + heartbeat ONLY miner B (the current miner of #48).
# Under V15, B (current miner) is EXCLUDED (anti-self) and A would win; under V2,
# eligible={B} -> B wins its OWN jackpot block. A (>=3 blocks, NOT bound) is
# excluded by the node gate.
#   Env: BUILD_DIR (default build-devnet)
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet}"
WORK="$(mktemp -d /tmp/v16jp.XXXXXX)"
P2P_PORT=$(( (RANDOM % 20000) + 20000 )); RPC_PORT=$(( P2P_PORT + 1 ))
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
NODE_LOG="$WORK/node.log"; FAILED=0
log(){ printf '[v16jp] %s\n' "$*"; }
ok(){  printf '[v16jp] PASS  %s\n' "$*"; }
bad(){ printf '[v16jp] FAIL  %s\n' "$*"; FAILED=1; }
NODE_PID=""; MINER_PID=""
stop_miner(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; true; }
cleanup(){ stop_miner; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; true; }
die(){ printf '[v16jp] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || die "binaries missing in $BUILD_DIR"
grep -q '^SOST_DEVNET_FORKS:BOOL=ON' "$BUILD_DIR/CMakeCache.txt" 2>/dev/null || die "$BUILD_DIR not DEVNET"
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
getblk(){ local bh; bh="$(rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}')"; [[ -n "$bh" ]] && rpc getblock "[\"$bh\"]"; }
mine_to(){ local addr="$1" w="$2" tgt="$3" dl="$4" t0; t0=$(date +%s)
  "$MINER" --profile dev --rpc "127.0.0.1:$RPC_PORT" --address "$addr" --wallet "$w" \
    --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/miner.log" 2>&1 &
  MINER_PID=$!
  while :; do local h; h="$(height)"; [[ -z "$h" ]] && { sleep 1; continue; }
    [[ "$h" -ge "$tgt" ]] && { stop_miner; return; }
    [[ $(($(date +%s)-t0)) -ge "$dl" ]] && { stop_miner; die "did not reach $tgt in ${dl}s"; }; sleep 2; done; }

log "work=$WORK rpc=$RPC_PORT V2@42 rollover=#42 paid=#48"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 >"$NODE_LOG" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node no RPC"
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
[[ -n "$A" && -n "$B" && "$A" != "$B" ]] || die "wallets"
log "A=$A (NOT bound)  B=$B (bind+heartbeat; current miner of #48)"

# A gets >=3 blocks; B mines across #42 (rollover) up to 43
mine_to "$A" "$WORK/a.json" 16 150; log "after A: $(height)"
mine_to "$B" "$WORK/b.json" 43 180; log "after B->43: $(height)"

# --- assert #42 rolled over (no bind could exist before activation 42) ---
BLK42="$(getblk 42)"
TXC42="$(echo "$BLK42" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' | head -1)"
[[ "$TXC42" == "1" ]] && ok "#42 first V2 jackpot ROLLED OVER (0 eligible, tx_count=1, no payout)" \
                      || bad "#42 tx_count=$TXC42 (expected 1 rollover)"

# --- bind ONLY B (valid now, h>=42) ---
NODEB="$(openssl rand -hex 32)"
BINDHEX="$("$CLI" --wallet "$WORK/b.json" createnodebind 1 "$NODEB" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
[[ ${#BINDHEX} -gt 200 ]] || die "createnodebind failed (see $WORK/cli.log)"
echo "$(rpc sendrawtransaction "[\"$BINDHEX\"]")" | grep -qiE '"result"|txid|accepted' \
  && ok "NODE_BIND(B) accepted" || bad "NODE_BIND rejected"
mine_to "$B" "$WORK/b.json" 45 150   # include the bind (effective ~45)

# --- heartbeat B for epoch 0 (=[42,47]); tip_ref = hash(#41) ---
TIP41="$(rpc getblockhash "[41]" | grep -oE '[a-f0-9]{64}')"
[[ -n "$TIP41" ]] || die "no hash for #41"
HBHEX="$("$CLI" --wallet "$WORK/b.json" nodeheartbeat "$NODEB" 0 "$TIP41" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
[[ ${#HBHEX} -gt 200 ]] || die "nodeheartbeat failed (see $WORK/cli.log)"
echo "$(rpc sendrawtransaction "[\"$HBHEX\"]")" | grep -qiE '"result"|txid|accepted' \
  && ok "NODE_HEARTBEAT(B, epoch 0) accepted" || bad "heartbeat rejected"
mine_to "$B" "$WORK/b.json" 47 150   # include the heartbeat (within epoch 0)

# --- DIAGNOSTIC: where did the node txs land? ---
log "mempool_before_48=$(rpc getmempoolinfo)"
for hh in 43 44 45 46 47; do
  bd="$(getblk $hh)"; tc="$(echo "$bd" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' | head -1)"
  log "  block #$hh tx_count=$tc"
done

# --- B mines the paid V2 jackpot block #48 ---
mine_to "$B" "$WORK/b.json" 48 150
BLK48="$(getblk 48)"
TXC="$(echo "$BLK48" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' | head -1)"
CBM="$(echo "$BLK48" | grep -oE '"miner_address":"[^"]+"' | grep -oE 'sost1[a-z0-9]+' | head -1)"
WIN="$(echo "$BLK48" | grep -oE '"lottery_winner_address":"[^"]+"' | grep -oE 'sost1[a-z0-9]+' | head -1)"
PAY="$(echo "$BLK48" | grep -oE '"lottery_payout":[0-9]+' | grep -oE '[0-9]+' | head -1)"
log "#48: tx_count=$TXC coinbase=$CBM winner=$WIN payout=$PAY"
[[ "$TXC" == "2" ]] && ok "#48 has coinbase + jackpot tx" || bad "#48 tx_count=$TXC (want 2)"
[[ "$CBM" == "$B" ]] && ok "current miner of #48 is B" || bad "coinbase=$CBM (want B)"
[[ "$WIN" == "$B" ]] && ok "V2 winner == B == CURRENT MINER (V15 forbids anti-self) -> V2 SELECTOR LIVE" \
                     || bad "winner=$WIN (want B)"
[[ -n "$WIN" && "$WIN" != "$A" ]] && ok "unbound miner A EXCLUDED by node gate (did not win)" || bad "A won despite not being bound"
[[ "${PAY:-0}" -gt 0 ]] && ok "V2 jackpot PAID ($PAY stocks)" || bad "no payout"

[[ "$FAILED" == "0" ]] && echo "[v16jp] RESULT: PASS — V2 rollover(#42) + first PAID node-gated weighted jackpot(#48) end-to-end" \
                       || echo "[v16jp] RESULT: FAIL"
exit "$FAILED"
