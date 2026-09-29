#!/usr/bin/env bash
# V16 fresh cutover battery (devnet). Activation N=HIST_JACKPOT_V2_HEIGHT=42 in DEVNET_FAST
# reproduces the mainnet #30000 cutover. Tests: straight N-2..N+2, restart persistence,
# and a reorg ACROSS the activation boundary. Mainnet height/rules untouched.
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO=/home/sost/SOST/sostcore/sost-core; BIN=$REPO/build-sacs; G=$REPO/genesis_block.json
SP=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
ROOT=$SP/v16cut; FEED="$SP/feedchain.py"; N=42
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

echo "############ PART 1 — STRAIGHT CUTOVER (N=$N, verify N-2..N+2) ############"
swset "$ROOT/A"
NA=$(node "$ROOT/A" 19941 19942); wr 19942
mine "$ROOT/A" 19942 $((N+2)); wh 19942 $((N+2)) || echo "  (A stalled at $(h 19942) — CUTOVER STALL!)"
echo "  A height=$(h 19942) (expected $((N+2)))"
echo "  per-block acceptance around activation:"
grep -E "\[BLOCK\] Height (4[0-4]) accepted" "$ROOT/A/node.log" | sed 's/^/     /' | tail -8
echo "  getinfo: $(rpc 19942 getinfo | python3 -c "import json,sys;r=json.load(sys.stdin).get('result',{});print('height',r.get('blocks'),'version',r.get('version'))" 2>/dev/null)"
echo "  jackpot V2 audit @N: $(rpc 19942 getjackpotv2audit "[$N]" | head -c 200)"
echo "  V16 eligibility state: $(rpc 19942 devchainstate 2>/dev/null | head -c 160)"
TA1=$(tip 19942)
echo "############ PART 2 — RESTART PERSISTENCE ############"
kill -9 $NA 2>/dev/null; sw 2; NA=$(node "$ROOT/A" 19941 19942); wr 19942; sw 1
echo "  after restart: h=$(h 19942) tip=$(echo $(tip 19942)|cut -c1-16) stable=$([ "$(tip 19942)" = "$TA1" ] && echo YES || echo NO)"
echo "############ PART 3 — REORG ACROSS ACTIVATION (fork@40, disconnect 3) ############"
# shared prefix 0..40 -> feed to B; A mines 41..43; B mines 41..44 (more work); feed B->A
FP=40
# rewind A is not possible; instead build fresh: A already at 44. Use its blocks 1..40 as shared prefix for B.
swset "$ROOT/B"; NB=$(node "$ROOT/B" 19943 19944); wr 19944
echo "  feed A[1..$FP] -> B (shared prefix)"
python3 "$FEED" 19942 19944 $FP >/dev/null; sw 1
echo "  B height after prefix=$(h 19944) (expect $FP)"
mine "$ROOT/B" 19944 4; wh 19944 $((FP+4))   # B: 41..44 divergent, crosses activation 42
echo "  B height=$(h 19944) tip=$(echo $(tip 19944)|cut -c1-16)  A height=$(h 19942) tip=$(echo $TA1|cut -c1-16)"
echo "  feed B[41..44] -> A : reorg across activation (fork_point $FP, disconnect 3)"
python3 "$FEED" 19944 19942 $((FP+4)) >/dev/null; sw 3
echo "  REORG log (A):"; grep -E "Fork detected|Disconnecting [0-9]+ blocks|Connecting [0-9]+ blocks|Success: new tip|exceeds REORG_LIMIT" "$ROOT/A/node.log" | tail -6 | sed 's/^/     /'
TBtip=$(tip 19944); echo "  A tip now=$(echo $(tip 19942)|cut -c1-16)  B tip=$(echo $TBtip|cut -c1-16)  converged=$([ "$(tip 19942)" = "$TBtip" ] && echo YES || echo NO)"
echo "  A height after reorg=$(h 19942)"
kill -9 $NA 2>/dev/null; sw 1; NA=$(node "$ROOT/A" 19941 19942); wr 19944 2>/dev/null; wr 19942; sw 1
echo "  RESTART A post-reorg: h=$(h 19942) tip=$(echo $(tip 19942)|cut -c1-16) stable=$([ "$(tip 19942)" = "$TBtip" ] && echo YES || echo NO)"
kill -9 $NA $NB 2>/dev/null
echo DONE
