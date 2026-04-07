#!/bin/bash
# SOST Auto-Checkpoint Updater
# Cron: */30 * * * * /opt/sost/deploy/update_checkpoint.sh
#
# Updates checkpoint.json when chain advances >100 blocks past current checkpoint.
# Node reads checkpoint.json on restart — no recompilation needed.
# Restarts the node service only when checkpoint actually changes.

set -euo pipefail

RPC_URL="http://127.0.0.1:18232"
CHECKPOINT_FILE="/opt/sost/build/checkpoint.json"
LOG="/var/log/sost-checkpoint.log"
MIN_ADVANCE=100  # only update if chain is >100 blocks past checkpoint

NOW=$(date '+%Y-%m-%d %H:%M:%S')

# Get current block height
HEIGHT=$(curl -sf -m 5 -d '{"method":"getblockcount","params":[],"id":1}' "$RPC_URL" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])" 2>/dev/null) || {
    echo "[$NOW] ERROR — node not responding" >> "$LOG"
    exit 1
}

# Read current checkpoint height (0 if file doesn't exist)
CURRENT_CP=0
if [ -f "$CHECKPOINT_FILE" ]; then
    CURRENT_CP=$(python3 -c "import json; print(json.load(open('$CHECKPOINT_FILE'))['assumevalid_height'])" 2>/dev/null || echo 0)
fi

# Check if we need to update
ADVANCE=$((HEIGHT - CURRENT_CP))
if [ "$ADVANCE" -lt "$MIN_ADVANCE" ]; then
    exit 0  # not enough advance, skip silently
fi

# Use height - 50 as the new checkpoint (50-block safety margin)
NEW_CP=$((HEIGHT - 50))

# Get block hash at checkpoint height
HASH=$(curl -sf -m 5 -d "{\"method\":\"getblockhash\",\"params\":[\"$NEW_CP\"],\"id\":1}" "$RPC_URL" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])" 2>/dev/null) || {
    echo "[$NOW] ERROR — cannot get hash for block $NEW_CP" >> "$LOG"
    exit 1
}

# Validate hash looks correct (64 hex chars)
if [ ${#HASH} -ne 64 ]; then
    echo "[$NOW] ERROR — invalid hash length for block $NEW_CP: $HASH" >> "$LOG"
    exit 1
fi

# Write new checkpoint.json
cat > "$CHECKPOINT_FILE" << EOF
{
  "assumevalid_height": $NEW_CP,
  "assumevalid_hash": "$HASH",
  "updated": "$NOW",
  "chain_height_at_update": $HEIGHT,
  "previous_checkpoint": $CURRENT_CP
}
EOF

echo "[$NOW] UPDATED checkpoint: $CURRENT_CP → $NEW_CP (chain at $HEIGHT, hash=${HASH:0:16}...)" >> "$LOG"

# Restart node to pick up new checkpoint
systemctl restart sost-node 2>/dev/null
sleep 3

# Verify node is back up
VERIFY=$(curl -sf -m 5 -d '{"method":"getblockcount","params":[],"id":1}' "$RPC_URL" 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['result'])" 2>/dev/null) || VERIFY="FAILED"

echo "[$NOW] Node restarted — height after restart: $VERIFY" >> "$LOG"
