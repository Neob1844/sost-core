set -u
ulimit -f unlimited
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
NODE="$S/build-peers/sost-node"
W="$(mktemp -d /tmp/peers.XXXXXX)"
APID=""; BPID=""
cleanup(){ [ -n "$BPID" ] && kill -9 "$BPID" 2>/dev/null; [ -n "$APID" ] && kill -9 "$APID" 2>/dev/null; for p in $(pgrep -f -- "$W" 2>/dev/null); do kill -9 "$p" 2>/dev/null; done; }
trap cleanup EXIT
rpc(){ curl -s --max-time 6 --data "$2" "http://127.0.0.1:$1/"; }
conns(){ rpc "$1" '{"method":"getinfo","params":[],"id":1}' | grep -oE '"connections":[0-9]+' | grep -oE '[0-9]+'; }
up(){ for _ in $(seq 1 40); do sleep 1; [ -n "$(rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '[0-9]+'|tail -1)" ] && return 0; done; return 1; }

# Node A = the "seed" peer on p2p 20310
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/a.json" --port 20310 --rpc-port 18310 --rpc-noauth --connect 127.0.0.1:1 >"$W/a.log" 2>&1 & APID=$!
up 18310 || { echo "A failed"; exit 1; }
echo "Node A up (p2p 20310)"

# Node B connects to A explicitly the FIRST time
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/b.json" --port 20311 --rpc-port 18311 --rpc-noauth --connect 127.0.0.1:20310 >"$W/b1.log" 2>&1 & BPID=$!
up 18311 || { echo "B failed"; exit 1; }
sleep 4
echo "Node B up, --connect 127.0.0.1:20310 ; B connections=$(conns 18311)"
echo "--- B peers.json after first connect ---"
BPEERS="$W/peers.json"   # chain is $W/b.json -> peers.json alongside in $W
cat "$BPEERS" 2>/dev/null | sed 's/^/  /'
grep -q '127.0.0.1:20310' "$BPEERS" 2>/dev/null && echo "  ✅ B persisted A (127.0.0.1:20310)" || echo "  ❌ not persisted"

echo "--- stop B, restart with NO --connect (must redial from peers.json) ---"
kill -9 "$BPID" 2>/dev/null; BPID=""; sleep 5
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/b.json" --port 20311 --rpc-port 18311 --rpc-noauth --connect 127.0.0.1:1 >"$W/b2.log" 2>&1 & BPID=$!
up 18311 || { echo "B restart failed"; exit 1; }
# wait for the startup redial to connect
RECON=0
for _ in $(seq 1 15); do sleep 2; c=$(conns 18311); [ "${c:-0}" -ge 1 ] && { RECON=1; break; }; done
echo "  B redial log: $(grep -i 'remembered peer' "$W/b2.log" | head -1)"
echo "  B connections after restart (no --connect) = $(conns 18311)"
if [ "$RECON" = "1" ]; then
  echo "RESULT: ✅ PEER PERSISTENCE — B reconnected to A from peers.json WITHOUT --connect or seeds (bootstrap independent of STRATO)"
else
  echo "RESULT: ⚠️ B did not reconnect (conns=$(conns 18311))"; tail -6 "$W/b2.log"|sed 's/^/    /'
fi
