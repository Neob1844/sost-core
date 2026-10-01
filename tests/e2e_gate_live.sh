#!/usr/bin/env bash
# E2E — admin consensus gate ACTIVE on a live devnet node (final build).
# The node is built with ADMIN_AUTHORITY_PKH = the test wallet's 'm' address.
# Proves: admin-signed asset op SUCCEEDS; a non-admin asset op is REJECTED (S14).
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-rc/build-v30000-devadmin"; G="$SP/wt-rc/genesis_block.json"; [ -f "$G" ] || G="$SP/wt-v2/genesis_block.json"
R=$(mktemp -d); printf p>"$R/pass"; chmod 600 "$R/pass"; echo "ROOT=$R"
cp "$SP/devadmin_wallet.json" "$R/w.json"    # the baked-admin wallet
PORT=19951; RPCP=19952
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" http://127.0.0.1:$RPCP/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
sw(){ ( sleep "$1" )& wait $!; }
CLI(){ "$BIN/sost-cli" "$@" --wallet "$R/w.json" --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass"; }
ADMIN="sost1064ea89b4fe4a8f03f696ec79e1642b26a5a9e46"   # the baked-admin address (pkh matches ADMIN_AUTHORITY_PKH); do NOT getnewaddress (creates a 2nd key)
echo "admin(mining) addr=$ADMIN"
N=$(nice -n 5 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --port $PORT --rpc-port $RPCP --rpc-user u --rpc-pass-file "$R/pass">>"$R/node.log" 2>&1 & echo $!)
for i in $(seq 1 60);do curl -s --max-time 2 -o /dev/null http://127.0.0.1:$RPCP/ 2>/dev/null&&break;sw 0.5;done
mine(){ nice -n 5 timeout 400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --mining-key-label m --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass" --blocks "$1" --realtime --threads 4 >>"$R/miner.log" 2>&1; }
abal(){ rpc getassetbalance "[\"$1\",\"$2\"]" | grep -oE '"balance":[0-9]+' | grep -oE '[0-9]+'; }
echo "[$(date +%T)] mine 55 (fund admin + pass activation 42)"; mine 55
echo "  height=$(num "$(rpc getblockcount)")  (restricted dev mode ACTIVE from 42)"
# ADMIN creates an asset -> funded by admin's UTXOs (admin-signed input) -> gate passes
echo "[$(date +%T)] ADMIN createasset GATED (fixed 1000)..."
COUT=$(CLI createasset GATED "Gated Token" 0 fixed 1000 1000 --from-address "$ADMIN" 2>&1)
AID=$(echo "$COUT" | grep -oE 'asset_id: [0-9a-f]{64}' | grep -oE '[0-9a-f]{64}')
echo "$COUT" | grep -E 'asset_id|Error|node' | sed 's/^/    /'
mine 3
echo "  ADMIN create: balance=$(abal "$ADMIN" "$AID") (expect 1000 — admin authorised)"
# NON-ADMIN attempt: fund a fresh address, try createasset from it -> should be REJECTED S14
NONADM=$(CLI getnewaddress other 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
CLI send "$NONADM" 20 --from-address "$ADMIN" --yes >/dev/null 2>&1; mine 2
echo "[$(date +%T)] NON-ADMIN createasset attempt from $NONADM ..."
NOUT=$(CLI createasset EVIL "Evil Token" 0 fixed 1000 1000 --from-address "$NONADM" 2>&1)
echo "$NOUT" | grep -E 'asset_id|Error|node|rejected|S14|restricted' | sed 's/^/    /'
mine 2
# the EVIL asset must NOT exist (gate rejected it at consensus/mempool)
EVID=$(echo "$NOUT" | grep -oE 'asset_id: [0-9a-f]{64}' | grep -oE '[0-9a-f]{64}')
echo "  non-admin asset in index? $(if [ -n "$EVID" ]; then rpc getasset "[\"$EVID\"]" | grep -oE '"issued":[0-9]+' || echo 'NOT FOUND (rejected)'; else echo 'no asset_id built'; fi)"
echo "  === node.log gate rejections ==="; grep -iE 'S14|restricted|admin|native asset' "$R/node.log" 2>/dev/null | tail -4
kill -9 $N 2>/dev/null
echo "E2E_GATE_LIVE_DONE"
