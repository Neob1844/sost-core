#!/usr/bin/env bash
# beacon-keygen.sh — generate a passphrase-encrypted secp256k1 keypair for
# SOST Beacon notices.
#
# This is run ONCE by the operator to create the Beacon signing identity.
# The private key:
#   - is generated in /dev/shm (RAM tmpfs) so the unencrypted form never
#     touches persistent storage,
#   - is then re-written to disk encrypted with AES-256, with the
#     passphrase prompted interactively on the tty,
#   - NEVER touches the repo.
# Only the public key is committed.
#
# Usage:
#   scripts/beacon-keygen.sh <priv_out.pem> <pub_out.pem>
#
# Example:
#   scripts/beacon-keygen.sh ~/secrets/beacon-priv.pem website/api/beacon-pub.pem
#
# The script REFUSES to overwrite existing files (safety against accidental
# key destruction).
#
# Operator workflow:
#   1. Run on an air-gapped machine.
#   2. openssl will prompt for the passphrase three times per invocation:
#        a) set the passphrase (encrypt the private key),
#        b) confirm the passphrase,
#        c) read the encrypted private key in order to derive the public key.
#      Use a strong passphrase (>= 20 chars, ideally a diceware passphrase),
#      DIFFERENT for every key, and stored SEPARATELY from the .pem file.
#   3. Move the encrypted .pem to an encrypted USB. Back up to a second
#      encrypted USB in a different physical location.
#   4. NEVER paste the .pem (encrypted or not) into chat, email, GitHub,
#      docs, comments, or the repo.

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

# Generate the private key in RAM tmpfs (no persistent storage of the
# unencrypted form). /dev/shm is required; on systems without it we abort
# rather than fall back to /tmp (which is on-disk on many distros).
if [[ ! -d /dev/shm || ! -w /dev/shm ]]; then
    echo "FATAL: /dev/shm not available/writable — refuse to generate" >&2
    echo "       an unencrypted intermediate private key on persistent disk." >&2
    exit 2
fi

TMP_PLAIN=$(mktemp /dev/shm/beacon-keygen.XXXXXX)
# Shred + remove the intermediate on ANY exit path. Belt and suspenders.
cleanup() {
    if [[ -f "$TMP_PLAIN" ]]; then
        # shred -u zeroes + unlinks. Falls back to rm if shred missing.
        shred -u "$TMP_PLAIN" 2>/dev/null || rm -f "$TMP_PLAIN"
    fi
}
trap cleanup EXIT INT TERM

echo
echo "Generating secp256k1 keypair. You will be prompted for a passphrase"
echo "THREE times: (1) set, (2) confirm, (3) read to derive public key."
echo "Use a STRONG passphrase (>= 20 chars). Different per key. Stored"
echo "SEPARATELY from the .pem file."
echo

# Step 1: generate raw private key into RAM tmpfs.
openssl ecparam -name secp256k1 -genkey -noout -out "$TMP_PLAIN"

# Step 2: re-write the private key encrypted with AES-256. openssl prompts
# for the passphrase twice (set + confirm) on the tty.
openssl ec -in "$TMP_PLAIN" -aes256 -out "$PRIV"

# Step 3: derive the public key from the now-encrypted private key.
# openssl prompts for the passphrase once more (read).
openssl ec -in "$PRIV" -pubout -out "$PUB" >/dev/null 2>&1

# Lock down file permissions even though the private key is encrypted.
chmod 600 "$PRIV"
chmod 644 "$PUB"

# Print fingerprint for cross-channel verification (BCT, GitHub README, etc.)
PUB_HEX=$(openssl ec -pubin -in "$PUB" -text -noout 2>/dev/null \
    | awk '/pub:/{flag=1;next} /ASN1/{flag=0} flag' \
    | tr -d ' :\n')
PUB_FP=$(printf '%s' "$PUB_HEX" | sha256sum | awk '{print $1}')

echo
echo "Beacon keypair generated:"
echo "  private key : $PRIV  (mode 600, AES-256 ENCRYPTED — keep SECRET)"
echo "  public  key : $PUB   (commit this to repo)"
echo
echo "Public key fingerprint (sha256 of uncompressed pubkey hex):"
echo "  $PUB_FP"
echo
echo "Uncompressed public key (hex, 65 bytes — embed in src/beacon.cpp"
echo "as BEACON_PUBKEY_HEX or as one entry of BEACON_THRESHOLD_PUBKEYS):"
echo "  $PUB_HEX"
echo
echo "Publish this fingerprint in MULTIPLE channels for cross-validation:"
echo "  - GitHub README"
echo "  - sostprotocol.com / sostcore.com index"
echo "  - BCT thread"
echo "  - Whitepaper"
echo
echo "Reminder: the private key is encrypted with the passphrase you"
echo "just set. Store the passphrase SEPARATELY from the .pem file. If"
echo "you lose the passphrase, this key becomes a brick — regenerate."
