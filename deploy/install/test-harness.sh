#!/usr/bin/env bash
# Smoke-test the RPC surface an exchange integration depends on.
# Usage: ./test-harness.sh <rpc-url> <rpc-user> <rpc-pass-file>
# Exits non-zero if any REQUIRED method is missing/broken. Read-only; safe against a live node.
set -uo pipefail
URL="${1:-http://127.0.0.1:18332/}"; USER="${2:-sostrpc}"; PASSFILE="${3:?rpc pass file required}"
PASS="$(cat "$PASSFILE")"
ok=0; bad=0

call() { # method params_json
  curl -s --max-time 15 -u "$USER:$PASS" -H 'Content-Type: application/json' \
    --data "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"$1\",\"params\":${2:-[]}}" "$URL"
}
check() { # label method params expect-substring
  local r; r="$(call "$2" "${3:-[]}")"
  if echo "$r" | grep -q '"result"' && ! echo "$r" | grep -q '"error":{'; then
    echo "  OK   $1 ($2)"; ok=$((ok+1)); LAST="$r"
  else
    echo "  FAIL $1 ($2): $(echo "$r" | head -c 160)"; bad=$((bad+1)); LAST="$r"
  fi
}

echo "== SOST exchange RPC smoke test =="
check "liveness"        getinfo
check "tip height"      getblockcount
HEIGHT="$(echo "$LAST" | grep -oE '"result":[0-9]+' | grep -oE '[0-9]+' | head -1)"
check "best hash"       getbestblockhash
check "block hash @tip" getblockhash "[${HEIGHT:-0}]"
BH="$(echo "$LAST" | grep -oE '"result":"[0-9a-f]+"' | grep -oE '[0-9a-f]{6,}' | head -1)"
[ -n "${BH:-}" ] && check "get block"    getblock "[\"$BH\"]"
check "mempool info"    getmempoolinfo
check "supply info"     getsupplyinfo
check "estimate fee"    estimatefee
check "new address"     getnewaddress
ADDR="$(echo "$LAST" | grep -oE '"result":"sost1[0-9a-z]+"' | grep -oE 'sost1[0-9a-z]+' | head -1)"
[ -n "${ADDR:-}" ] && check "validate address" validateaddress "[\"$ADDR\"]"
[ -n "${ADDR:-}" ] && check "address info"      getaddressinfo   "[\"$ADDR\"]"
[ -n "${ADDR:-}" ] && check "address utxos"     getaddressutxos  "[\"$ADDR\"]"

echo "== $ok ok / $bad fail =="
[ "$bad" -eq 0 ]
