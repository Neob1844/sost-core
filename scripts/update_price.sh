#!/bin/bash
# SOST Price Oracle — Update reference price every 15 minutes
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT="/opt/sost/data/current_price.json"

# Read RPC credentials if available
RPC_USER=""
RPC_PASS=""
if [ -f /etc/sost/rpc.env ]; then
    source /etc/sost/rpc.env
fi

mkdir -p "$(dirname "$OUTPUT")"

python3 "$SCRIPT_DIR/sost_price_oracle.py" \
    ${RPC_USER:+--rpc-url http://127.0.0.1:18232} \
    ${RPC_USER:+--rpc-user "$RPC_USER"} \
    ${RPC_PASS:+--rpc-pass "$RPC_PASS"} \
    --output-file "$OUTPUT" > /dev/null 2>&1

echo "$(date -u '+%Y-%m-%d %H:%M:%S UTC') — Price updated: $(cat "$OUTPUT" 2>/dev/null | python3 -c 'import sys,json;d=json.load(sys.stdin);print(f"${d[\"sost_price_usd\"]:.6f} USD")' 2>/dev/null || echo 'error')" >> /var/log/sost_price.log
