#!/usr/bin/env bash
set -uo pipefail
NEW=/home/sost/SOST/sostcore/d1-p2p-autonomy/build-devnet
GEN=/home/sost/SOST/sostcore/d1-p2p-autonomy/genesis_block.json
L=$(mktemp -d /tmp/rpcadv.XXXXXX); PIDS=()
trap 'for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null; done' EXIT
"$NEW/sost-node" --profile dev --genesis "$GEN" --chain "$L/c.json" --port 21301 --rpc-port 21302 --rpc-noauth --connect 127.0.0.1:1 >"$L/n.log" 2>&1 & PIDS+=($!)
for _ in $(seq 1 15); do curl -s --max-time 2 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:21302/ >/dev/null 2>&1 && break; sleep 1; done
P=21302; pass=0; fail=0
hit(){ curl -s --max-time 4 -H 'content-type: application/json' --data "$1" http://127.0.0.1:$P/ >/dev/null 2>&1; }
alive(){ curl -s --max-time 4 -H 'content-type: application/json' --data '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:$P/ 2>/dev/null | grep -qE '"result"' && return 0 || return 1; }
# SEC2 known vectors + extra malformed
VEC=(
'{"method":"getblockhash","params":["notanumber"],"id":1}'
'{"method":"getblockhash","params":[999999999999999999999],"id":1}'
'{"method":"getblock","params":[[[[[1]]]]],"id":1}'
'{"method":"getblock","params":[{"a":{"b":{"c":{"d":{}}}}}],"id":1}'
'{"method":"getrawtransaction","params":["../../etc/passwd"],"id":1}'
'not even json at all }{'
'{"method":"'"$(head -c 20000 </dev/zero | tr "\0" A)"'","params":[],"id":1}'
'{"method":"getblockhash","params":[-1],"id":1}'
'{"jsonrpc":"2.0","method":"getblock","params":null,"id":1}'
'{"method":"getpeerinfo","params":[1,2,3,4,5,6,7,8,9,10],"id":1}'
)
for i in "${!VEC[@]}"; do hit "${VEC[$i]}"; alive && { echo "  PASS vec$i: node alive after malformed RPC"; pass=$((pass+1)); } || { echo "  FAIL vec$i: node unresponsive"; fail=$((fail+1)); }; done
# flood: 500 rapid malformed
for _ in $(seq 1 500); do curl -s --max-time 1 -H 'content-type: application/json' --data '{"method":"getblock","params":[[[[1]]]],"id":1}' http://127.0.0.1:$P/ >/dev/null 2>&1; done
alive && { echo "  PASS flood: node alive after 500 malformed"; pass=$((pass+1)); } || { echo "  FAIL flood"; fail=$((fail+1)); }
echo "crashes en log: $(grep -ciE 'abort|segfault|terminate|bad_alloc|sanitizer' "$L/n.log" 2>/dev/null)"
echo "RPC ADVERSARIAL: $pass passed, $fail failed"
