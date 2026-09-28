#!/usr/bin/env bash
# SACS P7 — adversarial / DoS resistance of the read-only SACS RPC + monitor.
# Malformed & injection params, high-rate load, concurrency; confirm no crash,
# bounded responses, node stays alive, RSS stable. Uses ports 199 6x to avoid P3.
ulimit -f unlimited 2>/dev/null
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"; BIN="${BIN:-$REPO/build-sacs}"; G=$REPO/genesis_block.json
ROOT="$(mktemp -d)"; FEED="$(cd "$(dirname "$0")" && pwd)/sacs_feedchain.py"; RP=19962
trap 'rm -rf "$ROOT"' EXIT
rq(){ curl -s --max-time 8 -u u:p -H 'Content-Type: application/json' --data "$1" http://127.0.0.1:$RP/ 2>/dev/null; }
rpc(){ rq "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}"; }
h(){ rpc getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1; }
softwait(){ ( sleep "$1" ) & wait $!; }
sw(){ "$BIN/sost-cli" newwallet --wallet "$1/w.json" >/dev/null 2>&1; "$BIN/sost-cli" getnewaddress m --wallet "$1/w.json" >/dev/null 2>&1; }
mine(){ nice -n 19 timeout 200 "$BIN/sost-miner" --profile dev --genesis "$G" --chain "$1/chain.json" --wallet "$1/w.json" --mining-key-label m --rpc 127.0.0.1:$2 --rpc-user u --rpc-pass-file "$1/pass" --blocks "$3" --realtime --threads 3 >> "$1/miner.log" 2>&1; }
rss(){ ps -o rss= -p "$1" 2>/dev/null | tr -d ' '; }

rm -rf "$ROOT"; mkdir -p "$ROOT/A" "$ROOT/B"; printf p>"$ROOT/A/pass"; printf p>"$ROOT/B/pass"; chmod 600 "$ROOT/A/pass" "$ROOT/B/pass"
sw "$ROOT/A"; sw "$ROOT/B"
# A = 9 blocks, B = 8; feed A->B to generate a real reorg (populate SACS events)
nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$ROOT/A/chain.json" --wallet "$ROOT/A/w.json" --port 19961 --rpc-port 19960 --rpc-user u --rpc-pass-file "$ROOT/A/pass" >>"$ROOT/A/node.log" 2>&1 &
NA=$!
nice -n 19 "$BIN/sost-node" --profile dev --noseed --genesis "$G" --chain "$ROOT/B/chain.json" --wallet "$ROOT/B/w.json" --port 19963 --rpc-port $RP --rpc-user u --rpc-pass-file "$ROOT/B/pass" >>"$ROOT/B/node.log" 2>&1 &
NB=$!
for i in $(seq 1 60); do [ -n "$(h)" ] && [ -n "$(curl -s --max-time 3 -u u:p -H 'Content-Type: application/json' --data '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}' http://127.0.0.1:19960/ | grep -oE '[0-9]+')" ] && break; softwait 0.5; done
mine "$ROOT/A" 19960 9
mine "$ROOT/B" $RP 8
python3 "$FEED" 19960 $RP 9 >/dev/null; softwait 2
echo "B height=$(h) ; SACS events populated:"
rpc getsacsstatus | python3 -c "import json,sys;print('  counts=',json.load(sys.stdin)['result']['counts'])" 2>/dev/null

RSS0=$(rss $NB)
echo; echo "===== 1) MALFORMED / INJECTION RPC (must never crash) ====="
declare -a BAD=(
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":[-1]}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":[999999999999999999999999]}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":["abc","xyz"]}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":["0; DROP TABLE",-5]}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":[0,-1]}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":[0,99999999]}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":['"$(python3 -c 'print("9"*5000)')"']}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents","params":["'"$(python3 -c 'print("A"*20000)')"'"]}'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsstatus","params":["unexpected","extra","args"]}'
 'not even json'
 '{"jsonrpc":"2.0","id":1,"method":"getsacsevents"}'
)
N=0; CRASH=0
for b in "${BAD[@]}"; do
  R=$(rq "$b"); N=$((N+1))
  if [ -z "$R" ]; then echo "  [$N] EMPTY RESPONSE (node may have died!)"; CRASH=1
  else echo "  [$N] ok len=${#R} -> $(echo "$R" | cut -c1-80)"; fi
done
echo "  node alive after malformed barrage: $([ -n "$(h)" ] && echo YES || echo NO)"

echo; echo "===== 2) HUGE-LIMIT response is CLAMPED (cannot be forced unbounded) ====="
BIG=$(rpc getsacsevents '[0,100000000]'); echo "  returned=$(echo "$BIG" | grep -oE '"returned":[0-9]+') len=${#BIG} (bounded)"

echo; echo "===== 3) HIGH-RATE LOAD (2000 calls) ====="
T0=$(date +%s%N)
for i in $(seq 1 2000); do rpc getsacsstatus >/dev/null; done
T1=$(date +%s%N)
echo "  2000 sequential getsacsstatus in $(( (T1-T0)/1000000 )) ms ; node alive=$([ -n "$(h)" ] && echo YES || echo NO)"

echo; echo "===== 4) CONCURRENCY STORM (8 parallel x 300) ====="
for w in $(seq 1 8); do ( for i in $(seq 1 300); do rpc getsacsevents '[0,50]' >/dev/null; done ) & done
wait
echo "  concurrency storm done ; node alive=$([ -n "$(h)" ] && echo YES || echo NO)"

RSS1=$(rss $NB)
echo; echo "===== RSS (RESIDENT MEMORY) before/after DoS ====="
echo "  RSS before=${RSS0}KB  after=${RSS1}KB  delta=$(( ${RSS1:-0} - ${RSS0:-0} ))KB (ring is fixed 512-cap; must not grow unbounded)"
echo "  SACS ring size (must be <= 512): $(rpc getsacsstatus | grep -oE '"ring_size":[0-9]+')"
kill -9 $NA $NB 2>/dev/null
echo ALLDONE
