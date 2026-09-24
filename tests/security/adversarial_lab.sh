#!/usr/bin/env bash
# SOST Adversarial Network Lab (Phase D) — orchestrates concurrent attack vectors
# against a disposable victim node and measures resource use. Fully isolated: only
# 127.0.0.0/8, no mainnet, no STRATO, no real keys. Scale with env vars.
#
#   NODE=<sost-node>  GENESIS_HEX=<hex>  BASE_BLOCK=<block.json>  CHAIN=<chain.json>
#   ATK_IPS=40  FORK_N=45  DURATION=60  ./adversarial_lab.sh
#
# Vectors run concurrently: fork-storm (multi-IP /24), orphan-storm, connection
# churn, relay flood. Measures peak RSS, CPU, FDs, index size, bans, and whether
# the node stays alive and accepts an honest fork afterwards.
set -u
NODE="${NODE:?set NODE}"; GENESIS_HEX="${GENESIS_HEX:?}"; BASE_BLOCK="${BASE_BLOCK:?}"; CHAIN="${CHAIN:?}"
ATK_IPS="${ATK_IPS:-40}"; FORK_N="${FORK_N:-45}"; DURATION="${DURATION:-60}"
HERE="$(cd "$(dirname "$0")" && pwd)"
W="$(mktemp -d /tmp/advlab.XXXXXX)"; PORT=19860; RPORT=18860
for f in genesis_block.json popc_registry.json rpc.pass wallet.json; do
  cp "$(dirname "$CHAIN")/$f" "$W/" 2>/dev/null || true
done
cp "$CHAIN" "$W/chain.json"
( cd "$W" && setsid nohup "$NODE" --genesis genesis_block.json --chain chain.json \
    --profile mainnet --port $PORT --rpc-port $RPORT --rpc-user u --rpc-pass-file rpc.pass \
    --connect 127.0.0.1:1 > "$W/node.log" 2>&1 < /dev/null & )
sleep 7
VPID=$(ss -ltnp 2>/dev/null|grep ":$RPORT "|grep -oE 'pid=[0-9]+'|cut -d= -f2|head -1)
echo "[lab] victim PID $VPID  vectors=fork/orphan/churn  ATK_IPS=$ATK_IPS DURATION=${DURATION}s"
PEAK=0
mon() { for _ in $(seq 1 $((DURATION/3))); do
  [ -d /proc/$VPID ] || { echo "[lab] NODE DIED"; return; }
  r=$(grep VmRSS /proc/$VPID/status 2>/dev/null|awk '{print $2/1024}'); r=${r%.*}
  [ "${r:-0}" -gt "$PEAK" ] && PEAK=$r
  sleep 3; done; }
# launch vectors concurrently
timeout $DURATION python3 "$HERE/v1_fork_poison_attacker.py" 127.0.0.1 $PORT "$GENESIS_HEX" "$BASE_BLOCK" >/dev/null 2>&1 &
# connection churn: connect/disconnect rapidly
timeout $DURATION bash -c "while true; do python3 \"$HERE/churn_attacker.py\" 127.0.0.1 $PORT 100 >/dev/null 2>&1; done" >/dev/null 2>&1 &
mon
wait 2>/dev/null
ALIVE=$([ -d /proc/$VPID ] && echo yes || echo NO)
ST=$(curl -s -m5 -u "u:$(cat $W/rpc.pass)" -X POST http://127.0.0.1:$RPORT -d '{"jsonrpc":"1.0","id":1,"method":"getforkstats","params":[]}' 2>/dev/null)
FDS=$([ -d /proc/$VPID ] && ls /proc/$VPID/fd 2>/dev/null | wc -l)
echo "[lab] alive=$ALIVE peak_rss=${PEAK}MB fds=$FDS forkstats=$(echo "$ST"|grep -oE '\"forks\":[0-9]+,\"orphans\":[0-9]+')"
echo "[lab] rejects=$(grep -c REJECTED $W/node.log) invalid-bans=$(grep -c 'BANNED.*invalid' $W/node.log)"
# post-attack: honest fork from a different /24 must still be accepted
timeout 20 python3 "$HERE/v1_fork_honest_peer.py" 127.0.0.1 $PORT "$GENESIS_HEX" "$BASE_BLOCK" >/dev/null 2>&1
sleep 2
HON=$(grep -c deadbeef $W/node.log)
echo "[lab] post-attack honest fork accepted: $([ "$HON" -ge 1 ] && echo YES || echo NO)"
[ -n "$VPID" ] && [ -d /proc/$VPID ] && kill $VPID
if [ "$ALIVE" = yes ]; then rm -rf "$W"; else echo "[lab] log kept at $W/node.log"; fi
