#!/usr/bin/env bash
# beacon-vendor-fetch.sh — reproducible vendoring of the noble-secp256k1
# library used by the SOST Beacon explorer banner.
#
# This script ONLY runs in two scenarios:
#   1. Bootstrapping the vendor directory in a fresh checkout that does not
#      yet have the file (rare).
#   2. Deliberately bumping the pinned version (manual edit of VERSION /
#      EXPECTED_HASH below).
#
# Normal users do NOT need to run it — the vendored file is committed to
# the repo. CI integrity is enforced by `sha256sum -c website/vendor/HASHES.txt`.
#
# The script REFUSES to overwrite the existing vendored file unless the
# downloaded content matches the pinned hash exactly.

set -euo pipefail

VERSION="2.2.3"
EXPECTED_HASH="45f34003f752401c860347182c0bce4e7d0306cbf6aac70b17593ee70deaeaec"
SOURCE_URL="https://cdn.jsdelivr.net/npm/@noble/secp256k1@${VERSION}/index.js"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENDOR_DIR="${REPO_ROOT}/website/vendor"
TARGET="${VENDOR_DIR}/noble-secp256k1-${VERSION}.js"

mkdir -p "$VENDOR_DIR"

echo "Fetching @noble/secp256k1@${VERSION}"
echo "  from: ${SOURCE_URL}"
echo "  to:   ${TARGET}"

TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT

curl --fail --silent --show-error --location --connect-timeout 10 \
    --max-time 30 -o "$TMP" "$SOURCE_URL"

ACTUAL_HASH=$(sha256sum "$TMP" | awk '{print $1}')

if [[ "$ACTUAL_HASH" != "$EXPECTED_HASH" ]]; then
    echo "Hash mismatch — refusing to vendor potentially compromised file." >&2
    echo "  expected: $EXPECTED_HASH" >&2
    echo "  actual:   $ACTUAL_HASH" >&2
    echo >&2
    echo "If this is an intentional upgrade, manually update VERSION and" >&2
    echo "EXPECTED_HASH in this script after auditing the upstream diff." >&2
    exit 1
fi

# Refuse to silently overwrite a different pinned file
if [[ -e "$TARGET" ]]; then
    EXISTING_HASH=$(sha256sum "$TARGET" | awk '{print $1}')
    if [[ "$EXISTING_HASH" == "$EXPECTED_HASH" ]]; then
        echo "Vendor file already present and matches pin — nothing to do."
        exit 0
    fi
    echo "Refusing to overwrite existing $TARGET (hash differs from pin)." >&2
    echo "Delete the file manually if you really intend to replace it." >&2
    exit 1
fi

mv "$TMP" "$TARGET"
chmod 644 "$TARGET"

echo "Vendored OK (sha256 = $EXPECTED_HASH)"
echo
echo "Reminder: update website/vendor/HASHES.txt if this is a version bump."
