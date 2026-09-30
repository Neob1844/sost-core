#!/usr/bin/env bash
# E2E — native asset Tokenize (create) on a real devnet node (activation height 42).
# mine (fund + pass activation) -> createasset -> mine (include genesis) -> getasset verify.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-rc/build-v30000-dev"; G="$SP/wt-rc/genesis_block.json"
[ -f "$G" ] || G="$SP/wt-v2/genesis_block.json"
R=$(mktemp -d); printf p>"$R/pass"; chmod 600 "$R/pass"; echo "ROOT=$R G=$G"
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" http://127.0.0.1:19902/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
sw(){ ( sleep "$1" )& wait $!; }
CLI(){ "$BIN/sost-cli" "$@" --wallet "$R/w.json" --rpc 127.0.0.1:19902 --rpc-user u --rpc-pass-file "$R/pass"; }
"$BIN/sost-cli" newwallet --wallet "$R/w.json">/dev/null 2>&1
ADDR=$("$BIN/sost-cli" getnewaddress m --wallet "$R/w.json" 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "wallet addr=$ADDR"
N=$(nice -n 5 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --port 19901 --rpc-port 19902 --rpc-user u --rpc-pass-file "$R/pass">>"$R/node.log" 2>&1 & echo $!)
for i in $(seq 1 60);do curl -s --max-time 2 -o /dev/null http://127.0.0.1:19902/ 2>/dev/null&&break;sw 0.5;done
echo "[$(date +%T)] minando 55 bloques (funda + pasa activación 42)..."
nice -n 5 timeout 900 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --mining-key-label m --rpc 127.0.0.1:19902 --rpc-user u --rpc-pass-file "$R/pass" --blocks 55 --realtime --threads 4 >>"$R/miner.log" 2>&1
H=$(num "$(rpc getblockcount)"); echo "  altura=$H (activación native assets = 42)"
BAL=$(rpc getbalance | grep -oE '"available":"[0-9.]+"' | grep -oE '[0-9.]+' | head -1); echo "  balance=$BAL SOST"
mine(){ nice -n 5 timeout 300 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --mining-key-label m --rpc 127.0.0.1:19902 --rpc-user u --rpc-pass-file "$R/pass" --blocks "$1" --realtime --threads 4 >>"$R/miner.log" 2>&1; }
abal(){ rpc getassetbalance "[\"$1\",\"$2\"]" | grep -oE '"balance":[0-9]+' | grep -oE '[0-9]+'; }
echo "[$(date +%T)] createasset GOLD (fixed, 8 dec, supply 1000000)..."
COUT=$(CLI createasset GOLD "Gold Token" 8 fixed 1000000 1000000 --from-address "$ADDR" 2>&1)
echo "$COUT" | grep -E 'asset_id|txid|Error' | sed 's/^/    /'
AID=$(echo "$COUT" | grep -oE 'asset_id: [0-9a-f]{64}' | grep -oE '[0-9a-f]{64}')
echo "  asset_id=$AID"
echo "[$(date +%T)] minando 3 (incluir genesis)..."; mine 3
echo "  TOKENIZE: getassetbalance($ADDR)=$(abal "$ADDR" "$AID")  (esperado 1000000)"
RECV=$(CLI getnewaddress recv 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "[$(date +%T)] transferasset 300000 GOLD -> $RECV ..."
CLI transferasset "$AID" "$RECV" 300000 --from-address "$ADDR" 2>&1 | grep -E 'txid|node|Error' | sed 's/^/    /'
echo "[$(date +%T)] minando 3 (incluir transfer)..."; mine 3
echo "  TRANSFER: sender($ADDR)=$(abal "$ADDR" "$AID") (esp 700000) · recv($RECV)=$(abal "$RECV" "$AID") (esp 300000)"
echo "  listassets (supply debe seguir 1000000/0):"; rpc listassets | grep -oE '"issued":[0-9]+,"burned":[0-9]+,"circulating":[0-9]+' | sed 's/^/    /'
kill -9 $N 2>/dev/null
echo "=== rechazos asset en node.log ==="; grep -E 'native asset|REJECTED.*asset' "$R/node.log" 2>/dev/null | tail -5
echo "E2E_DONE ROOT_KEPT=$R"
