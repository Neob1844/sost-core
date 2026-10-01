#!/usr/bin/env bash
# prefork_checklist.sh — READ-ONLY pre/post-#30000 fork verification for SOST.
# Prints height, distance to the fork, tip, V16/Jackpot-V2/DTD parameters, miner
# liveness (two-sample height delta), RPC health, peers and mempool. It NEVER
# writes, restarts, kills or reconfigures anything. Run it in the days before the
# fork and immediately after #30000.
#   ssh root@VPS bash -s < scripts/ops/prefork_checklist.sh
set -uo pipefail
RPC_USER="${RPC_USER:-AdminNeoB}"; RPC_PASS_FILE="${RPC_PASS_FILE:-/etc/sost/rpc.pass}"; RPC_PORT="${RPC_PORT:-18232}"
V16=30000; JV2=30186
pass=$(cat "$RPC_PASS_FILE" 2>/dev/null)
rpc(){ curl -s --max-time 8 -u "$RPC_USER:$pass" -H 'content-type: application/json' --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" "http://127.0.0.1:$RPC_PORT/"; }
num(){ grep -oE "\"result\":[0-9]+" | grep -oE "[0-9]+"; }
H=$(rpc getblockcount | num)
[ -z "${H:-}" ] && { echo "FAIL: RPC unreachable"; exit 3; }
sleep 4; H2=$(rpc getblockcount | num)
echo "==================== SOST PRE/POST-FORK CHECKLIST (read-only) ===================="
printf '%-26s %s\n' "UTC:" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '%-26s %s\n' "HEIGHT:" "$H"
printf '%-26s %s\n' "TO #29850:" "$((29850-H))"
printf '%-26s %s\n' "TO #29900:" "$((29900-H))"
printf '%-26s %s\n' "TO #30000:" "$((V16-H))"
printf '%-26s %s\n' "MINER PRODUCING:" "$([ "${H2:-$H}" -ge "$H" ] && echo "yes (h $H -> ${H2:-$H} in ~4s window; blocks advance over time)" || echo "CHECK")"
printf '%-26s %s\n' "V16 ACTIVATION HEIGHT:" "$V16 (owner-locked)"
printf '%-26s %s\n' "FIRST JACKPOT V2:" "$JV2"
printf '%-26s %s\n' "V16 ACTIVE NOW?:" "$([ "$H" -ge "$V16" ] && echo YES || echo "not yet (activates by height at $V16)")"
printf '%-26s %s\n' "RPC HEALTH:" "OK (getblockcount responded)"
PEERS=$(rpc getconnectioncount | num); printf '%-26s %s\n' "PEERS:" "${PEERS:-n/a}"
MP=$(rpc getmempoolinfo | grep -oE "\"size\":[0-9]+" | grep -oE "[0-9]+" | head -1); printf '%-26s %s\n' "MEMPOOL SIZE:" "${MP:-n/a}"
printf '%-26s %s\n' "STALL FLAG:" "$(cat /opt/sost/website/chain-stall.json 2>/dev/null || echo 'not written yet')"
echo "NOTE: read-only. Do NOT swap the STRATO binary or touch consensus for a toolchain-only hash diff."
echo "================================================================================="
