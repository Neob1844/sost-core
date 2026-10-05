#!/usr/bin/env bash
set -uo pipefail
OLD=/home/sost/SOST/sostcore/lab-old-v30000/build-devnet
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
LAB=$(mktemp -d /tmp/sostlab.XXXXXX)
PASS=0; FAIL=0; PIDS=()
ok(){ echo "  PASS  $*"; PASS=$((PASS+1)); }
bad(){ echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
cleanup(){ for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null; done; wait 2>/dev/null; true; }
trap cleanup EXIT
rpc(){ curl -s --max-time 8 -H 'content-type: application/json' --data "{\"method\":\"$2\",\"params\":${3:-[]},\"id\":1}" "http://127.0.0.1:$1/"; }
height(){ rpc "$1" getblockcount | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+'; }
tiphash(){ rpc "$1" getbestblockhash | grep -oE '[a-f0-9]{64}' | head -1; }
npeers(){ rpc "$1" getpeerinfo | grep -oE '"addr"' | wc -l; }
cnt(){ local n; n=$(grep -c "$2" "$1" 2>/dev/null); echo "${n:-0}"; }
# role id p2pport rpcport bindip connect...
start(){ local role=$1 id=$2 pp=$3 rp=$4 ip=$5; shift 5
  local bin="$OLD/sost-node"; [[ $role == NEW ]] && bin="$NEW/sost-node"
  local dd="$LAB/$role$id"; mkdir -p "$dd"
  local a=(--profile dev --genesis "$GEN" --chain "$dd/chain.json" --port "$pp" --rpc-port "$rp" --rpc-noauth)
  [[ $role == NEW && -n $ip ]] && a+=(--p2p-bind "$ip")
  if [[ $# -eq 0 ]]; then a+=(--connect 127.0.0.1:1); else for c in "$@"; do a+=(--connect "$c"); done; fi
  "$bin" "${a[@]}" >"$dd/node.log" 2>&1 & echo $!; }
echo "=== LAB $LAB  OLD=$(sha256sum $OLD/sost-node|cut -c1-10) NEW=$(sha256sum $NEW/sost-node|cut -c1-10) ==="
PO1=$(start OLD 1 20401 20402 "");             PIDS+=($PO1); sleep 2
PO2=$(start OLD 2 20403 20404 "" 127.0.0.1:20401); PIDS+=($PO2)
PN1=$(start NEW 1 20405 20406 127.0.0.5 127.0.0.1:20401); PIDS+=($PN1); sleep 2
PN2=$(start NEW 2 20407 20408 127.0.0.7 127.0.0.5:20405); PIDS+=($PN2)
PN3=$(start NEW 3 20409 20410 127.0.0.9 127.0.0.5:20405); PIDS+=($PN3)
DO1=$LAB/OLD1 DO2=$LAB/OLD2 DN1=$LAB/NEW1 DN2=$LAB/NEW2 DN3=$LAB/NEW3
echo "--- settle (up to 40s) ---"
for t in $(seq 1 20); do sleep 2; ac=1; for rp in 20402 20404 20406 20408 20410; do [[ "$(npeers $rp)" -ge 1 ]] || ac=0; done; [[ $ac -eq 1 ]] && break; done
for rp in 20402 20404 20406 20408 20410; do echo "  rpc$rp peers=$(npeers $rp) h=$(height $rp)"; done
ac=1; for rp in 20402 20404 20406 20408 20410; do [[ "$(npeers $rp)" -ge 1 ]] || ac=0; done
[[ $ac -eq 1 ]] && ok "full mesh (all 5 nodes >=1 peer, incl NEW2 self-heal)" || bad "a node has 0 peers"
ub=$(( $(cnt "$DO1/node.log" "unknown command") + $(cnt "$DO2/node.log" "unknown command") ))
[[ $ub -eq 0 ]] && ok "capability negotiation: 0 'unknown command' on OLD" || bad "OLD penalized unknown cmd ($ub)"
served=$(( $(cnt "$DN1/node.log" "served ADDR")+$(cnt "$DN2/node.log" "served ADDR")+$(cnt "$DN3/node.log" "served ADDR") ))
recv=$(( $(cnt "$DN1/node.log" "received ADDR")+$(cnt "$DN2/node.log" "received ADDR")+$(cnt "$DN3/node.log" "received ADDR") ))
gadr=$(( $(cnt "$DN1/node.log" "sent GADR")+$(cnt "$DN2/node.log" "sent GADR")+$(cnt "$DN3/node.log" "sent GADR") ))
echo "  GADR sent=$gadr  ADDR served=$served received=$recv"
[[ $gadr -ge 1 && $served -ge 1 && $recv -ge 1 ]] && ok "ADDR gossip exchanged (GADR+served+received)" || bad "no ADDR gossip"
MA=$("$OLD/sost-cli" --wallet "$LAB/mw.json" newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)
"$OLD/sost-miner" --profile dev --rpc 127.0.0.1:20402 --address "$MA" --wallet "$LAB/mw.json" --mining-key-label default --blocks 8 --threads 3 >"$LAB/miner.log" 2>&1 & MP=$!; PIDS+=($MP)
for _ in $(seq 1 60); do [[ "$(height 20402)" -ge 8 ]] 2>/dev/null && break; sleep 2; done; kill $MP 2>/dev/null; sleep 8
H1=$(height 20402); ref="$H1:$(tiphash 20402)"; sa=1
for rp in 20404 20406 20408 20410; do r="$(height $rp):$(tiphash $rp)"; echo "  rpc$rp=$r"; [[ "$r" == "$ref" ]] || sa=0; done
[[ $sa -eq 1 && "${H1:-0}" -ge 8 ]] && ok "block propagation: all 5 same height+tip" || bad "divergence ref=$ref"
echo "--- gossip functional: kill NEW1; NEW3 must survive via gossiped candidate ---"
kill $PN1 2>/dev/null; sleep 40
n3=$(npeers 20410); echo "  NEW3 peers after NEW1 death=$n3"; grep -E "Peer connected: 127.0.0.1:20401|reconnect" "$DN3/node.log" | tail -2 | sed 's/^/    /'
[[ "$n3" -ge 1 ]] && ok "NEW3 survived loss of its only --connect via gossiped/stored candidate" || bad "NEW3 isolated"
echo "=== PHASE 1: $PASS passed, $FAIL failed ==="; echo "LAB_DIR=$LAB"
