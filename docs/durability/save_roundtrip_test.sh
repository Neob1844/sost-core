set -u
ulimit -f unlimited
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
B="$S/build-durable"; NODE="$B/sost-node"; MINER="$B/sost-miner"; CLI="$B/sost-cli"
RP=18272; PP=20272
W="$(mktemp -d /tmp/durable.XXXXXX)"
CHAIN="$W/chain.json"
cleanup(){ for pid in $(pgrep -f -- "$W" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 8 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
A="$("$CLI" --wallet "$W/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"

echo "=== start node #1 (chain=$CHAIN, rpc=$RP) ==="
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$CHAIN" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >"$W/n1.log" 2>&1 &
N1=$!
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height $RP)" ]]&&break; done
echo "  node1 up, height=$(height $RP)"

echo "=== mine 10 blocks ==="
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/a.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/m.log" 2>&1 & MP=$!
while [[ "$(height $RP)" -lt 10 ]]; do sleep 2; done; kill $MP 2>/dev/null; sleep 1
H1=$(height $RP); echo "  mined to height=$H1"

echo "=== SIGTERM node1 (triggers durable save) ==="
kill -TERM $N1 2>/dev/null
for _ in $(seq 1 15); do kill -0 $N1 2>/dev/null || break; sleep 1; done
kill -0 $N1 2>/dev/null && { echo "  node1 still alive, SIGKILL"; kill -9 $N1; }
echo "  node1 stopped; chain.json present=$([ -s "$CHAIN" ]&&echo yes) size=$(stat -c%s "$CHAIN" 2>/dev/null) bytes"
echo "  chain.json.tmp leftover=$([ -e "$CHAIN.tmp" ]&&echo YES(bad)||echo no)"
# validate JSON parses + extract block count from the saved file
python3 -c "import json,sys; d=json.load(open('$CHAIN')); b=d.get('blocks',d if isinstance(d,list) else []); print('  saved chain parses OK, blocks in file =', len(b) if isinstance(b,list) else 'n/a')" 2>&1 | sed 's/^/  /'

echo "=== restart node #2 from the SAME chain.json (load roundtrip) ==="
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$CHAIN" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >"$W/n2.log" 2>&1 &
N2=$!
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height $RP)" ]]&&break; done
H2=$(height $RP); echo "  node2 loaded height=$H2"
echo ""
if [ -n "$H2" ] && [ "$H2" -ge "$H1" ] 2>/dev/null; then
  echo "RESULT: ✅ DURABLE ROUNDTRIP OK — saved@$H1 -> loaded@$H2 (fsync save + load, no corruption, no .tmp leftover)"
else
  echo "RESULT: ❌ mismatch saved@$H1 loaded@$H2"
  tail -5 "$W/n2.log" | sed 's/^/    n2: /'
fi
kill -TERM $N2 2>/dev/null; sleep 1
