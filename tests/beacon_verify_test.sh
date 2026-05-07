#!/usr/bin/env bash
# beacon_verify_test.sh — adversarial tests for the SOST Beacon scripts.
#
# Runs 7 cases. ALL must pass before any explorer/website integration ships.
# A passing run prints "ALL TESTS PASSED" and exits 0. Any failure halts
# at the offending case with details.
#
# Usage:
#   tests/beacon_verify_test.sh

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "$0")/.." && pwd)/scripts"
KEYGEN="$SCRIPTS_DIR/beacon-keygen.sh"
SIGN="$SCRIPTS_DIR/beacon-sign.sh"
VERIFY="$SCRIPTS_DIR/beacon-verify.sh"

for s in "$KEYGEN" "$SIGN" "$VERIFY"; do
    [[ -x "$s" ]] || { echo "Missing or non-executable: $s" >&2; exit 2; }
done

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PASS=0
FAIL=0

pass() { echo "  PASS — $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL — $1" >&2; FAIL=$((FAIL+1)); echo; echo "STOPPED at first failure." >&2; exit 1; }

echo "=== Beacon adversarial verification suite ==="
echo

# Generate two distinct key pairs:
#   A = the legitimate Beacon key
#   B = an attacker's key
"$KEYGEN" "$WORK/priv-A.pem" "$WORK/pub-A.pem" >/dev/null
"$KEYGEN" "$WORK/priv-B.pem" "$WORK/pub-B.pem" >/dev/null

# Build a canonical unsigned notice (Phase 1 schema)
cat > "$WORK/notice.unsigned.json" <<'EOF'
{
  "notice_id": "beacon-test-001",
  "network": "mainnet",
  "severity": "info",
  "title_en": "Test notice",
  "message_en": "This is a test of the Beacon verification path.",
  "activation_height": 7500,
  "expires_height": 7900,
  "created_at": "2026-05-07T00:00:00Z",
  "commands": [],
  "signature": ""
}
EOF

# Sign with key A (legitimate)
"$SIGN" "$WORK/priv-A.pem" "$WORK/notice.unsigned.json" "$WORK/notice.A.signed.json" >/dev/null

# ----------------------------------------------------------------------------
# Test 1 — valid signature against the correct pubkey MUST be ACCEPTED
# ----------------------------------------------------------------------------
echo "Test 1: valid signature with correct pubkey -> expect ACCEPT"
if "$VERIFY" "$WORK/pub-A.pem" "$WORK/notice.A.signed.json" >/dev/null 2>&1; then
    pass "valid signature accepted"
else
    fail "valid signature was REJECTED (verify path is broken — would reject all real notices)"
fi

# ----------------------------------------------------------------------------
# Test 2 — fabricated/random signature MUST be REJECTED
# ----------------------------------------------------------------------------
echo "Test 2: fabricated signature -> expect REJECT"
# Build a notice with a syntactically valid but fake signature
FAKE_SIG=$(head -c 64 /dev/urandom | base64 -w 0)
jq -cS --arg sig "$FAKE_SIG" 'del(.signature) + {signature: $sig}' "$WORK/notice.unsigned.json" \
    > "$WORK/notice.fake.json"
if "$VERIFY" "$WORK/pub-A.pem" "$WORK/notice.fake.json" >/dev/null 2>&1; then
    fail "fabricated signature was ACCEPTED (CRITICAL: phishing vector — verify always-accepts)"
else
    pass "fabricated signature rejected"
fi

# ----------------------------------------------------------------------------
# Test 3 — missing signature field MUST be REJECTED
# ----------------------------------------------------------------------------
echo "Test 3: notice with no signature field -> expect REJECT"
jq -cS 'del(.signature)' "$WORK/notice.unsigned.json" > "$WORK/notice.nosig.json"
if "$VERIFY" "$WORK/pub-A.pem" "$WORK/notice.nosig.json" >/dev/null 2>&1; then
    fail "notice with no signature was ACCEPTED (CRITICAL: empty-sig bypass)"
else
    pass "missing signature rejected"
fi

# ----------------------------------------------------------------------------
# Test 4 — signature from a DIFFERENT key (attacker) MUST be REJECTED
# ----------------------------------------------------------------------------
echo "Test 4: signature from attacker's key, verified against legit pubkey -> expect REJECT"
"$SIGN" "$WORK/priv-B.pem" "$WORK/notice.unsigned.json" "$WORK/notice.B.signed.json" >/dev/null
if "$VERIFY" "$WORK/pub-A.pem" "$WORK/notice.B.signed.json" >/dev/null 2>&1; then
    fail "attacker-signed notice was ACCEPTED against legitimate pubkey (CRITICAL: any-key bypass)"
else
    pass "attacker-signed notice rejected"
fi

# ----------------------------------------------------------------------------
# Test 5 — message tampered AFTER signing MUST be REJECTED
# ----------------------------------------------------------------------------
echo "Test 5: tamper with message_en after signing -> expect REJECT"
jq -cS '.message_en = "TAMPERED — download evil binary from attacker.com"' \
    "$WORK/notice.A.signed.json" > "$WORK/notice.tampered.json"
if "$VERIFY" "$WORK/pub-A.pem" "$WORK/notice.tampered.json" >/dev/null 2>&1; then
    fail "tampered message was ACCEPTED (CRITICAL: signature does not bind payload)"
else
    pass "tampered message rejected"
fi

# ----------------------------------------------------------------------------
# Test 6 — malformed JSON MUST be rejected without crashing
# ----------------------------------------------------------------------------
echo "Test 6: malformed JSON -> expect REJECT (no crash)"
echo '{ this is not json' > "$WORK/notice.bad.json"
if "$VERIFY" "$WORK/pub-A.pem" "$WORK/notice.bad.json" >/dev/null 2>&1; then
    fail "malformed JSON was ACCEPTED"
else
    pass "malformed JSON rejected cleanly"
fi

# ----------------------------------------------------------------------------
# Test 7 — sign script REFUSES to re-sign already-signed notice
# ----------------------------------------------------------------------------
echo "Test 7: re-signing an already-signed notice -> expect FAIL fast"
if "$SIGN" "$WORK/priv-A.pem" "$WORK/notice.A.signed.json" "$WORK/should-not-exist.json" >/dev/null 2>&1; then
    fail "sign script silently re-signed an already-signed notice (defensive guard missing)"
else
    pass "sign script refused to re-sign"
fi

echo
echo "=========================================="
echo "Tests passed: $PASS"
echo "Tests failed: $FAIL"
if [[ $FAIL -eq 0 ]]; then
    echo "ALL TESTS PASSED"
    exit 0
else
    echo "FAILURES PRESENT — DO NOT SHIP"
    exit 1
fi
