#!/bin/bash
# decrypt_secrets.sh — Temporarily decrypt secret files for use
# Decrypted files go to /tmp/sost_secrets/ (cleared on reboot)
#
# Usage:
#   bash scripts/decrypt_secrets.sh                  # decrypt all
#   bash scripts/decrypt_secrets.sh --auto-cleanup   # decrypt, use, then destroy
set -e

SECRETS_DIR="$HOME/SOST/secrets"
TMP_DIR="/tmp/sost_secrets"
AUTO_CLEANUP=false

if [ "$1" = "--auto-cleanup" ]; then
    AUTO_CLEANUP=true
fi

echo "============================================"
echo "  SOST Secrets Decryption (Temporary)"
echo "============================================"
echo ""
echo "Decrypted files will be placed in: $TMP_DIR"
if $AUTO_CLEANUP; then
    echo "Auto-cleanup: files will be destroyed after 5 minutes"
fi
echo ""

read -sp "Enter decryption password: " PASS
echo ""

mkdir -p "$TMP_DIR"
chmod 700 "$TMP_DIR"

COUNT=0

for f in "$SECRETS_DIR"/*.json.enc "$SECRETS_DIR"/regenesis/*.json.enc; do
    [ -f "$f" ] || continue

    BASENAME=$(basename "$f" .enc)
    OUTFILE="$TMP_DIR/$BASENAME"

    if openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
        -in "$f" -out "$OUTFILE" -pass "pass:$PASS" 2>/dev/null; then
        chmod 600 "$OUTFILE"
        echo "  ✓ Decrypted: $BASENAME → $OUTFILE"
        COUNT=$((COUNT + 1))
    else
        echo "  ✗ FAILED: $BASENAME (wrong password or corrupted file)"
        rm -f "$OUTFILE"
    fi
done

echo ""
echo "============================================"
echo "  $COUNT file(s) decrypted to $TMP_DIR"
echo "============================================"

if $AUTO_CLEANUP; then
    echo ""
    echo "Auto-cleanup in 5 minutes..."
    echo "Press Ctrl+C to cancel cleanup and keep files."
    sleep 300
    echo "Cleaning up..."
    shred -vfz -n 1 "$TMP_DIR"/*.json 2>/dev/null
    rm -rf "$TMP_DIR"
    echo "Temporary secrets destroyed."
else
    echo ""
    echo "REMEMBER: Delete these files when done!"
    echo "  shred -vfz $TMP_DIR/*.json && rm -rf $TMP_DIR"
fi
