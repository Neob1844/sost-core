#!/usr/bin/env bash
# health-check.sh — verify sost-node still answers RPC; restart on hang.
#
# Symptom this catches: sost-node process is alive (PID exists,
# systemd reports active), but it has stopped servicing the JSON-RPC
# port. The last incident was a TIME-WAIT saturation; in general any
# I/O / lock / socket-table-exhaustion stall the binary would slip
# under systemd's process-alive heartbeat.
#
# Strategy: GET getinfo with a 10 s timeout. If it times out OR does
# not return a "blocks" key, schedule a `systemctl restart sost-node`.
#
# Idempotent: safe to run repeatedly. Logs every run to
# /var/log/sost-health.log and rotates by size (kept simple — logrotate
# can take over later if needed).

set -u

LOG=/var/log/sost-health.log
ENV_FILE=/etc/sost/rpc.env
PORT=18232
TIMEOUT_SEC=10

# Rotate the log if it grew past 5 MB. Keeps one .1 backup.
if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv -f "$LOG" "$LOG.1" 2>/dev/null || true
fi
echo "[$(date -Iseconds)] health-check start" >> "$LOG"

if [ ! -r "$ENV_FILE" ]; then
    echo "[$(date -Iseconds)] WARN: $ENV_FILE not readable; skipping health probe" >> "$LOG"
    exit 0
fi

# shellcheck disable=SC1090
. "$ENV_FILE"
if [ -z "${RPC_USER:-}" ] || [ -z "${RPC_PASS:-}" ]; then
    echo "[$(date -Iseconds)] WARN: RPC_USER / RPC_PASS missing in $ENV_FILE; skipping" >> "$LOG"
    exit 0
fi

RESP=$(curl -m "$TIMEOUT_SEC" -s \
    -u "$RPC_USER:$RPC_PASS" \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getinfo"}' \
    "http://127.0.0.1:$PORT/" 2>&1)
RC=$?

if [ "$RC" -ne 0 ]; then
    echo "[$(date -Iseconds)] CRITICAL: curl exit=$RC (timeout/connection refused). Restarting sost-node." >> "$LOG"
    systemctl restart sost-node
    exit 0
fi

if echo "$RESP" | grep -q '"blocks"'; then
    BLOCKS=$(echo "$RESP" | sed -n 's/.*"blocks":\([0-9]*\).*/\1/p')
    CONNS=$(ss -tan 2>/dev/null | grep -c ":$PORT" || true)
    echo "[$(date -Iseconds)] ok  blocks=$BLOCKS conns=$CONNS" >> "$LOG"
    exit 0
fi

echo "[$(date -Iseconds)] CRITICAL: RPC responded but 'blocks' missing. Body=${RESP:0:200}. Restarting." >> "$LOG"
systemctl restart sost-node
