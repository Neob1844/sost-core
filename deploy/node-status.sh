#!/bin/bash
# SOST Node Status — writes JSON for explorer frontend
# Install: crontab -e → */1 * * * * /opt/sost/deploy/node-status.sh
# Output: /opt/sost/website/node-status.json

RPC_URL="http://127.0.0.1:18232"
RPC_USER="sostadmin"
RPC_PASS="$(cat /opt/sost/.rpc-pass 2>/dev/null || echo '')"
OUT="/opt/sost/website/node-status.json"

# Get blockcount
BC=$(curl -s --max-time 5 -u "$RPC_USER:$RPC_PASS" -d '{"method":"getblockcount","params":[]}' -H 'Content-Type:application/json' "$RPC_URL" 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('result',0))" 2>/dev/null)

# Check miner process
MINER_PID=$(pgrep -f sost-miner 2>/dev/null)
MINER_ACTIVE=false
if [ -n "$MINER_PID" ]; then MINER_ACTIVE=true; fi

# Node active if blockcount > 0
NODE_ACTIVE=false
if [ -n "$BC" ] && [ "$BC" -gt 0 ] 2>/dev/null; then NODE_ACTIVE=true; fi

# Write JSON
TS=$(date +%s)
cat > "$OUT" << EOF
{"node":$NODE_ACTIVE,"miner":$MINER_ACTIVE,"blockcount":${BC:-0},"timestamp":$TS}
EOF

chmod 644 "$OUT"
