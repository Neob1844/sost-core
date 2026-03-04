#!/bin/bash
# ===========================================================================
# SOST Node Health Check — run via cron every 5 minutes
# crontab -e → */5 * * * * /opt/sost/monitor.sh >> /opt/sost/monitor.log 2>&1
# ===========================================================================

RPC_USER="CHANGE_ME"
RPC_PASS="CHANGE_ME"
RPC_URL="http://127.0.0.1:18232"
LOG_FILE="/opt/sost/monitor.log"

NOW=$(date '+%Y-%m-%d %H:%M:%S')

# Check if node process is running
if ! pgrep -f "sost-node" > /dev/null; then
    echo "[$NOW] ALERT: sost-node is NOT running! Attempting restart..."
    sudo systemctl restart sost-node
    sleep 5
fi

# Check if miner process is running
if ! pgrep -f "sost-miner" > /dev/null; then
    echo "[$NOW] ALERT: sost-miner is NOT running! Attempting restart..."
    sudo systemctl restart sost-miner
    sleep 5
fi

# Query node status
RESPONSE=$(curl -s --max-time 10 -u "$RPC_USER:$RPC_PASS" -X POST \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","id":1,"method":"getinfo","params":[]}' \
    "$RPC_URL" 2>/dev/null)

if [ -z "$RESPONSE" ]; then
    echo "[$NOW] ALERT: Node RPC not responding!"
    exit 1
fi

HEIGHT=$(echo "$RESPONSE" | grep -o '"height":[0-9]*' | grep -o '[0-9]*')
PEERS=$(echo "$RESPONSE" | grep -o '"peers":[0-9]*' | grep -o '[0-9]*')
MEMPOOL=$(echo "$RESPONSE" | grep -o '"mempool_size":[0-9]*' | grep -o '[0-9]*')

echo "[$NOW] OK: height=$HEIGHT peers=${PEERS:-0} mempool=${MEMPOOL:-0}"

# Alert if no peers (after initial setup)
if [ "${PEERS:-0}" -eq 0 ]; then
    echo "[$NOW] WARNING: No connected peers!"
fi
