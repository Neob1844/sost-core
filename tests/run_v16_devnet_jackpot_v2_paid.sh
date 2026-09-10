#!/usr/bin/env bash
# =============================================================================
# run_v16_devnet_jackpot_v2_paid.sh — PAID Historical Jackpot V2, end-to-end.
# Build: build-devnet-v2e (SOST_DEVNET_V2_FIRST_JACKPOT => HIST_JACKPOT_V2_HEIGHT=18),
# so the FIRST jackpot (#24) is a V2 jackpot and the (tiny) devnet reserve is still
# full (a V15 jackpot would otherwise drain+retire it first).
# epoch=6, epoch 0=[18,23], bootstrap at #24 requires 1 heartbeat.
# Decisive proof: bind + heartbeat ONLY B (current miner of #24). V2 pays B (its own
# block — V15 anti-self forbids it). A (>=3 blocks, NOT bound) excluded by node gate.
#   Env: BUILD_DIR (default build-devnet-v2e)
# =============================================================================
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-devnet-v2e}"
WORK="$(mktemp -d /tmp/v16jpP.XXXXXX)"
P2P_PORT=$(( (RANDOM % 20000) + 20000 )); RPC_PORT=$(( P2P_PORT + 1 ))
NODE="$BUILD_DIR/sost-node"; MINER="$BUILD_DIR/sost-miner"; CLI="$BUILD_DIR/sost-cli"
FAILED=0; FIRSTJ=24; TIPREF_H=17    # epoch0 tip_ref = hash(V2H-1)=hash(17)
GOLD="sost11a9c6fe1de076fc31c8e74ee084f8e5025d2bb4d"; POPC="sost1d876c5b8580ca8d2818ab0fed393df9cb1c3a30f"
log(){ printf '[v16paid] %s\n' "$*"; }
ok(){  printf '[v16paid] PASS  %s\n' "$*"; }
bad(){ printf '[v16paid] FAIL  %s\n' "$*"; FAILED=1; }
NODE_PID=""; MINER_PID=""
stop_miner(){ [[ -n "$MINER_PID" ]] && kill "$MINER_PID" 2>/dev/null; pkill -P $$ sost-miner 2>/dev/null; MINER_PID=""; true; }
cleanup(){ stop_miner; [[ -n "$NODE_PID" ]] && kill "$NODE_PID" 2>/dev/null; wait 2>/dev/null; true; }
die(){ printf '[v16paid] FATAL %s\n' "$*" >&2; cleanup; log "logs in $WORK"; exit 1; }
trap cleanup EXIT
[[ -x "$NODE" && -x "$MINER" && -x "$CLI" ]] || die "binaries missing in $BUILD_DIR"
rpc(){ curl -s --max-time 15 -H 'content-type: application/json' --data "{\"method\":\"$1\",\"params\":${2:-[]},\"id\":1}" "http://127.0.0.1:$RPC_PORT/"; }
height(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
getblk(){ local bh; bh="$(rpc getblockhash "[$1]" | grep -oE '[a-f0-9]{64}')"; [[ -n "$bh" ]] && rpc getblock "[\"$bh\"]"; }
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

log "work=$WORK rpc=$RPC_PORT (V2@18 build) firstJ=$FIRSTJ"
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/chain.json" \
  --port "$P2P_PORT" --rpc-port "$RPC_PORT" --rpc-noauth --connect 127.0.0.1:1 >"$WORK/node.log" 2>&1 &
NODE_PID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height)" ]] && break; done
[[ -n "$(height)" ]] || die "node no RPC"
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)"
[[ -n "$A" && -n "$B" && "$A" != "$B" ]] || die "wallets"
log "A=$A (NOT bound)  B=$B (bind+heartbeat; current miner of #$FIRSTJ)"

mine_to "$A" "$WORK/a.json" 8 120;  log "after A: $(height)"
mine_to "$B" "$WORK/b.json" 19 150; log "after B->19: $(height)"

