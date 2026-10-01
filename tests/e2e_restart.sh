#!/usr/bin/env bash
# E2E — node RESTART: the native-asset index is derived chain state; after a
# kill+relaunch it must be rebuilt identically from the persisted chain.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-rc/build-v30000-dev"; G="$SP/wt-rc/genesis_block.json"; [ -f "$G" ] || G="$SP/wt-v2/genesis_block.json"
R=$(mktemp -d); printf p>"$R/pass"; chmod 600 "$R/pass"; echo "ROOT=$R"
PORT=19941; RPCP=19942
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" http://127.0.0.1:$RPCP/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
sw(){ ( sleep "$1" )& wait $!; }
CLI(){ "$BIN/sost-cli" "$@" --wallet "$R/w.json" --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass"; }
abal(){ rpc getassetbalance "[\"$1\",\"$2\"]" | grep -oE '"balance":[0-9]+' | grep -oE '[0-9]+'; }
alist(){ rpc listassets | grep -oE '"issued":[0-9]+,"burned":[0-9]+,"circulating":[0-9]+'; }
startnode(){ nice -n 5 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --port $PORT --rpc-port $RPCP --rpc-user u --rpc-pass-file "$R/pass" >>"$R/node.log" 2>&1 & echo $!; }
waitnode(){ for i in $(seq 1 60);do curl -s --max-time 2 -o /dev/null http://127.0.0.1:$RPCP/ 2>/dev/null&&return 0;sw 0.5;done;return 1; }
mine(){ nice -n 5 timeout 400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --mining-key-label m --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass" --blocks "$1" --realtime --threads 4 >>"$R/miner.log" 2>&1; }

"$BIN/sost-cli" newwallet --wallet "$R/w.json">/dev/null 2>&1
ADDR=$("$BIN/sost-cli" getnewaddress m --wallet "$R/w.json" 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "addr=$ADDR"
N=$(startnode); waitnode || { echo "node1 failed"; exit 1; }
echo "[$(date +%T)] mine 55 (fund+activation)"; mine 55
echo "[$(date +%T)] create+issue+burn a CAPPED asset"
AID=$(CLI createasset REST "Restart Token" 0 capped 5000 2000 --from-address "$ADDR" 2>&1 | grep -oE 'asset_id: [0-9a-f]{64}' | grep -oE '[0-9a-f]{64}'); echo "  asset_id=$AID"; mine 3
CLI issueasset "$AID" 1000 --from-address "$ADDR" >/dev/null 2>&1; mine 3
CLI burnasset "$AID" 500 --from-address "$ADDR" >/dev/null 2>&1; mine 3
H1=$(num "$(rpc getblockcount)")
BAL_BEFORE=$(abal "$ADDR" "$AID"); SUP_BEFORE=$(alist)
echo "  BEFORE restart: height=$H1 bal=$BAL_BEFORE supply=$SUP_BEFORE  (expect bal=2500 issued3000/burned500/circ2500)"
# ---- RESTART: kill node by PID, relaunch on same chain file ----
echo "[$(date +%T)] KILL node pid=$N and relaunch (rebuild index from chain)"
kill -9 $N 2>/dev/null; sw 2
N2=$(startnode); waitnode || { echo "node2 failed to restart"; exit 1; }
sw 2
H2=$(num "$(rpc getblockcount)")
BAL_AFTER=$(abal "$ADDR" "$AID"); SUP_AFTER=$(alist)
echo "  AFTER  restart: height=$H2 bal=$BAL_AFTER supply=$SUP_AFTER"
echo "  === VERDICT ==="
[ "$H1" = "$H2" ] && echo "  HEIGHT preserved: PASS ($H1)" || echo "  HEIGHT: FAIL ($H1 != $H2)"
[ "$BAL_BEFORE" = "$BAL_AFTER" ] && [ -n "$BAL_AFTER" ] && echo "  ASSET BALANCE rebuilt: PASS ($BAL_AFTER)" || echo "  ASSET BALANCE: FAIL ($BAL_BEFORE != $BAL_AFTER)"
[ "$SUP_BEFORE" = "$SUP_AFTER" ] && [ -n "$SUP_AFTER" ] && echo "  SUPPLY INDEX rebuilt: PASS ($SUP_AFTER)" || echo "  SUPPLY INDEX: FAIL ($SUP_BEFORE != $SUP_AFTER)"
kill -9 $N2 2>/dev/null
echo "E2E_RESTART_DONE ROOT_KEPT=$R"
