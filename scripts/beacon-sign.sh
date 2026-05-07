#!/usr/bin/env bash
# beacon-sign.sh — sign a SOST Beacon notice with the operator's private key.
#
# Usage:
#   scripts/beacon-sign.sh <priv.pem> <unsigned.json> <signed_out.json>
#
# The unsigned notice MUST follow the Phase 1 schema (see docs/beacon.md):
#   notice_id, network, severity, title_en, message_en,
#   activation_height, expires_height, created_at, commands
#
# A "signature" field, if present in the input, must be empty ("") — this
# script REFUSES to re-sign an already-signed notice (defensive).
#
# Canonical payload = jq -cS over (input minus the signature field).
# Signature = base64(ECDSA-SHA256(canonical_payload, priv_key)) on secp256k1.
#
# Output JSON merges the signature back: signed_notice = canonical_payload
#                                       with "signature" = base64_sig.

set -euo pipefail

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <priv.pem> <unsigned.json> <signed_out.json>" >&2
    exit 64
fi

PRIV="$1"
UNSIGNED="$2"
OUT="$3"

[[ -r "$PRIV"     ]] || { echo "Cannot read private key: $PRIV" >&2; exit 1; }
[[ -r "$UNSIGNED" ]] || { echo "Cannot read unsigned notice: $UNSIGNED" >&2; exit 1; }

# Validate input is JSON object
if ! jq -e 'type == "object"' "$UNSIGNED" >/dev/null 2>&1; then
    echo "Input is not a JSON object: $UNSIGNED" >&2
    exit 2
fi

# Defensive: refuse to re-sign a notice that already has a non-empty signature
EXISTING_SIG=$(jq -r '.signature // ""' "$UNSIGNED")
if [[ -n "$EXISTING_SIG" ]]; then
    echo "Refusing to re-sign: input already has a non-empty 'signature' field." >&2
    echo "If you must re-issue, edit the JSON first and remove or empty 'signature'." >&2
    exit 3
fi

# Validate required fields are present (Phase 1 schema)
REQUIRED_FIELDS=(notice_id network severity title_en message_en activation_height expires_height created_at commands)
for f in "${REQUIRED_FIELDS[@]}"; do
    if ! jq -e --arg k "$f" 'has($k)' "$UNSIGNED" >/dev/null; then
        echo "Missing required field in notice: $f" >&2
        exit 2
    fi
done

# Build canonical payload: drop signature field, sort keys recursively,
# compact form, NO trailing newline (-j). The browser verifier produces the
# same byte sequence via canonicalize(); a trailing newline would diverge.
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

jq -cSj 'del(.signature)' "$UNSIGNED" > "$TMP/payload.canonical"

# Sign canonical payload with ECDSA-SHA256
openssl dgst -sha256 -sign "$PRIV" -out "$TMP/sig.bin" "$TMP/payload.canonical"

# Base64 encode signature (single line, no wrapping)
SIG_B64=$(base64 -w 0 < "$TMP/sig.bin")

# Output: canonical payload merged with signature field
jq -cS --arg sig "$SIG_B64" '. + {signature: $sig}' "$TMP/payload.canonical" > "$OUT"

echo "Signed notice written to: $OUT"
echo "Signature (base64): $SIG_B64"
