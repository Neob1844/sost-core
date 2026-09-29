#!/usr/bin/env bash
# Watchdog lab: OFFICIAL v16.3.0 code on both nodes. A mines (reference), B is a
# pure relay that starves at +50 without help. The watchdog restarts B on lag.
S="${LAB_DIR:-$(mktemp -d)}"
OFF="${OFF_BUILD:?DEVNET build of unmodified v16.3.0}"
G="${GENESIS:-$(cd "$(dirname "$0")/../.." && pwd)/genesis_block.json}"
WD="${WATCHDOG:?path to sost-relay-watchdog.sh}"; W=$S/lab6; rm -rf $W; mkdir -p $W
IGN='import signal,os,sys; signal.signal(signal.SIGPIPE,signal.SIG_IGN); os.execv(sys.argv[1],sys.argv[1:])'
python3 -c "$IGN" $OFF/sost-node --profile dev --genesis $G --chain $W/a.json --port 19961 --rpc-port 18961 --rpc-noauth --p2p-enc on --connect 127.0.0.1:1 > $W/a.log 2>&1 &
PA=$!
sleep 3
cat > $W/startB.sh <<EOB
#!/usr/bin/env bash
python3 -c "$IGN" $OFF/sost-node --profile dev --genesis $G --chain $W/b.json --port 19962 --rpc-port 18962 --rpc-noauth --p2p-enc on --connect localhost:19961 >> $W/b.log 2>&1 &
echo \$! > $W/b.pid
EOB
cat > $W/restartB.sh <<EOR
#!/usr/bin/env bash
P=\$(cat $W/b.pid); kill \$P; while kill -0 \$P 2>/dev/null; do sleep 0.5; done
sleep 31   # lab only: all nodes share 127.0.0.1 and the reference enforces a 30 s per-IP cooldown
bash $W/startB.sh
EOR
chmod +x $W/*.sh; bash $W/startB.sh; sleep 3
ADDR=$($OFF/sost-cli --wallet $W/m.json newwallet 2>&1 | grep -oE 'sost1[a-z0-9]+' | head -1)
$OFF/sost-miner --profile dev --rpc 127.0.0.1:18961 --address $ADDR --wallet $W/m.json --mining-key-label default --blocks 100000 --threads 1 > $W/m.log 2>&1 &
PM=$!
h(){ curl -s -m5 -d '{"method":"getblockcount","params":[],"id":1}' http://127.0.0.1:$1/ | python3 -c 'import sys,json;print(json.load(sys.stdin)["result"])' 2>/dev/null; }
maxlag=0; restarts=0
while :; do
  ha=$(h 18961); hb=$(h 18962)
  [[ -n "$ha" && -n "$hb" ]] && (( ha-hb > maxlag )) && maxlag=$((ha-hb))
  out=$(LOCAL_RPC=http://127.0.0.1:18962/ REF_RPC=http://127.0.0.1:18961/ MAX_LAG=2 STRIKES=2 MIN_GAP_S=60 \
        RESTART_CMD=$W/restartB.sh STATE=$W/wd.state bash $WD)
  echo "$(date +%T) A=$ha B=$hb | $out" >> $W/trace.log
  grep -q "restarting" <<<"$out" && restarts=$((restarts+1))
  [[ -n "$ha" && "$ha" -ge 200 ]] && break
  sleep 15
done
kill $PM; wait $PM 2>/dev/null
for i in $(seq 1 12); do ha=$(h 18961); hb=$(h 18962); [[ "$ha" == "$hb" ]] && break; sleep 10; done
echo "RESULT: A=$(h 18961) B=$(h 18962) watchdog_restarts=$restarts max_observed_lag=$maxlag instances_of_B=$(pgrep -fc 'lab6/b.json')"
kill $PA $(cat $W/b.pid); wait 2>/dev/null
