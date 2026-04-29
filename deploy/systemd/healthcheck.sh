#!/usr/bin/env bash
#
# healthcheck.sh — verify sost-node is properly configured and answering
# authenticated RPC calls.
#
# Catches the silent "empty RPC credentials" failure mode by issuing a
# real authenticated sendrawtransaction with garbage hex. A working node
# returns a JSON error like "TX decode failed" (HTTP 200, auth passed,
# payload rejected). A broken node returns HTTP 401.
#
# Exit codes:
#   0 — every invariant passed
#   1 — at least one invariant failed (details on stderr)
#   2 — environment problem (missing tools, must run as root, etc.)
#
set -uo pipefail

ENV_FILE="/etc/sost/rpc.env"
UNIT_FILE="/etc/systemd/system/sost-node.service"
RPC_HOST="127.0.0.1"
RPC_PORT="18232"

C_RED=$'\033[31m'
C_GRN=$'\033[32m'
C_YEL=$'\033[33m'
C_OFF=$'\033[0m'

PASS=()
FAIL=()

ok()   { PASS+=("$1"); printf "%sPASS%s  %s\n" "$C_GRN" "$C_OFF" "$1"; }
warn() { printf "%sWARN%s  %s\n" "$C_YEL" "$C_OFF" "$1"; }
bad()  { FAIL+=("$1"); printf "%sFAIL%s  %s\n" "$C_RED" "$C_OFF" "$1" >&2; }

# --- root required for env file read ---
if [ "$(id -u)" -ne 0 ]; then
  echo "must run as root (use sudo) — needs to read $ENV_FILE" >&2
  exit 2
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not installed — install with: apt install -y curl" >&2
  exit 2
fi

echo "== sost-node healthcheck =="
echo "host: ${RPC_HOST}:${RPC_PORT}"
echo

# --- 1. unit file present ---
if [ -f "$UNIT_FILE" ]; then
  ok "unit installed at $UNIT_FILE"
else
  bad "unit file missing: $UNIT_FILE"
fi

# --- 2. env file present and 600 ---
if [ -f "$ENV_FILE" ]; then
  ok "env file present: $ENV_FILE"
  perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%Lp' "$ENV_FILE" 2>/dev/null)"
  if [ "$perm" = "600" ]; then
    ok "env file mode is 600"
  else
    bad "env file mode is $perm (expected 600) — fix with: chmod 600 $ENV_FILE"
  fi
  owner="$(stat -c '%U:%G' "$ENV_FILE" 2>/dev/null)"
  if [ "$owner" = "root:root" ]; then
    ok "env file owned by root:root"
  else
    bad "env file owned by $owner (expected root:root) — fix with: chown root:root $ENV_FILE"
  fi
else
  bad "env file missing: $ENV_FILE — run install-sost-node.sh to generate"
fi

# --- 3. credentials non-empty ---
RPC_USER=""
RPC_PASS=""
if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; . "$ENV_FILE"; set +a
fi
if [ -n "${RPC_USER:-}" ]; then
  ok "RPC_USER set (len ${#RPC_USER}, prefix ${RPC_USER:0:8}...)"
else
  bad "RPC_USER empty in $ENV_FILE"
fi
if [ -n "${RPC_PASS:-}" ]; then
  ok "RPC_PASS set (len ${#RPC_PASS}, prefix ${RPC_PASS:0:8}...)"
else
  bad "RPC_PASS empty in $ENV_FILE"
fi

# --- 4. service active ---
if systemctl is-active --quiet sost-node; then
  ok "sost-node service is active"
else
  bad "sost-node service is NOT active — see: journalctl -u sost-node -n 40 --no-pager"
fi

# --- 5. ExecStart of running process has actual values ---
exec_line="$(ps -ef | grep "[s]ost-node" | head -1)"
if [ -n "$exec_line" ]; then
  if echo "$exec_line" | grep -qE -- '--rpc-user [^ ]+ --rpc-pass [^ ]+'; then
    ok "running process has --rpc-user / --rpc-pass with values"
  else
    bad "running process has empty --rpc-user / --rpc-pass — systemd substitution failed"
    echo "    -> $(echo "$exec_line" | grep -oE -- '--rpc-user [^ ]+ --rpc-pass [^ ]+' || echo '(args missing)')" >&2
  fi
else
  bad "no sost-node process found"
fi

# --- 6. RPC port listening ---
if ss -tlnp 2>/dev/null | grep -qE "127\.0\.0\.1:${RPC_PORT}\b|::1:${RPC_PORT}\b"; then
  ok "RPC port ${RPC_PORT} is listening on loopback"
else
  bad "RPC port ${RPC_PORT} is NOT listening — node may not have started"
fi

# --- 7. unauthenticated read works (sanity) ---
unauth_resp="$(curl -s -o /dev/null -w '%{http_code}' \
  -X POST "http://${RPC_HOST}:${RPC_PORT}/" \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"getinfo","params":[]}' || echo 000)"
if [ "$unauth_resp" = "200" ]; then
  ok "unauth getinfo returns 200"
else
  warn "unauth getinfo returned $unauth_resp (expected 200)"
fi

# --- 8. authenticated WRITE reaches dispatcher (the critical check) ---
if [ -n "${RPC_USER:-}" ] && [ -n "${RPC_PASS:-}" ]; then
  auth_resp="$(curl -s -u "${RPC_USER}:${RPC_PASS}" \
    -X POST "http://${RPC_HOST}:${RPC_PORT}/" \
    -H 'Content-Type: application/json' \
    -d '{"jsonrpc":"2.0","id":1,"method":"sendrawtransaction","params":["00"]}' || echo '')"
  if echo "$auth_resp" | grep -qiE 'authentication required|"code":-401'; then
    bad "authenticated sendrawtransaction returned 401 — credentials in env do NOT match running process"
    echo "    response: ${auth_resp:0:160}" >&2
  elif [ -n "$auth_resp" ]; then
    ok "authenticated sendrawtransaction reached the dispatcher (auth OK)"
    # the response will contain a JSON error about the bogus tx, which is what we want
  else
    bad "authenticated sendrawtransaction returned empty body"
  fi
else
  warn "skipping auth write check — credentials not loaded"
fi

# --- summary ---
echo
echo "== summary =="
echo "passed: ${#PASS[@]}"
echo "failed: ${#FAIL[@]}"
if [ "${#FAIL[@]}" -gt 0 ]; then
  echo
  printf '%sFAIL%s — fix the items above and re-run.\n' "$C_RED" "$C_OFF" >&2
  exit 1
fi
printf '%sALL CHECKS PASSED%s\n' "$C_GRN" "$C_OFF"
exit 0
