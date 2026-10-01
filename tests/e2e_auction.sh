#!/usr/bin/env bash
# E2E — AUCTION modality: ATOMIC asset<->SOST settlement in a single tx.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-rc/build-v30000-dev"; G="$SP/wt-rc/genesis_block.json"; [ -f "$G" ] || G="$SP/wt-v2/genesis_block.json"
R=$(mktemp -d); printf p>"$R/pass"; chmod 600 "$R/pass"; echo "ROOT=$R"
PORT=19931; RPCP=19932
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" http://127.0.0.1:$RPCP/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
sw(){ ( sleep "$1" )& wait $!; }
CLI(){ "$BIN/sost-cli" "$@" --wallet "$R/w.json" --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass"; }
"$BIN/sost-cli" newwallet --wallet "$R/w.json">/dev/null 2>&1
SELLER=$("$BIN/sost-cli" getnewaddress seller --wallet "$R/w.json" 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "seller=$SELLER"
N=$(nice -n 5 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --port $PORT --rpc-port $RPCP --rpc-user u --rpc-pass-file "$R/pass">>"$R/node.log" 2>&1 & echo $!)
for i in $(seq 1 60);do curl -s --max-time 2 -o /dev/null http://127.0.0.1:$RPCP/ 2>/dev/null&&break;sw 0.5;done
mine(){ nice -n 5 timeout 400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --mining-key-label seller --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass" --blocks "$1" --realtime --threads 4 >>"$R/miner.log" 2>&1; }
abal(){ rpc getassetbalance "[\"$1\",\"$2\"]" | grep -oE '"balance":[0-9]+' | grep -oE '[0-9]+'; }
sbal(){ rpc getbalance "[\"$1\"]" | grep -oE '"available":"[0-9.]+"' | grep -oE '[0-9.]+' | head -1; }
echo "[$(date +%T)] minando 55..."; mine 55
echo "[$(date +%T)] createasset ARTPZ (tokenized item, supply 500)..."
AID=$(CLI createasset ARTPZ "Auction Item" 0 fixed 500 500 --from-address "$SELLER" 2>&1 | grep -oE 'asset_id: [0-9a-f]{64}' | grep -oE '[0-9a-f]{64}')
echo "  asset_id=$AID"; mine 3
BUYER=$(CLI getnewaddress buyer 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1); echo "  buyer=$BUYER"
# fund buyer with SOST for the price (10 SOST)
CLI send "$BUYER" 10 --from-address "$SELLER" --yes >/dev/null 2>&1; mine 2
echo "  PRE  : seller asset=$(abal "$SELLER" "$AID") buyer asset=$(abal "$BUYER" "$AID") | seller SOST=$(sbal "$SELLER") buyer SOST=$(sbal "$BUYER")"
PRICE=300000000   # 3 SOST in stocks
echo "[$(date +%T)] auctionsettle: 500 ARTPZ seller->buyer, price 3 SOST buyer->seller (ATOMIC)..."
CLI auctionsettle "$AID" 500 "$SELLER" "$BUYER" "$PRICE" 2>&1 | grep -E 'txid|node|Error' | sed 's/^/    /'
mine 3
echo "  POST : seller asset=$(abal "$SELLER" "$AID") buyer asset=$(abal "$BUYER" "$AID") | seller SOST=$(sbal "$SELLER") buyer SOST=$(sbal "$BUYER")"
echo "  EXPECT: seller asset=0 buyer asset=500 ; seller SOST +3 ; buyer SOST ~7 (10 - 3 - fee)"
kill -9 $N 2>/dev/null
echo "E2E_AUCTION_DONE ROOT_KEPT=$R"
