#!/usr/bin/env bash
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO=/home/sost/SOST/sostcore/sost-core; BIN=$REPO/build-sacs; G=$REPO/genesis_block.json
SP=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
ROOT=$SP/v16reorg; FEED="$SP/feedchain.py"; N=42; FP=40
rm -rf "$ROOT"; mkdir -p "$ROOT/A" "$ROOT/B"
rpc(){ curl -s --max-time 8 -u u:p -H 'Content-Type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$2\",\"params\":${3:-[]}}" http://127.0.0.1:$1/ 2>/dev/null; }
h(){ rpc $1 getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
tip(){ rpc $1 getbestblockhash | grep -oE '"result":"[0-9a-f]+"' | grep -oE '[0-9a-f]{16,}' | head -1; }
sw(){ ( sleep "$1" ) & wait $!; }
swset(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
node(){ printf p>"$1/pass"; chmod 600 "$1/pass"; nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --port $2 --rpc-port $3 --rpc-user u --rpc-pass-file "$1/pass" >> "$1/node.log" 2>&1 & echo $!; }
mine(){ nice -n 19 timeout 300 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 3 >> "$1/miner.log" 2>&1; }
wr(){ for i in $(seq 1 60); do [ -n "$(h $1)" ] && return 0; sw 0.5; done; }
wh(){ for i in $(seq 1 240); do [ "$(h $1)" = "$2" ] && return 0; sw 0.5; done; }
swset "$ROOT/A"; NA=$(node "$ROOT/A" 19941 19942); wr 19942
mine "$ROOT/A" 19942 44; wh 19942 44
TA=$(tip 19942); echo "A mined to h=$(h 19942) tip=$(echo $TA|cut -c1-16) (crossed activation $N)"
swset "$ROOT/B"; NB=$(node "$ROOT/B" 19943 19944); wr 19944
python3 "$FEED" 19942 19944 $FP >/dev/null; sw 1
echo "B shared prefix h=$(h 19944) (expect $FP)"
mine "$ROOT/B" 19944 5; wh 19944 $((FP+5))    # B -> 45 (more work than A's 44)
TB=$(tip 19944); echo "B mined divergent to h=$(h 19944) tip=$(echo $TB|cut -c1-16)"
echo ">>> feed B[41..45] -> A : reorg ACROSS activation (fork_point $FP, disconnect 4, connect 5)"
python3 "$FEED" 19944 19942 $((FP+5)) >/dev/null; sw 3
echo "REORG log (A):"; grep -E "Fork detected at height|Disconnecting [0-9]+ blocks|Connecting [0-9]+ blocks|Success: new tip|exceeds REORG_LIMIT" "$ROOT/A/node.log" | tail -6 | sed 's/^/   /'
echo "A after: h=$(h 19942) tip=$(echo $(tip 19942)|cut -c1-16)  ==B? $([ "$(tip 19942)" = "$TB" ] && echo YES-CONVERGED || echo NO)"
echo "jackpot V2 audit @$N on A (post-reorg): $(rpc 19942 getjackpotv2audit "[$N]" | grep -oE '"is_v2_jackpot":(true|false),"activation_height":[0-9]+')"
kill -9 $NA 2>/dev/null; sw 1; NA=$(node "$ROOT/A" 19941 19942); wr 19942; sw 1
echo "RESTART A: h=$(h 19942) tip=$(echo $(tip 19942)|cut -c1-16) stable=$([ "$(tip 19942)" = "$TB" ] && echo YES || echo NO)"
kill -9 $NA $NB 2>/dev/null; echo DONE