# bind ONLY B (valid, h>=18)
NODEB="$(openssl rand -hex 32)"
BINDHEX="$("$CLI" --wallet "$WORK/b.json" createnodebind 1 "$NODEB" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
[[ ${#BINDHEX} -gt 200 ]] || die "createnodebind failed"
echo "$(rpc sendrawtransaction "[\"$BINDHEX\"]")" | grep -qiE '"result"|txid|accepted' && ok "NODE_BIND(B) accepted" || bad "bind rejected"
mine_to "$B" "$WORK/b.json" 21 150

# heartbeat B epoch 0 (=[18,23]); tip_ref = hash(#17)
TIPREF="$(rpc getblockhash "[$TIPREF_H]" | grep -oE '[a-f0-9]{64}')"; [[ -n "$TIPREF" ]] || die "no hash #$TIPREF_H"
HBHEX="$("$CLI" --wallet "$WORK/b.json" nodeheartbeat "$NODEB" 0 "$TIPREF" 2>>"$WORK/cli.log" | tr -d '[:space:]')"
[[ ${#HBHEX} -gt 200 ]] || die "nodeheartbeat failed"
echo "$(rpc sendrawtransaction "[\"$HBHEX\"]")" | grep -qiE '"result"|txid|accepted' && ok "NODE_HEARTBEAT(B,epoch0) accepted" || bad "heartbeat rejected"
mine_to "$B" "$WORK/b.json" 23 150

# --- RPC V2 checks (against real state: B bound+heartbeat, A unbound) ---
EB="$(rpc checkhistoricaljackpoteligibility "[\"$B\"]")"; log "RPC checkelig B: $EB"
EA="$(rpc checkhistoricaljackpoteligibility "[\"$A\"]")"; log "RPC checkelig A: $EA"
echo "$EB" | grep -q '"eligible":true'  && ok "RPC checkeligibility: B eligible=true" || bad "RPC B not eligible"
echo "$EA" | grep -q '"eligible":false' && ok "RPC checkeligibility: A eligible=false (node gate)" || bad "RPC A eligible unexpectedly"

# snapshot reserve, then B mines the PAID V2 jackpot #24
read -r RB RC < <(resv "$GOLD" "$POPC"); log "reserve_before=$RB ($RC UTXOs)"
[[ "$RB" -gt 0 ]] && ok "reserve non-empty before V2 jackpot" || bad "reserve empty"
mine_to "$B" "$WORK/b.json" "$FIRSTJ" 150

BLK="$(getblk $FIRSTJ)"
TXC="$(echo "$BLK" | grep -oE '"tx_count":[0-9]+' | grep -oE '[0-9]+' | head -1)"
CBM="$(echo "$BLK" | grep -oE '"miner_address":"[^"]+"' | grep -oE 'sost1[a-z0-9]+' | head -1)"
JTXID="$(echo "$BLK" | python3 -c 'import sys,json;d=json.load(sys.stdin);r=d.get("result",{});ids=r.get("txids",[]);print(ids[1] if len(ids)>1 else "")')"
log "#$FIRSTJ: tx_count=$TXC coinbase=$CBM jackpot_txid=$JTXID"
[[ "$TXC" == "2" ]] && ok "#$FIRSTJ has coinbase + V2 jackpot tx" || { bad "#$FIRSTJ tx_count=$TXC (want 2)"; }
[[ "$CBM" == "$B" ]] && ok "current miner is B" || bad "coinbase=$CBM"
# resolve winners by parsing tx hex output[0].pubkey_hash (getrawtransaction=hex only).
out0_pkh(){ # <txid> -> 40-hex pkh of output[0]
  local hx; hx="$(rpc getrawtransaction "[\"$1\"]" | grep -oE '"result":"[0-9a-f]+"' | cut -d'"' -f4)"
  [[ -z "$hx" ]] && { echo ""; return; }
  python3 - "$hx" <<'PYX'
import sys
b=bytes.fromhex(sys.argv[1]); o=4+1          # version + tx_type
nin=b[o]; o+=1                                # compact n_in (<253 on devnet)
o+=nin*133                                    # each input: 32+4+64+33
o+=1                                          # compact n_out
o+=8+1                                        # output0: amount(8)+type(1)
print(b[o:o+20].hex())                        # output0 pubkey_hash
PYX
}
CB_PKH="$(out0_pkh "$(echo "$BLK" | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["txids"][0])')")"  # = miner B
A_BLK="$(getblk 5)"; A_CBTX="$(echo "$A_BLK" | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"]["txids"][0])')"
A_PKH="$(out0_pkh "$A_CBTX")"                 # = miner A (A mined 1..8)
if [[ -n "$JTXID" ]]; then
  JWIN_PKH="$(out0_pkh "$JTXID")"
  log "jackpot out0 pkh=$JWIN_PKH  coinbase(B) pkh=$CB_PKH  A pkh=$A_PKH"
  [[ -n "$JWIN_PKH" && "$JWIN_PKH" == "$CB_PKH" ]] && ok "V2 WINNER == B == CURRENT MINER (V15 anti-self forbids) -> V2 PAYMENT LIVE" || bad "jackpot winner pkh=$JWIN_PKH != B pkh=$CB_PKH"
  [[ -n "$JWIN_PKH" && "$JWIN_PKH" != "$A_PKH" ]] && ok "unbound A excluded by node gate (A pkh did NOT win)" || bad "A (unbound) won"
fi
AUD="$(rpc getjackpotv2audit "[24]")"; log "RPC getjackpotv2audit #24: $AUD"
echo "$AUD" | grep -q '"is_v2_jackpot":true' && ok "RPC audit: #24 is V2 jackpot" || bad "RPC audit not v2"
echo "$AUD" | grep -q "\"winner_address\":\"$B\"" && ok "RPC audit winner == B" || bad "RPC audit winner != B"
read -r RA RAC < <(resv "$GOLD" "$POPC"); log "reserve_after=$RA ($RAC UTXOs)"
[[ "$RA" -lt "$RB" ]] && ok "reserve spent by V2 jackpot ($RB -> $RA)" || bad "reserve not spent"

[[ "$FAILED" == "0" ]] && echo "[v16paid] RESULT: PASS — first PAID node-gated weighted Historical Jackpot V2, end-to-end" \
                       || echo "[v16paid] RESULT: FAIL"
exit "$FAILED"
