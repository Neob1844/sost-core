#!/bin/bash
# encrypt_secrets.sh — Encrypt all secret files with AES-256-CBC + PBKDF2
# The original plaintext files are securely destroyed with shred.
#
# Usage: bash scripts/encrypt_secrets.sh
set -e

SECRETS_DIR="$HOME/SOST/secrets"

if [ ! -d "$SECRETS_DIR" ]; then
    echo "ERROR: $SECRETS_DIR not found"
    exit 1
fi

echo "============================================"
echo "  SOST Secrets Encryption"
echo "============================================"
echo ""
echo "This will encrypt ALL .json files in:"
echo "  $SECRETS_DIR/"
echo "  $SECRETS_DIR/regenesis/"
echo ""
echo "Original plaintext files will be DESTROYED (shred)."
echo ""

read -sp "Enter encryption password: " PASS
echo ""
read -sp "Confirm password: " PASS2
echo ""

if [ "$PASS" != "$PASS2" ]; then
    echo "ERROR: Passwords do not match"
    exit 1
fi

if [ ${#PASS} -lt 8 ]; then
    echo "ERROR: Password must be at least 8 characters"
    exit 1
fi

COUNT=0

for f in "$SECRETS_DIR"/*.json "$SECRETS_DIR"/regenesis/*.json; do
    [ -f "$f" ] || continue

    BASENAME=$(basename "$f")
    ENCFILE="${f}.enc"

    echo "  Encrypting: $BASENAME"
    openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
        -in "$f" -out "$ENCFILE" -pass "pass:$PASS"

    # Verify the encrypted file can be decrypted
    TESTOUT=$(mktemp)
    if openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
        -in "$ENCFILE" -out "$TESTOUT" -pass "pass:$PASS" 2>/dev/null; then
        # Compare
        if diff -q "$f" "$TESTOUT" > /dev/null 2>&1; then
            echo "    ✓ Verified: decryption matches original"
            # Securely destroy the original
            shred -vfz -n 3 "$f" 2>/dev/null && rm -f "$f"
            echo "    ✓ Original destroyed (shred)"
            COUNT=$((COUNT + 1))
        else
            echo "    ✗ ERROR: decryption mismatch! Keeping original."
            rm -f "$ENCFILE"
        fi
    else
        echo "    ✗ ERROR: decryption failed! Keeping original."
        rm -f "$ENCFILE"
    fi
    rm -f "$TESTOUT"
done

echo ""
echo "============================================"
echo "  $COUNT file(s) encrypted and originals destroyed"
echo "  Encrypted files: *.json.enc"
echo "============================================"
echo ""
echo "To decrypt later: bash scripts/decrypt_secrets.sh"
