#!/usr/bin/env bash
# sign-release.sh — produce a CRYPTOGRAPHIC AUTHENTICITY signature over a
# release's SHA256SUMS file.
#
# SHA256SUMS already gives INTEGRITY (did the bytes change?). This adds
# AUTHENTICITY (were these the bytes the SOST owner actually released?) by
# signing SHA256SUMS with the owner's private release key. Verifiers then
# check the detached signature against the PUBLIC key (scripts/verify-release.sh).
#
# ===== HARD KEY-SAFETY INVARIANTS =====
#   * This script NEVER generates, stores, copies, prints, or transmits a
#     private key. The operator supplies the private key path at RUNTIME
#     (argument or env). It is read by the signing tool only.
#   * No private key must EVER live in this repo, on the VPS, in logs, in CI,
#     or on GitHub. The owner holds it OFFLINE (encrypted USB / air-gapped).
#   * The signature is detached: the SHA256SUMS file is never modified.
#
# Backends (preferred first):
#   minisign  — tiny, modern Ed25519. Install: `apt install minisign`.
#   gpg       — if minisign is unavailable.
#
# Usage:
#   # minisign (preferred)
#   scripts/sign-release.sh --minisign <SHA256SUMS> <seckey_path>
#   #   env alt: SIGN_KEY=<seckey_path> scripts/sign-release.sh --minisign <SHA256SUMS>
#
#   # gpg
#   scripts/sign-release.sh --gpg <SHA256SUMS> [key-id-or-fingerprint]
#
# Output:
#   minisign -> <SHA256SUMS>.minisig   (detached)
#   gpg      -> <SHA256SUMS>.asc        (detached, ASCII-armored)
#
# Exit: 0 ok, 2 usage, 3 missing tool, 4 missing input, 5 signing failed.
set -uo pipefail

die() { echo "ERROR: $*" >&2; exit "${2:-2}"; }

[ $# -ge 2 ] || die "usage: $0 --minisign|--gpg <SHA256SUMS> [key]  (see header)" 2
BACKEND="$1"; shift
SUMS="$1"; shift
[ -r "$SUMS" ] || die "cannot read SHA256SUMS file: $SUMS" 4

# SAFETY: refuse to proceed if the SHA256SUMS path looks like it IS a key.
case "$SUMS" in
  *.key|*.pem|*secret*|*seckey*|*.sec) die "refusing: '$SUMS' looks like a key, not a SHA256SUMS file" 2 ;;
esac

case "$BACKEND" in
  --minisign)
    command -v minisign >/dev/null 2>&1 || die "minisign not installed (apt install minisign) — or use --gpg" 3
    KEY="${1:-${SIGN_KEY:-}}"
    [ -n "$KEY" ] || die "minisign needs a secret-key PATH (arg or SIGN_KEY env). This path is READ at runtime and never stored." 2
    [ -r "$KEY" ] || die "cannot read secret key at: $KEY" 4
    OUT="$SUMS.minisig"
    # -S sign, -s secret key, -m message, -x detached sig out.
    # minisign prompts for the key's passphrase on the TTY; we never echo it.
    if minisign -S -s "$KEY" -m "$SUMS" -x "$OUT"; then
      echo "OK: wrote detached minisign signature -> $OUT"
      echo "Publish $OUT next to $SUMS. Verify with scripts/verify-release.sh --minisign $SUMS <pubkey>"
    else
      die "minisign signing failed" 5
    fi
    ;;
  --gpg)
    command -v gpg >/dev/null 2>&1 || die "gpg not installed — or use --minisign" 3
    KEYID="${1:-${SIGN_KEY:-}}"   # optional: specific signing identity
    OUT="$SUMS.asc"
    # --detach-sign --armor; gpg selects the secret key from the operator's
    # OFFLINE keyring (never from this repo). -u pins the identity if given.
    if [ -n "$KEYID" ]; then
      gpg --batch --yes --armor -u "$KEYID" --detach-sign -o "$OUT" "$SUMS"
    else
      gpg --batch --yes --armor --detach-sign -o "$OUT" "$SUMS"
    fi
    [ -f "$OUT" ] || die "gpg signing failed (no $OUT produced)" 5
    echo "OK: wrote detached GPG signature -> $OUT"
    echo "Publish $OUT next to $SUMS. Verify with scripts/verify-release.sh --gpg $SUMS <public_key.asc>"
    ;;
  *) die "unknown backend '$BACKEND' (use --minisign or --gpg)" 2 ;;
esac
