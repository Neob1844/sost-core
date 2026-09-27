set -u
ulimit -f unlimited
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
B="$S/build-durable"; NODE="$B/sost-node"; MINER="$B/sost-miner"; CLI="$B/sost-cli"
RP=18282; PP=20282
W="$(mktemp -d /tmp/savefail.XXXXXX)"
DDIR="$W/chaindir"; mkdir -p "$DDIR"; CHAIN="$DDIR/chain.json"
cleanup(){ chmod 700 "$DDIR" 2>/dev/null; for pid in $(pgrep -f -- "$W" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 8 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
gbt(){ rpc "$1" '{"method":"getblocktemplate","params":["'"$2"'"],"id":1}'; }
A="$("$CLI" --wallet "$W/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"

"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$CHAIN" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >"$W/n.log" 2>&1 & N=$!
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height $RP)" ]]&&break; done
echo "node up h=$(height $RP)"
# mine a few blocks NORMALLY -> getblocktemplate must work
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/a.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/m.log" 2>&1 & MP=$!
while [[ "$(height $RP)" -lt 6 ]]; do sleep 2; done; kill $MP 2>/dev/null; sleep 1
echo "normal mining OK, h=$(height $RP)"
echo "gbt(normal) => $(gbt $RP "$A" | grep -oE '"(result|error)"' | head -1)"

echo ""
echo "=== INDUCE SAVE FAILURE: chmod chaindir read-only (0500) ==="
chmod 500 "$DDIR"
# each mined block triggers a save (now failing). Mine a few more so >=3 consecutive failures accrue.
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/a.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/m2.log" 2>&1 & MP2=$!
sleep 12; kill $MP2 2>/dev/null; sleep 1
echo "save failures logged in node: $(grep -c 'auto-save failed' "$W/n.log") ; last:"
grep 'auto-save failed' "$W/n.log" | tail -2 | sed 's/^/    /'
echo "gbt(after failures) => $(gbt $RP "$A" | grep -oE 'mining halted[^"]*|"error"|"result"' | head -1)"
GBT_ERR=$(gbt $RP "$A")
echo "$GBT_ERR" | grep -q 'mining halted' && echo "  ✅ getblocktemplate HALTED with -10 as designed" || echo "  ⚠️ not halted: $(echo "$GBT_ERR"|head -c 120)"

echo ""
echo "=== RECOVER: chmod back to writable, next save should reset counter ==="
chmod 700 "$DDIR"
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/a.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/m3.log" 2>&1 & MP3=$!
# but mining is halted; getblocktemplate -10 means miner can't build. The PERIODIC main-loop save (30s) will reset. Wait for it.
for _ in $(seq 1 40); do
  R=$(gbt $RP "$A")
  echo "$R" | grep -q '"result"' && { echo "  ✅ recovered: getblocktemplate serves templates again"; break; }
  sleep 3
done
kill $MP3 2>/dev/null
FINAL=$(gbt $RP "$A")
echo "$FINAL" | grep -q '"result"' && echo "RESULT: ✅ save-failure policy works (halt on disk failure, resume on recovery)" || echo "RESULT: ⚠️ still halted after recovery: $(echo "$FINAL"|head -c 120)"
kill -TERM $N 2>/dev/null; sleep 1
