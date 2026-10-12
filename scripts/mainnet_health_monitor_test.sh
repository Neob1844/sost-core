#!/usr/bin/env bash
# mainnet_health_monitor_test.sh — unit test for the mainnet health monitor's
# DETECTION CORE (ops/mainnet_health_detect.py).
#
# It feeds the detector SYNTHETIC combined snapshots — it NEVER touches a real
# node, never opens a socket, never SSHes anywhere — and asserts that the
# correct conditions are labelled:
#
#   1. tip divergence      -> TIP_DIVERGENCE
#   2. a stalled node      -> HEIGHT_STALL
#   3. an unavailable obs.  -> NODE_DOWN
#   plus a healthy "agree" case asserts NO alert (no false positives),
#   and a peer-drop case asserts PEER_DROP.
#
# Exit 0 = all PASS, 1 = any FAIL.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DETECT="$HERE/../ops/mainnet_health_detect.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0; FAIL=0
run() { printf '%s' "$1" | python3 "$DETECT" --snapshot - --json 2>/dev/null; }

# assert_has <label> <json> <CODE...>  : every CODE must appear in conditions
assert_has() {
  local label="$1" json="$2"; shift 2
  local ok=1 code
  for code in "$@"; do
    if ! grep -q "\"$code\"" <<<"$json"; then ok=0; echo "  MISSING: $code"; fi
  done
  if [ "$ok" -eq 1 ]; then echo "PASS: $label"; PASS=$((PASS+1));
  else echo "FAIL: $label"; FAIL=$((FAIL+1)); fi
}
# assert_no_alert <label> <json>
assert_no_alert() {
  local label="$1" json="$2"
  if grep -q '"alert": false' <<<"$json"; then echo "PASS: $label"; PASS=$((PASS+1));
  else echo "FAIL: $label (expected alert=false)"; echo "$json" | head -20; FAIL=$((FAIL+1)); fi
}
# assert_not_has <label> <json> <CODE>
assert_not_has() {
  local label="$1" json="$2" code="$3"
  if grep -q "\"$code\"" <<<"$json"; then echo "FAIL: $label ($code should NOT fire)"; FAIL=$((FAIL+1));
  else echo "PASS: $label"; PASS=$((PASS+1)); fi
}

echo "==================== MONITOR DETECTION TESTS ===================="
[ -f "$DETECT" ] || { echo "FAIL: detector missing at $DETECT"; exit 1; }

# -- Scenario A: healthy, both observers agree -> NO alert --------------------
A='{"ts":"T","thresholds":{"stall_secs":1800,"min_peers":1,"max_height_gap":2},
"observers":[
 {"observer":"LOCAL","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","chainwork":null,"last_block_age_secs":120,"peers":2,"mempool":0,"version":"0.3.2"},
 {"observer":"STRATO","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","chainwork":null,"last_block_age_secs":121,"peers":3,"mempool":0,"version":"0.3.2"}]}'
OUT_A="$(run "$A")"
assert_no_alert "A healthy/agree -> no alert" "$OUT_A"
assert_not_has  "A no false TIP_DIVERGENCE"  "$OUT_A" "TIP_DIVERGENCE"

# -- Scenario B: TIP DIVERGENCE (same height, different tip hash) -------------
B='{"ts":"T","thresholds":{"stall_secs":1800,"min_peers":1,"max_height_gap":2},
"observers":[
 {"observer":"LOCAL","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa1111","chainwork":"0x10","last_block_age_secs":100,"peers":2,"version":"0.3.2"},
 {"observer":"STRATO","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"bbbb2222","chainwork":"0x11","last_block_age_secs":100,"peers":2,"version":"0.3.2"}]}'
OUT_B="$(run "$B")"
assert_has "B tip divergence -> TIP_DIVERGENCE + CHAINWORK_DIVERGENCE" "$OUT_B" TIP_DIVERGENCE CHAINWORK_DIVERGENCE

# -- Scenario C: HEIGHT STALL (tip older than stall window) -------------------
C='{"ts":"T","thresholds":{"stall_secs":1800,"min_peers":1,"max_height_gap":2},
"observers":[
 {"observer":"LOCAL","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","chainwork":null,"last_block_age_secs":4200,"peers":2,"version":"0.3.2"},
 {"observer":"STRATO","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","chainwork":null,"last_block_age_secs":4200,"peers":2,"version":"0.3.2"}]}'
OUT_C="$(run "$C")"
assert_has "C stalled node -> HEIGHT_STALL" "$OUT_C" HEIGHT_STALL

# -- Scenario D: UNAVAILABLE OBSERVER -> NODE_DOWN ----------------------------
D='{"ts":"T","thresholds":{"stall_secs":1800,"min_peers":1,"max_height_gap":2},
"observers":[
 {"observer":"LOCAL","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","last_block_age_secs":100,"peers":2,"version":"0.3.2"},
 {"observer":"STRATO","reachable":false,"rpc_alive":false,"node_alive":false,"height":null,"tip_hash":null,"error":"SSH unavailable"}]}'
OUT_D="$(run "$D")"
assert_has "D unavailable observer -> NODE_DOWN" "$OUT_D" NODE_DOWN

# -- Scenario E: RPC up but transport reached, RPC failed -> RPC_FAILURE ------
E='{"ts":"T","thresholds":{"stall_secs":1800,"min_peers":1,"max_height_gap":2},
"observers":[
 {"observer":"LOCAL","reachable":true,"rpc_alive":false,"node_alive":false,"height":null,"error":"RPC degraded"},
 {"observer":"STRATO","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","last_block_age_secs":100,"peers":2,"version":"0.3.2"}]}'
OUT_E="$(run "$E")"
assert_has "E rpc failure -> RPC_FAILURE + NODE_DOWN" "$OUT_E" RPC_FAILURE NODE_DOWN

# -- Scenario F: PEER DROP ----------------------------------------------------
F='{"ts":"T","thresholds":{"stall_secs":1800,"min_peers":2,"max_height_gap":2},
"observers":[
 {"observer":"LOCAL","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","last_block_age_secs":100,"peers":0,"version":"0.3.2"},
 {"observer":"STRATO","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","last_block_age_secs":100,"peers":3,"version":"0.3.2"}]}'
OUT_F="$(run "$F")"
assert_has "F low peers -> PEER_DROP" "$OUT_F" PEER_DROP

# -- Scenario G: OLD VERSION --------------------------------------------------
G='{"ts":"T","thresholds":{"stall_secs":1800,"min_peers":1,"max_height_gap":2,"expected_version":"0.3.2"},
"observers":[
 {"observer":"LOCAL","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","last_block_age_secs":100,"peers":2,"version":"0.3.1"},
 {"observer":"STRATO","reachable":true,"rpc_alive":true,"node_alive":true,"height":29045,"tip_hash":"aaaa","last_block_age_secs":100,"peers":2,"version":"0.3.2"}]}'
OUT_G="$(run "$G")"
assert_has "G old version -> OLD_VERSION" "$OUT_G" OLD_VERSION

echo "----------------------------------------------------------------"
echo "RESULT: $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ] && { echo "ALL TESTS PASS"; exit 0; } || { echo "SOME TESTS FAILED"; exit 1; }
