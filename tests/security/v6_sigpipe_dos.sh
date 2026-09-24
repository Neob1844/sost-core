#!/usr/bin/env bash
# V6 regression — SIGPIPE availability DoS.
# A peer that closes its socket while the node writes to it delivers SIGPIPE,
# whose default action KILLS the node. Reproduce: fork-storm + connection churn.
#   NODE=<sost-node> GENESIS_HEX=<hex> BASE_BLOCK=<block.json> CHAIN=<chain.json> ./v6_sigpipe_dos.sh
# PASS: node still alive after 45s of churn+flood.
set -u
NODE="${NODE:?}"; GENESIS_HEX="${GENESIS_HEX:?}"; BASE_BLOCK="${BASE_BLOCK:?}"; CHAIN="${CHAIN:?}"
HERE="$(cd "$(dirname "$0")" && pwd)"; W="$(mktemp -d /tmp/v6.XXXXXX)"; P=19870
for f in genesis_block.json popc_registry.json rpc.pass wallet.json; do cp "$(dirname "$CHAIN")/$f" "$W/" 2>/dev/null||true; done
cp "$CHAIN" "$W/chain.json"
( cd "$W" && "$NODE" --genesis genesis_block.json --chain chain.json --profile mainnet \
    --port $P --rpc-port $((P-1000)) --rpc-user u --rpc-pass-file rpc.pass --connect 127.0.0.1:1 > "$W/node.log" 2>&1 & echo $! > "$W/pid" )
sleep 8; NPID=$(cat "$W/pid")
timeout 45 python3 "$HERE/v1_fork_poison_attacker.py" 127.0.0.1 $P "$GENESIS_HEX" "$BASE_BLOCK" >/dev/null 2>&1 &
timeout 45 python3 -c "import socket,time;t=time.time()
while time.time()-t<45:
 for _ in range(50):
  try:s=socket.socket();s.settimeout(1);s.connect(('127.0.0.1',$P));s.close()
  except OSError:pass" >/dev/null 2>&1 &
for i in $(seq 1 16); do kill -0 $NPID 2>/dev/null || { echo "FAIL: node died at $((i*3))s"; rm -rf "$W"; exit 1; }; sleep 3; done
wait 2>/dev/null
if kill -0 $NPID 2>/dev/null; then echo "PASS: node survived churn+flood"; kill $NPID; rm -rf "$W"; exit 0
else echo "FAIL: node died"; rm -rf "$W"; exit 1; fi
