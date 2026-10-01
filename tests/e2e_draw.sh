#!/usr/bin/env bash
# E2E — DRAW modality on a real devnet node.
# Real prize asset + real on-chain entries + block-hash entropy + verifiable
# selection + real on-chain settlement to the entropy-selected winner.
ulimit -f unlimited 2>/dev/null; set -uo pipefail
SP="/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad"
BIN="$SP/wt-rc/build-v30000-dev"; G="$SP/wt-rc/genesis_block.json"; [ -f "$G" ] || G="$SP/wt-v2/genesis_block.json"
R=$(mktemp -d); printf p>"$R/pass"; chmod 600 "$R/pass"; echo "ROOT=$R"
PORT=19921; RPCP=19922
rpc(){ curl -s --max-time 15 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" http://127.0.0.1:$RPCP/ 2>/dev/null; }
num(){ echo "$1"|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'|head -1; }
rstr(){ echo "$1"|grep -oE '"result":"[0-9a-f]+"'|grep -oE '[0-9a-f]{8,}'|head -1; }
sw(){ ( sleep "$1" )& wait $!; }
CLI(){ "$BIN/sost-cli" "$@" --wallet "$R/w.json" --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass"; }
"$BIN/sost-cli" newwallet --wallet "$R/w.json">/dev/null 2>&1
ORG=$("$BIN/sost-cli" getnewaddress org --wallet "$R/w.json" 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "organizer=$ORG"
N=$(nice -n 5 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --port $PORT --rpc-port $RPCP --rpc-user u --rpc-pass-file "$R/pass">>"$R/node.log" 2>&1 & echo $!)
for i in $(seq 1 60);do curl -s --max-time 2 -o /dev/null http://127.0.0.1:$RPCP/ 2>/dev/null&&break;sw 0.5;done
mine(){ nice -n 5 timeout 400 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$R/chain.json" --wallet "$R/w.json" --mining-key-label org --rpc 127.0.0.1:$RPCP --rpc-user u --rpc-pass-file "$R/pass" --blocks "$1" --realtime --threads 4 >>"$R/miner.log" 2>&1; }
abal(){ rpc getassetbalance "[\"$1\",\"$2\"]" | grep -oE '"balance":[0-9]+' | grep -oE '[0-9]+'; }
echo "[$(date +%T)] minando 55 (funda + activación 42)..."; mine 55
echo "  altura=$(num "$(rpc getblockcount)")"
# 1) prize asset
echo "[$(date +%T)] createasset DRAWPZ (fixed, prize pool 1000)..."
COUT=$(CLI createasset DRAWPZ "Draw Prize" 0 fixed 1000 1000 --from-address "$ORG" 2>&1)
AID=$(echo "$COUT" | grep -oE 'asset_id: [0-9a-f]{64}' | grep -oE '[0-9a-f]{64}'); echo "  asset_id=$AID"
mine 3
echo "  prize@organizer=$(abal "$ORG" "$AID") (esp 1000)"
# 2) participants + real on-chain entries (1 SOST each to organizer pool); capture entry txids
declare -a P TXIDS
for k in 0 1 2 3; do
  P[$k]=$(CLI getnewaddress "p$k" 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
done
# fund participants so they can pay the entry
for k in 0 1 2 3; do CLI send "${P[$k]}" 5 --from-address "$ORG" --yes >/dev/null 2>&1; mine 1; done
for k in 0 1 2 3; do echo "  funded p$k bal=$(rpc getbalance "[\"${P[$k]}\"]" | grep -oE '"available":"[0-9.]+"' | grep -oE '[0-9.]+' | head -1)"; done
POOL=$(CLI getnewaddress pool 2>/dev/null | grep -oE 'sost1[0-9a-z]+' | head -1)
echo "  pool=$POOL"
for k in 0 1 2 3; do
  T=$(CLI send "$POOL" 1 --from-address "${P[$k]}" --yes 2>&1 | grep -oE '[0-9a-f]{64}' | head -1)
  TXIDS[$k]="$T"; echo "  entry p$k=${P[$k]} txid=$T"; mine 1
done
# 3) draw_id + close height + entropy
DRAW_ID=$(printf 'SOST-DRAW-1' | sha256sum | cut -c1-64)
CLOSE=$(num "$(rpc getblockcount)"); CLOSE=$((CLOSE+3))
echo "  draw_id=$DRAW_ID  close_height=$CLOSE"
echo "[$(date +%T)] minando hasta close..."; while [ "$(num "$(rpc getblockcount)")" -lt "$CLOSE" ]; do mine 1; done
BH=$(rstr "$(rpc getblockhash "[$CLOSE]")"); echo "  entropy blockhash@$CLOSE=$BH"
# 4) canonical order by entry txid ascending -> ordered participant list
ORDER=$(for k in 0 1 2 3; do echo "${TXIDS[$k]} $k"; done | sort | awk '{print $2}' | tr '\n' ' ')
echo "  canonical order (by txid): $ORDER"
# 5) verifiable winner index (anyone can recompute)
IDX=$("$BIN/sost-cli" drawwinner "$BH" "$DRAW_ID" 4 2>&1 | grep -oE 'draw_winner_index: [0-9]+' | grep -oE '[0-9]+')
IDX2=$("$BIN/sost-cli" drawwinner "$BH" "$DRAW_ID" 4 2>&1 | grep -oE 'draw_winner_index: [0-9]+' | grep -oE '[0-9]+')
WK=$(echo $ORDER | awk -v i=$((IDX+1)) '{print $i}')
WINNER=${P[$WK]}
echo "  winner_index=$IDX (recompute2=$IDX2)  -> participant p$WK = $WINNER"
# 6) real on-chain settlement: organizer transfers prize to the selected winner
echo "[$(date +%T)] settledraw: transfer 1000 DRAWPZ -> winner..."
CLI transferasset "$AID" "$WINNER" 1000 --from-address "$ORG" 2>&1 | grep -E 'txid|node|Error' | sed 's/^/    /'
mine 3
echo "  RESULT: winner($WINNER)=$(abal "$WINNER" "$AID") (esp 1000) · organizer=$(abal "$ORG" "$AID") (esp 0)"
echo "  losers: $(for k in 0 1 2 3; do [ "$k" != "$WK" ] && printf 'p%s=%s ' "$k" "$(abal "${P[$k]}" "$AID")"; done)"
echo "  DETERMINISM: idx==recompute2 ? $([ "$IDX" = "$IDX2" ] && echo YES || echo NO)"
kill -9 $N 2>/dev/null
echo "E2E_DRAW_DONE ROOT_KEPT=$R"
