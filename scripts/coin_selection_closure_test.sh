set -u
ulimit -f unlimited
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
B="$S/build-coinsel"; NODE="$B/sost-node"; MINER="$B/sost-miner"; CLI="$B/sost-cli"
RP=18262; PP=20262
W="$(mktemp -d /tmp/closure.XXXXXX)"
cleanup(){ for pid in $(pgrep -f -- "$W" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 8 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
gbal(){ "$CLI" --wallet "$1" --rpc 127.0.0.1:$RP getbalance 2>/dev/null | grep -oE 'Spendable: *[0-9]+\.?[0-9]*' | grep -oE '[0-9]+\.?[0-9]*' | head -1; }

A="$("$CLI" --wallet "$W/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
BB="$("$CLI" --wallet "$W/b.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
echo "A=$A"; echo "B=$BB"

# --- IDENTITY of the node we talk to (per Ángel: verify PID/binary/genesis/port/datadir) ---
"$NODE" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$W/c.json" --port $PP --rpc-port $RP --rpc-noauth --connect 127.0.0.1:1 >"$W/n.log" 2>&1 &
NODEPID=$!
for _ in $(seq 1 20); do sleep 1; [[ -n "$(height $RP)" ]]&&break; done
echo "--- NODE IDENTITY ---"
echo "  launched PID=$NODEPID  chain=$W/c.json  rpc=$RP p2p=$PP profile=dev"
echo "  listener on $RP: $(ss -ltnp 2>/dev/null | grep ":$RP " | grep -oE 'pid=[0-9]+' | head -1)"
echo "  getinfo: $(rpc $RP '{"method":"getinfo","params":[],"id":1}' | head -c 200)"

# --- mine to A (devnet maturity=5) ---
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/a.json" --mining-key-label default --blocks 100000 --threads 3 >>"$W/m.log" 2>&1 & MP=$!
while [[ "$(height $RP)" -lt 15 ]]; do sleep 2; done; kill $MP 2>/dev/null; sleep 2
echo "--- after mining: height=$(height $RP)  A_spendable=$(gbal "$W/a.json") ---"
ABEFORE=$(gbal "$W/a.json")

echo ""
echo "========= CLOSURE SEND (A->B 20, --yes) — FULL OUTPUT ========="
"$CLI" --wallet "$W/a.json" --rpc 127.0.0.1:$RP --yes --skip-warning send "$BB" 20 2>&1 | tee "$W/send.out" | sed 's/^/  /'
echo "=============================================================="
echo ""
echo "--- mempool on the SAME node right after send ---"
rpc $RP '{"method":"getrawmempool","params":[],"id":1}' | sed 's/^/  /'
echo ""
echo "--- mine 2 blocks to confirm ---"
"$MINER" --profile dev --rpc 127.0.0.1:$RP --address "$A" --wallet "$W/a.json" --mining-key-label default --blocks 2 --threads 3 >>"$W/m.log" 2>&1; sleep 2
echo "--- RECONCILIATION ---"
AAFTER=$(gbal "$W/a.json"); BAFTER=$(gbal "$W/b.json")
echo "  A before=$ABEFORE  A after=$AAFTER"
echo "  B after=$BAFTER   (expected ~20)"
echo "  height=$(height $RP)"
# extract accepted txid from output and verify on-chain
TXID=$(grep -oiE 'accepted by node! Txid: [a-f0-9]+' "$W/send.out" | grep -oE '[a-f0-9]{16,}')
echo "  accepted txid=$TXID"
[ -n "$TXID" ] && rpc $RP "{\"method\":\"getrawtransaction\",\"params\":[\"$TXID\"],\"id\":1}" | head -c 160 | sed 's/^/  gettx: /'
echo ""
