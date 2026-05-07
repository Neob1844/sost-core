#!/usr/bin/env bash
# beacon_cross_verify_test.sh — adversarial cross-fixture test:
# a notice signed by the shell pipeline (beacon-keygen.sh + beacon-sign.sh)
# MUST verify under the same JavaScript path that the explorer browser
# loads (website/js/beacon.js). Any divergence between shell and browser
# verification is a P0 trust failure.
#
# Pre-reqs: bash, jq, openssl, node (>= 18).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="$REPO_ROOT/scripts"
JSHARNESS="$REPO_ROOT/tests/beacon_cross_verify.mjs"
VENDOR="$REPO_ROOT/website/vendor/noble-secp256k1-2.2.3.js"
HASHES="$REPO_ROOT/website/vendor/HASHES.txt"

for s in "$SCRIPTS/beacon-keygen.sh" "$SCRIPTS/beacon-sign.sh"; do
    [[ -x "$s" ]] || { echo "Missing or non-executable: $s" >&2; exit 2; }
done
[[ -r "$JSHARNESS" ]] || { echo "Missing JS harness: $JSHARNESS" >&2; exit 2; }
[[ -r "$VENDOR"    ]] || { echo "Missing vendored library: $VENDOR" >&2; exit 2; }

# Vendor integrity gate — refuse to run if the pin has drifted.
echo "=== Vendor integrity check ==="
( cd "$REPO_ROOT/website/vendor" && sha256sum -c HASHES.txt )
echo

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# 1. Generate a fresh keypair on the spot. The hex pubkey is harvested from
#    keygen output — the same value the operator would paste into
#    BEACON_PUBKEY_HEX in production.
"$SCRIPTS/beacon-keygen.sh" "$WORK/priv.pem" "$WORK/pub.pem" > "$WORK/keygen.out"
PUB_HEX=$(awk '/Uncompressed public key/{getline; getline; gsub(/^ +/,""); print; exit}' "$WORK/keygen.out")
[[ -n "$PUB_HEX" ]] || { echo "Could not extract pubkey hex from keygen output" >&2; exit 2; }
echo "Generated test pubkey hex: ${PUB_HEX:0:32}…"

# 2. Build a representative Phase 1 notice (un-signed).
cat > "$WORK/notice.unsigned.json" <<'EOF'
{
  "notice_id": "x-cross-verify-test-001",
  "network": "mainnet",
  "severity": "info",
  "title_en": "Cross-fixture test notice",
  "message_en": "If you see this banner the JS path matches the shell path.",
  "activation_height": 7500,
  "expires_height": 7900,
  "created_at": "2026-05-07T00:00:00Z",
  "commands": [],
  "signature": ""
}
EOF

# 3. Sign with the shell pipeline.
"$SCRIPTS/beacon-sign.sh" "$WORK/priv.pem" "$WORK/notice.unsigned.json" "$WORK/signed.json" >/dev/null

# 4. Materialise the canonical payload the way `jq -cS` produces it. The JS
#    canonicalize() output must match this byte-for-byte.
jq -cS 'del(.signature)' "$WORK/signed.json" > "$WORK/canonical.ref"

# 5. Hand off to the JS harness — it loads the same beacon.js the browser
#    loads and runs the adversarial cases.
echo
echo "=== Cross-fixture verification (Node) ==="
node "$JSHARNESS" "$PUB_HEX" "$WORK/signed.json" "$WORK/canonical.ref"
