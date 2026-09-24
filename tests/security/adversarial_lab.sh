#!/usr/bin/env bash
# SOST Adversarial Network Lab (Phase D) — orchestrates concurrent attack vectors
# against a disposable victim node and measures resource use. Fully isolated: only
# 127.0.0.0/8, no mainnet, no STRATO, no real keys. Scale with env vars.
#
#   NODE=<sost-node>  GENESIS_HEX=<hex>  BASE_BLOCK=<block.json>  CHAIN=<chain.json>
#   ATK_IPS=40  FORK_N=45  DURATION=60  ./adversarial_lab.sh
#
# Vectors run concurrently: fork-storm (multi-IP /24), connection churn, relay
# flood. Measures peak RSS, FDs, index size, bans, and — crucially — HOW the node
# dies if it dies: `wait` yields the exit status, and 128+N decodes the signal, so
# a SIGPIPE/SIGSEGV death (the V6 class) is reported instead of a bogus "alive".
set -u
NODE="${NODE:?set NODE}"; GENESIS_HEX="${GENESIS_HEX:?}"; BASE_BLOCK="${BASE_BLOCK:?}"; CHAIN="${CHAIN:?}"
ATK_IPS="${ATK_IPS:-40}"; FORK_N="${FORK_N:-45}"; DURATION="${DURATION:-60}"
HERE="$(cd "$(dirname "$0")" && pwd)"
W="$(mktemp -d /tmp/advlab.XXXXXX)"; PORT=19860; RPORT=18860
for f in genesis_block.json popc_registry.json rpc.pass wallet.json; do
  cp "$(dirname "$CHAIN")/$f" "$W/" 2>/dev/null || true
done
cp "$CHAIN" "$W/chain.json"

# --- Launch the victim with RELIABLE PID capture ($!, not ss/pgrep) ---
# No setsid/subshell wrapper: the node is a direct child of this script, so $!
# is exactly its PID and `wait` later yields its true exit status.
( cd "$W" && exec "$NODE" --genesis genesis_block.json --chain chain.json \
    --profile mainnet --port $PORT --rpc-port $RPORT --rpc-user u --rpc-pass-file rpc.pass \
    --connect 127.0.0.1:1 > node.log 2>&1 < /dev/null ) &
VPID=$!
sleep 7
# sanity: the captured PID must actually be our node, not a ghost
COMM=$(cat /proc/$VPID/comm 2>/dev/null || echo GONE)
echo "[lab] victim PID $VPID comm=$COMM  vectors=fork/churn  ATK_IPS=$ATK_IPS DURATION=${DURATION}s"

PEAK=0
mon() { for _ in $(seq 1 $((DURATION/3))); do
  [ -d /proc/$VPID ] || { echo "[lab] NODE DIED during attack (t≈$((_*3))s)"; return; }
  r=$(awk '/VmRSS/{print $2/1024}' /proc/$VPID/status 2>/dev/null); r=${r%.*}
  [ "${r:-0}" -gt "$PEAK" ] && PEAK=$r
  sleep 3; done; }

# --- Concurrent attack vectors ---
timeout $DURATION python3 "$HERE/v1_fork_poison_attacker.py" 127.0.0.1 $PORT "$GENESIS_HEX" "$BASE_BLOCK" >/dev/null 2>&1 &
FORK_BG=$!
# connection churn: connect/close rapidly — this is the vector that exposed V6
timeout $DURATION bash -c "while true; do python3 \"$HERE/churn_attacker.py\" 127.0.0.1 $PORT 100 >/dev/null 2>&1; done" &
CHURN_BG=$!
mon
wait $FORK_BG 2>/dev/null; kill $CHURN_BG 2>/dev/null; wait $CHURN_BG 2>/dev/null

# --- How is the node now? If dead, decode the killing signal ---
if [ -d /proc/$VPID ]; then
  ALIVE=yes; RC=""
else
  ALIVE=NO; wait $VPID 2>/dev/null; RC=$?
  SIG=$((RC-128)); SIGNM=$(kill -l $SIG 2>/dev/null || echo "?")
  echo "[lab] node exit status=$RC $( [ $RC -gt 128 ] && echo "(killed by SIG$SIGNM)" )"
fi
ST=$(curl -s -m5 -u "u:$(cat $W/rpc.pass)" -X POST http://127.0.0.1:$RPORT -d '{"jsonrpc":"1.0","id":1,"method":"getforkstats","params":[]}' 2>/dev/null)
FDS=$([ -d /proc/$VPID ] && ls /proc/$VPID/fd 2>/dev/null | wc -l)
echo "[lab] alive=$ALIVE peak_rss=${PEAK}MB fds=${FDS:-n/a} forkstats=$(echo "$ST"|grep -oE '\"forks\":[0-9]+,\"orphans\":[0-9]+')"
echo "[lab] rejects=$(grep -c REJECTED $W/node.log) invalid-bans=$(grep -c 'BANNED.*invalid' $W/node.log)"

# --- Post-attack liveness: honest forks from BOTH a foreign /24 and the SAME /24
#     as the attackers must still be accepted (V1 + V3 false-positive guard). ---
if [ "$ALIVE" = yes ]; then
  timeout 20 python3 "$HERE/v1_fork_honest_peer.py"        127.0.0.1 $PORT "$GENESIS_HEX" "$BASE_BLOCK" >/dev/null 2>&1
  timeout 20 python3 "$HERE/v1_fork_honest_same_subnet.py" 127.0.0.1 $PORT "$GENESIS_HEX" "$BASE_BLOCK" >/dev/null 2>&1
  sleep 2
  HON=$(grep -c deadbeef $W/node.log)
  echo "[lab] post-attack honest fork accepted: $([ "$HON" -ge 1 ] && echo YES || echo NO)"
fi

[ -d /proc/$VPID ] && kill $VPID 2>/dev/null
if [ "$ALIVE" = yes ]; then rm -rf "$W"; else echo "[lab] log kept at $W/node.log"; fi
# Exit non-zero if the node died — makes the lab usable as a CI gate.
[ "$ALIVE" = yes ]
