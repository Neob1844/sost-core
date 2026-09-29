#!/usr/bin/env bash
# Mixed-version starvation test: which side needs the fix? A mines; B follows A.
S="${LAB_DIR:-$(mktemp -d)}"
OFF="${OFF_BUILD:?DEVNET build of unmodified v16.3.0}"; FIX="${FIX_BUILD:?DEVNET build of this branch}"
G="${GENESIS:-$(cd "$(dirname "$0")/../.." && pwd)/genesis_block.json}"
run_case(){ # name binA binB
  local W=$S/lab5/$1; rm -rf $W; mkdir -p $W
  python3 -c "import signal,os,sys; signal.signal(signal.SIGPIPE,signal.SIG_IGN); os.execv(sys.argv[1],sys.argv[1:])" $2/sost-node --profile dev --genesis $G --chain $W/a.json --port 19961 --rpc-port 18961 --rpc-noauth --p2p-enc on --connect 127.0.0.1:1 > $W/a.log 2>&1 & PA=$!
  sleep 3
  python3 -c "import signal,os,sys; signal.signal(signal.SIGPIPE,signal.SIG_IGN); os.execv(sys.argv[1],sys.argv[1:])" $3/sost-node --profile dev --genesis $G --chain $W/b.json --port 19962 --rpc-port 18962 --rpc-noauth --p2p-enc on --connect localhost:19961 > $W/b.log 2>&1 & PB=$!
  sleep 3
  ADDR=$($OFF/sost-cli --wallet $W/m.json newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)
  $OFF/sost-miner --profile dev --rpc 127.0.0.1:18961 --address $ADDR --wallet $W/m.json --mining-key-label default --blocks 100000 --threads 4 > $W/m.log 2>&1 & PM=$!
  h(){ curl -s -m5 -d '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:$1/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"])' 2>/dev/null; }
  until [[ "$(h 18961)" -ge 75 ]]; do sleep 3; done; kill $PM; wait $PM 2>/dev/null; sleep 5
  echo "$1: A($(basename $(dirname $2))) h=$(h 18961)  B($(basename $(dirname $3))) h=$(h 18962)"
  kill $PA $PB; wait $PA $PB 2>/dev/null; sleep 2
}
run_case sender_official_receiver_fixed $OFF $FIX
run_case sender_fixed_receiver_official $FIX $OFF
