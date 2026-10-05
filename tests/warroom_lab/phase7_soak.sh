#!/usr/bin/env bash
set -uo pipefail
OLD=/home/sost/SOST/sostcore/lab-old-v30000/build-devnet
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
LAB=/home/sost/SOST/sostcore/lab/soak_run; rm -rf "$LAB"; mkdir -p "$LAB"
MET="$LAB/metrics.csv"; echo "ts,node,rss_kb,fd,peers,peerstore,candidates_log,tip,errors" > "$MET"
PIDS=()
cleanup(){ for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null; done; wait 2>/dev/null; true; }
trap cleanup EXIT
rpc(){ curl -s --max-time 5 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":[],\"id\":1}" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" getblockcount | grep -oE '[0-9]+' | head -1; }
tiphash(){ rpc "$1" getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1; }
npeers(){ rpc "$1" getpeerinfo | grep -oE '"addr"' | wc -l; }
start(){ local role=$1 id=$2 pp=$3 rp=$4 ip=$5; shift 5
  local bin="$OLD/sost-node"; [[ $role == NEW ]] && bin="$NEW/sost-node"
  local dd="$LAB/$role$id"; mkdir -p "$dd"
  local a=(--profile dev --genesis "$GEN" --chain "$dd/chain.json" --port "$pp" --rpc-port "$rp" --rpc-noauth)
  [[ $role == NEW ]] && a+=(--p2p-bind "$ip")
  if [[ $# -eq 0 ]]; then a+=(--connect 127.0.0.1:1); else for c in "$@"; do a+=(--connect "$c"); done; fi
  "$bin" "${a[@]}" >"$dd/node.log" 2>&1 & echo $!; }
# 4-node mixed mesh
PO=$(start OLD 1 20601 20602 "");               PIDS+=($PO); sleep 2
PN1=$(start NEW 1 20603 20604 127.0.0.30 127.0.0.1:20601); PIDS+=($PN1); sleep 1
PN2=$(start NEW 2 20605 20606 127.0.0.31 127.0.0.30:20603); PIDS+=($PN2)
PO2=$(start OLD 2 20607 20608 "" 127.0.0.30:20603); PIDS+=($PO2)
sleep 8
MA=$("$NEW/sost-cli" --wallet "$LAB/w.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+'|head -1)
# continuous light miner on NEW1
"$NEW/sost-miner" --profile dev --rpc 127.0.0.1:20604 --address "$MA" --wallet "$LAB/w.json" --mining-key-label default --blocks 1000000 --threads 2 >"$LAB/miner.log" 2>&1 & PIDS+=($!)
declare -A RP=( [OLD1]=20602 [NEW1]=20604 [NEW2]=20606 [OLD2]=20608 )
declare -A PID=( [OLD1]=$PO [NEW1]=$PN1 [NEW2]=$PN2 [OLD2]=$PO2 )
declare -A DIR=( [OLD1]=$LAB/OLD1 [NEW1]=$LAB/NEW1 [NEW2]=$LAB/NEW2 [OLD2]=$LAB/OLD2 )
sample(){ local now=$(date -u +%H:%M:%S)
  for n in OLD1 NEW1 NEW2 OLD2; do local pid=${PID[$n]} rp=${RP[$n]} d=${DIR[$n]}
    local rss=$(awk '/VmRSS/{print $2}' /proc/$pid/status 2>/dev/null); local fd=$(ls /proc/$pid/fd 2>/dev/null|wc -l)
    local pk=$([[ -f $d/peers.txt ]] && wc -l <$d/peers.txt || echo 0)
    local cand=$(grep -c "received ADDR" $d/node.log 2>/dev/null); local errs=$(grep -ciE "error|crash|abort|exception|bad_alloc" $d/node.log 2>/dev/null)
    echo "$now,$n,${rss:-0},${fd:-0},$(npeers $rp),$pk,${cand:-0},$(tiphash $rp|cut -c1-10),${errs:-0}" >> "$MET"
  done; }
# run for a long time: sample every 60s. External watcher (claude) checks metrics.csv.
echo "SOAK STARTED pids=${PIDS[*]}" > "$LAB/status.txt"
for i in $(seq 1 1440); do sample; sleep 60; done   # up to 24h
