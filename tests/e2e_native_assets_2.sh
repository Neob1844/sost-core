#!/usr/bin/env bash
# E2E-2 — ISSUE + BURN on a CAPPED_REISSUABLE asset (exercises issuance authority).
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-rc/build-v30000-dev"; G="$SP/wt-rc/genesis_block.json"
[ -f "$G" ] || G="$SP/wt-v2/genesis_block.json"
R=$(mktemp -d); printf p>"$R/pass"; chmod 600 "$R/pass"; echo "ROOT=$R"
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" http://127.0.0.1:19912/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
sw(){ ( sleep "$1" )& wait $!; }
CLI(){ "$BIN/sost-cli" "$@" --wallet "$R/w.json" --rpc 127.0.0.1:19912 --rpc-user u --rpc-pass-file "$R/pass"; }
"$BIN/sost-cli" newwallet --wallet "$R/w.json">/dev/null 2>&1
ADDR=$("$BIN/sost-cli" getnewaddress m --wallet "$R/w.json" 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "wallet addr=$ADDR"
N=$(nice -n 5 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --port 19911 --rpc-port 19912 --rpc-user u --rpc-pass-file "$R/pass">>"$R/node.log" 2>&1 & echo $!)
for i in $(seq 1 60);do curl -s --max-time 2 -o /dev/null http://127.0.0.1:19912/ 2>/dev/null&&break;sw 0.5;done
mine(){ nice -n 5 timeout 400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --mining-key-label m --rpc 127.0.0.1:19912 --rpc-user u --rpc-pass-file "$R/pass" --blocks "$1" --realtime --threads 4 >>"$R/miner.log" 2>&1; }
abal(){ rpc getassetbalance "[\"$1\",\"$2\"]" | grep -oE '"balance":[0-9]+' | grep -oE '[0-9]+'; }
supply(){ rpc getasset "[\"$1\"]" | grep -oE '"issued":[0-9]+,"burned":[0-9]+,"circulating":[0-9]+'; }
echo "[$(date +%T)] minando 55 (funda + activación 42)..."; mine 55
echo "  altura=$(num "$(rpc getblockcount)")"
echo "[$(date +%T)] createasset SILVER (capped_reissuable, max 5000000, mint 1000000)..."
COUT=$(CLI createasset SILVER "Silver Token" 8 capped 5000000 1000000 --from-address "$ADDR" 2>&1)
AID=$(echo "$COUT" | grep -oE 'asset_id: [0-9a-f]{64}' | grep -oE '[0-9a-f]{64}')
echo "  asset_id=$AID"; echo "$COUT" | grep -E 'Error' | sed 's/^/    /'
echo "[$(date +%T)] minando 3 (genesis)..."; mine 3
echo "  CREATE: bal=$(abal "$ADDR" "$AID") (esp 1000000) · supply=$(supply "$AID") (esp 1000000/0/1000000)"
echo "[$(date +%T)] issueasset +500000 SILVER -> $ADDR ..."
CLI issueasset "$AID" 500000 --from-address "$ADDR" 2>&1 | grep -E 'txid|node|Error' | sed 's/^/    /'
echo "[$(date +%T)] minando 3 (issue)..."; mine 3
echo "  ISSUE: bal=$(abal "$ADDR" "$AID") (esp 1500000) · supply=$(supply "$AID") (esp 1500000/0/1500000)"
echo "[$(date +%T)] burnasset 200000 SILVER ..."
CLI burnasset "$AID" 200000 --from-address "$ADDR" 2>&1 | grep -E 'txid|node|Error' | sed 's/^/    /'
echo "[$(date +%T)] minando 3 (burn)..."; mine 3
echo "  BURN: bal=$(abal "$ADDR" "$AID") (esp 1300000) · supply=$(supply "$AID") (esp 1500000/200000/1300000)"
kill -9 $N 2>/dev/null
echo "E2E2_DONE ROOT_KEPT=$R"
