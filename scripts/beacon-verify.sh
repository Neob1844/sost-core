#!/usr/bin/env bash
# beacon-verify.sh — verify a signed SOST Beacon notice against a public key.
#
# Usage:
#   scripts/beacon-verify.sh <pub.pem> <signed.json>
#
# Exit codes:
#   0  signature valid
#   1  signature invalid (rejected)
#   2  malformed input (cannot parse / missing fields)
#  64  bad usage
#
# This script is the SAME algorithm the browser uses. If openssl says OK
# here, the explorer should also say OK. The shell tests in
# tests/beacon_verify_test.sh exercise the four adversarial cases.

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <pub.pem> <signed.json>" >&2
    exit 64
fi

PUB="$1"
NOTICE="$2"

[[ -r "$PUB"    ]] || { echo "Cannot read public key: $PUB" >&2; exit 2; }
[[ -r "$NOTICE" ]] || { echo "Cannot read notice: $NOTICE" >&2; exit 2; }

# Validate input is a JSON object
if ! jq -e 'type == "object"' "$NOTICE" >/dev/null 2>&1; then
    echo "Notice is not a JSON object" >&2
    exit 2
fi

# Extract signature; require it to be present and non-empty
SIG_B64=$(jq -r '.signature // ""' "$NOTICE")
if [[ -z "$SIG_B64" ]]; then
    echo "REJECTED: missing or empty signature field" >&2
    exit 1
fi

# Build canonical payload (everything except signature, sorted keys, compact,
# NO trailing newline — must be byte-identical to what beacon-sign.sh signed
# and what the browser canonicalize() produces).
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

jq -cSj 'del(.signature)' "$NOTICE" > "$TMP/payload.canonical"

# Decode signature (base64 -> raw bytes); fail-closed on bad encoding
if ! printf '%s' "$SIG_B64" | base64 -d > "$TMP/sig.bin" 2>/dev/null; then
    echo "REJECTED: signature is not valid base64" >&2
    exit 1
fi

# Verify; openssl exits non-zero on bad signature, also writes "Verification Failure" to stderr
if openssl dgst -sha256 -verify "$PUB" -signature "$TMP/sig.bin" "$TMP/payload.canonical" >/dev/null 2>&1; then
    echo "OK"
    exit 0
else
    echo "REJECTED: signature does not match public key for this payload" >&2
    exit 1
fi
