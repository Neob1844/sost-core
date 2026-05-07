#!/usr/bin/env bash
# beacon-keygen.sh — generate a dedicated secp256k1 keypair for SOST Beacon notices
#
# This is run ONCE by the operator to create the Beacon signing identity.
# The private key NEVER touches the repo. Only the public key is committed.
#
# Usage:
#   scripts/beacon-keygen.sh <priv_out.pem> <pub_out.pem>
#
# Example:
#   scripts/beacon-keygen.sh ~/secrets/beacon-priv.pem website/api/beacon-pub.pem
#
# The script REFUSES to overwrite existing files (safety against accidental
# key destruction).

set -euo pipefail

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <priv_out.pem> <pub_out.pem>" >&2
    exit 64
fi

PRIV="$1"
PUB="$2"

if [[ -e "$PRIV" ]]; then
    echo "Refusing to overwrite existing private key: $PRIV" >&2
    exit 1
fi
if [[ -e "$PUB" ]]; then
    echo "Refusing to overwrite existing public key: $PUB" >&2
    exit 1
fi

# Ensure parent directories exist before openssl writes
mkdir -p "$(dirname "$PRIV")" "$(dirname "$PUB")"

# Generate secp256k1 private key (same curve as SOST consensus, off-chain use)
openssl ecparam -name secp256k1 -genkey -noout -out "$PRIV"

# Derive public key
openssl ec -in "$PRIV" -pubout -out "$PUB" >/dev/null 2>&1

# Lock down private key permissions
chmod 600 "$PRIV"
chmod 644 "$PUB"

# Print fingerprint for cross-channel verification (BCT, GitHub README, etc.)
PUB_HEX=$(openssl ec -pubin -in "$PUB" -text -noout 2>/dev/null \
    | awk '/pub:/{flag=1;next} /ASN1/{flag=0} flag' \
    | tr -d ' :\n')
PUB_FP=$(printf '%s' "$PUB_HEX" | sha256sum | awk '{print $1}')

echo "Beacon keypair generated:"
echo "  private key : $PRIV  (mode 600 — keep SECRET)"
echo "  public  key : $PUB   (commit this to repo)"
echo
echo "Public key fingerprint (sha256 of uncompressed pubkey hex):"
echo "  $PUB_FP"
echo
echo "Uncompressed public key (hex, 65 bytes — embed in website/js/beacon.js"
echo "as BEACON_PUBKEY_HEX):"
echo "  $PUB_HEX"
echo
echo "Publish this fingerprint in MULTIPLE channels for cross-validation:"
echo "  - GitHub README"
echo "  - sostprotocol.com index"
echo "  - BCT thread"
echo "  - Whitepaper"
