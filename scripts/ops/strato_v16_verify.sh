#!/usr/bin/env bash
# strato_v16_verify.sh — STRICTLY READ-ONLY verification of the running sost-node ("STRATO")
# against the expected V16 (v16.3.0) release binary.
#
# It NEVER writes, restarts, stops, kills, replaces a binary, or changes any config/service.
# It only: locates the node PID, resolves /proc/PID/exe, hashes it, reads the chain height and
# RPC health, and compares against the expected release hash. Safe to run on production.
#
# Expected values come from docs/v16/SHA256SUMS (commit a69e7182…). Override via env if needed.
set -uo pipefail

EXPECTED_NODE_SHA="${EXPECTED_NODE_SHA:-304d056d504960b4179543672f14bee28146788b985363a5e95d476cc6b1492e}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-a69e7182e8dacc8a6143918d6dbf7a9e35294339}"
EXPECTED_ACTIVATION="${EXPECTED_ACTIVATION:-30000}"
RPC_USER="${RPC_USER:-AdminNeoB}"
RPC_PASS_FILE="${RPC_PASS_FILE:-/etc/sost/rpc.pass}"

say() { printf '%-22s %s\n' "$1" "$2"; }

# 1. PID — prefer systemd MainPID, fall back to EXACT-name pgrep (never pkill / never by pattern)
PID="$(systemctl show -p MainPID --value sost-node 2>/dev/null || true)"
case "$PID" in ''|0) PID="$(pgrep -x sost-node 2>/dev/null | head -1)";; esac
if [ -z "${PID:-}" ]; then echo "FAIL: no running sost-node found"; exit 3; fi

# 2. executable path (read-only)
EXE="$(readlink -f "/proc/$PID/exe" 2>/dev/null || true)"

# 3. sha256 of the currently-loaded binary (read-only)
CUR_SHA="$(sha256sum "$EXE" 2>/dev/null | awk '{print $1}')"

# 4. service status (read-only)
SVC="$(systemctl is-active sost-node 2>/dev/null || echo unknown)"

# 5. RPC port — autodetect the node's localhost listener, else default 18232 (read-only)
RPC_PORT="$(ss -ltnp 2>/dev/null | grep "pid=$PID," | grep -oE '127\.0\.0\.1:[0-9]+' | head -1 | cut -d: -f2)"
RPC_PORT="${RPC_PORT:-18232}"

rpc() { # $1 = method  — read-only JSON-RPC call
  local pass; pass="$(cat "$RPC_PASS_FILE" 2>/dev/null)"
  curl -s --max-time 8 -u "$RPC_USER:$pass" -H 'content-type: application/json' \
    --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":[]}" \
    "http://127.0.0.1:$RPC_PORT/" 2>/dev/null
}

HEIGHT_JSON="$(rpc getblockcount)"
HEIGHT="$(printf '%s' "$HEIGHT_JSON" | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1)"
if [ -n "${HEIGHT:-}" ]; then RPC_HEALTH="OK (getblockcount responded)"; else RPC_HEALTH="UNREACHABLE"; HEIGHT="n/a"; fi

# node version, if the RPC exposes it (read-only; we do NOT exec the binary)
BCINFO="$(rpc getblockchaininfo)"
VER="$(printf '%s' "$BCINFO" | grep -oE '"(subversion|version)":"?[^",}]+' | head -1 | sed 's/.*://; s/"//g')"
[ -z "${VER:-}" ] && VER="n/a (not exposed by RPC; do not exec the daemon to read it)"

if [ "$CUR_SHA" = "$EXPECTED_NODE_SHA" ]; then MATCH="YES"; else MATCH="NO"; fi

echo   "==================== STRATO V16 READ-ONLY VERIFICATION ===================="
say    "CURRENT PID:"        "$PID"
say    "CURRENT EXECUTABLE:" "${EXE:-unknown}"
say    "CURRENT SHA256:"     "${CUR_SHA:-unknown}"
say    "EXPECTED V16 SHA256:" "$EXPECTED_NODE_SHA"
say    "MATCH:"              "$MATCH"
say    "SERVICE STATUS:"     "$SVC"
say    "CURRENT HEIGHT:"     "$HEIGHT"
say    "RPC HEALTH:"         "$RPC_HEALTH"
say    "NODE VERSION:"       "$VER"
say    "V16 SOURCE COMMIT:"  "$EXPECTED_COMMIT"
say    "ACTIVATION HEIGHT:"  "$EXPECTED_ACTIVATION"
if [ "$MATCH" = "YES" ]; then
  say  "ACTION REQUIRED:"    "NO — STRATO V16 BINARY VERIFIED"
else
  say  "ACTION REQUIRED:"    "YES — running binary != expected V16 release (report; do NOT auto-swap)"
fi
echo   "==========================================================================="
echo   "NOTE: read-only. No process was started, stopped, killed or replaced; no file was written."
