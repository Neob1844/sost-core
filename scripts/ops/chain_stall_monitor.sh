#!/usr/bin/env bash
# chain_stall_monitor.sh — detects a STALLED chain (RPC up but no new blocks).
# health_check.sh already restarts the node when RPC is DOWN; this catches the
# other failure mode: RPC responds but height stops advancing (miner stalled,
# timestamp-too-far rejection, fork wedge). Read-only w.r.t. the node: it never
# restarts, kills or reconfigures anything — it only records state and writes a
# served flag + log line an operator/alert can consume. Safe near the fork.
#
# cron (VPS): */5 * * * * /opt/sost/scripts/ops/chain_stall_monitor.sh
set -uo pipefail
RPC_USER="${RPC_USER:-AdminNeoB}"
RPC_PASS_FILE="${RPC_PASS_FILE:-/etc/sost/rpc.pass}"
RPC_PORT="${RPC_PORT:-18232}"
STALL_SECS="${STALL_SECS:-1800}"        # 30 min (~3 block times at 10 min); alert past this
STATE="${STATE:-/opt/sost/data/chain_stall_state}"
FLAG="${FLAG:-/opt/sost/website/chain-stall.json}"   # served; explorer/monitor can read
LOG="${LOG:-/var/log/sost-stall.log}"
NOW=$(date -u +%s); NOWH=$(date -u +%Y-%m-%dT%H:%M:%SZ)

pass=$(cat "$RPC_PASS_FILE" 2>/dev/null)
H=$(curl -s --max-time 8 -u "$RPC_USER:$pass" -H 'content-type: application/json' \
     --data '{"jsonrpc":"2.0","id":1,"method":"getblockcount","params":[]}' \
     "http://127.0.0.1:$RPC_PORT/" 2>/dev/null | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+')
if [ -z "${H:-}" ]; then
  # RPC unreachable is health_check.sh's job; record and exit non-alerting here.
  echo "[$NOWH] rpc-unreachable (deferred to health_check)" >> "$LOG" 2>/dev/null || true
  exit 0
fi

mkdir -p "$(dirname "$STATE")" "$(dirname "$FLAG")" 2>/dev/null || true
prevH=0; prevT=$NOW
if [ -f "$STATE" ]; then prevH=$(cut -d' ' -f1 "$STATE" 2>/dev/null); prevT=$(cut -d' ' -f2 "$STATE" 2>/dev/null); fi
[ -z "${prevH:-}" ] && prevH=0; [ -z "${prevT:-}" ] && prevT=$NOW

if [ "$H" -gt "${prevH:-0}" ]; then
  echo "$H $NOW" > "$STATE"                       # advanced: reset the clock
  printf '{"stalled":false,"height":%s,"stalled_for_secs":0,"checked":"%s","to_29900":%s,"to_30000":%s}\n' \
    "$H" "$NOWH" "$((29900-H))" "$((30000-H))" > "$FLAG"
else
  age=$(( NOW - prevT ))
  if [ "$age" -ge "$STALL_SECS" ]; then
    echo "[$NOWH] CRITICAL STALL — height stuck at $H for ${age}s (>= ${STALL_SECS}s). RPC up, no new blocks." >> "$LOG"
    printf '{"stalled":true,"height":%s,"stalled_for_secs":%s,"checked":"%s","to_29900":%s,"to_30000":%s}\n' \
      "$H" "$age" "$NOWH" "$((29900-H))" "$((30000-H))" > "$FLAG"
  else
    printf '{"stalled":false,"height":%s,"stalled_for_secs":%s,"checked":"%s","to_29900":%s,"to_30000":%s}\n' \
      "$H" "$age" "$NOWH" "$((29900-H))" "$((30000-H))" > "$FLAG"
  fi
fi
exit 0
