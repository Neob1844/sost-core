#!/usr/bin/env bash
# monitor-connections.sh — log + alert on RPC port connection saturation.
#
# Runs every hour from the systemd timer. Counts every TCP connection
# in any state (ESTAB, TIME-WAIT, CLOSE-WAIT, FIN-WAIT-*, …) on the RPC
# port and writes a compact one-line summary. If the total exceeds
# ALERT_THRESHOLD it logs WARN and (optionally) writes a marker file
# operators can wire to their alerting of choice.

set -u

LOG=/var/log/sost-conn-monitor.log
ALERT_MARK=/run/sost-conn-saturation
PORT=18232
ALERT_THRESHOLD=500

if [ -f "$LOG" ] && [ "$(stat -c%s "$LOG" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv -f "$LOG" "$LOG.1" 2>/dev/null || true
fi

TOTAL=$(ss -tan 2>/dev/null | grep -c ":$PORT" || echo 0)
BREAKDOWN=$(ss -tan 2>/dev/null | grep ":$PORT" | awk '{print $1}' \
            | sort | uniq -c | tr '\n' ' ' | sed 's/  */ /g')

LINE="[$(date -Iseconds)] total=$TOTAL  $BREAKDOWN"
if [ "$TOTAL" -ge "$ALERT_THRESHOLD" ]; then
    echo "WARN $LINE" >> "$LOG"
    : > "$ALERT_MARK"
else
    echo "ok   $LINE" >> "$LOG"
    rm -f "$ALERT_MARK" 2>/dev/null || true
fi
