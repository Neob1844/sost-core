#!/usr/bin/env bash
# Deterministic orphan dead-end repro. A synthetic plaintext peer serves blocks 1..5 of a
# DEVNET chain.json fixture in a chosen order. v16.3.0: order 1,3,2,4,5 stops at height 2.
# Env: BUILD (DEVNET build dir), FIXTURE (a DEVNET chain.json with >= 5 blocks), GENESIS.
set -u
B="${BUILD:?}"; FX="${FIXTURE:?}"; HERE="$(cd "$(dirname "$0")" && pwd)"
G="${GENESIS:-$HERE/../../genesis_block.json}"; W="$(mktemp -d)"
case_run(){ rm -f $W/$1.json
  python3 "$HERE/orphan_peer.py" "$FX" 19981 5 "$2" ${3:+"$3"} > $W/$1.peer.log 2>&1 & PP=$!; sleep 0.5
  "$B/sost-node" --profile dev --genesis "$G" --chain $W/$1.json --port 19982 --rpc-port 18982 \
     --rpc-noauth --p2p-enc off --connect 127.0.0.1:19981 > $W/$1.node.log 2>&1 & NP=$!
  sleep 12
  h=$(curl -s -m3 -d '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:18982/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"])')
  echo "$1: served=[$2] relay=[${3:-}] -> height=$h (expect 5)"
  kill $NP; wait $NP 2>/dev/null; kill $PP 2>/dev/null; wait $PP 2>/dev/null; sleep 1; }
case_run control      "1,2,3,4,5"
case_run orphan       "1,3,2,4,5"
case_run orphan_relay "1,3,2" "4,5"
echo "logs: $W"
