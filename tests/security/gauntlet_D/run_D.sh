#!/usr/bin/env bash
# Gauntlet D — mass adversarial lab (SIMULATED peers, not real nodes) + honest-peer convergence under noise.
set -u
ROOT=/home/sost/SOST/sostcore/sost-core
S=/tmp/claude-1001/-home-sost-SOST-sostcore-sost-core/b88ec304-d8fa-4665-8e3f-69bca45fb9f9/scratchpad
DIR="$S/gauntlet-D"
BIN="${GD_BIN:-$S/build-comb-dev/sost-node}"; MINER="$S/build-comb-dev/sost-miner"; CLI="$S/build-comb-dev/sost-cli"
N="${1:-200}"; DUR="${2:-60}"
WORK="$(mktemp -d /tmp/gd.XXXXXX)"
cleanup(){ for pid in $(pgrep -f -- "$WORK" 2>/dev/null); do [[ "$pid" == "$$" ]]&&continue; kill "$pid" 2>/dev/null; done; wait 2>/dev/null; }
trap cleanup EXIT
rpc(){ curl -s --max-time 6 --data "$2" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" '{"method":"getblockcount","params":[],"id":1}'|grep -oE '"result":[0-9]+'|grep -oE '[0-9]+'; }
tip(){ rpc "$1" '{"method":"getbestblockhash","params":[],"id":1}'|grep -oE '[a-f0-9]{64}'|head -1; }
npeers(){ rpc "$1" '{"method":"getpeerinfo","params":[],"id":1}'|grep -oc '"addr"'; }
sn(){ "$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$1" --port "$2" --rpc-port "$3" --rpc-noauth --connect "${5:-127.0.0.1:1}" >>"$WORK/$4.log" 2>&1 & for _ in $(seq 1 30); do sleep 1; [[ -n "$(height "$3")" ]]&&return; done; echo boot-fail; }
stopc(){ for pid in $(pgrep -f -- "$1" 2>/dev/null); do kill $pid 2>/dev/null; done; sleep 2; }
mineto(){ "$MINER" --profile dev --rpc "127.0.0.1:$1" --address "$2" --wallet "$3" --mining-key-label default --blocks 100000 --threads 3 >>"$WORK/m.log" 2>&1 & local mp=$!; while [[ "$(height "$1")" -lt "$4" ]]; do sleep 2; done; kill $mp 2>/dev/null; sleep 1; }
A="$("$CLI" --wallet "$WORK/a.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
B="$("$CLI" --wallet "$WORK/b.json" newwallet 2>&1|grep -oE 'sost1[a-z0-9]+'|head -1)"
# victim V -> 15 ; honest B -> 20 (divergent)
sn "$WORK/v.json" 20100 18100 V; mineto 18100 "$A" "$WORK/a.json" 15; stopc "$WORK/v.json"
sn "$WORK/b.json" 20102 18102 Bn; mineto 18102 "$B" "$WORK/b.json" 20
BT="$(tip 18102)"; echo "[D] honest B @h=$(height 18102) tip=${BT:0:16}"
# restart V dialing B, capture PID
"$BIN" --profile dev --genesis "$ROOT/genesis_block.json" --chain "$WORK/v.json" --port 20100 --rpc-port 18100 --rpc-noauth --connect 127.0.0.1:20102 >>"$WORK/V.log" 2>&1 & VPID=$!
for _ in $(seq 1 30); do sleep 1; [[ -n "$(height 18100)" ]]&&break; done
GEN=$(grep -oE 'Genesis: [0-9a-f]{64}' "$WORK/V.log" | head -1 | awk '{print $2}')
echo "[D] victim V pid=$VPID @h=$(height 18100), honest peer + launching $N sim-peers for ${DUR}s"
python3 "$DIR/mass_lab.py" 20100 18100 "$GEN" "$VPID" "$N" "$DUR"
echo "[D] === post-tormenta ==="
sleep 3
VH=$(height 18100); VT=$(tip 18100); alive=$([ -n "$VH" ]&&echo sí||echo NO)
echo "[D] victim: alive=$alive height=$VH tip=${VT:0:16} peers=$(npeers 18100)"
echo "[D] honest B: alive=$([ -n "$(height 18102)" ]&&echo sí||echo NO) height=$(height 18102)"
conv=$([ "$VT" == "$BT" ]&&[ "$VH" == "20" ]&&echo "SÍ (converged a B h20 bajo ataque)"||echo "no ($VH)")
echo "[D] convergencia bajo ruido: $conv"
echo "[D] fork-store/known del victim (máximos en log):"
echo "    orphans max: $(grep -oE '[0-9]+ orphans total' "$WORK/V.log"|grep -oE '^[0-9]+'|sort -n|tail -1 || echo 0) (cap 200)"
echo "    crashes: $(grep -ciE 'Segmentation|Aborted|terminate|core dumped|bad_alloc' "$WORK/V.log") "
echo "    misbehavior/bans a peers honestos (127.0.0.1:20102): $(grep -c '20102.*[Mm]isbehav\|[Bb]an.*20102' "$WORK/V.log")"
echo "work=$WORK"
