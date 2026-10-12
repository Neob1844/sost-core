#!/usr/bin/env bash
# verify-release.sh — verify a release's SHA256SUMS authenticity against the
# SOST PUBLIC release key, and (optionally) verify the binaries' integrity
# against SHA256SUMS.
#
# This is the script a third party runs. It needs ONLY public material:
#   - the SHA256SUMS file,
#   - its detached signature (.minisig or .asc),
#   - the SOST public key.
# It never needs — and must never be given — any private key.
#
# Backends:
#   minisign -> verify <SHA256SUMS>.minisig against a minisign public key.
#   gpg      -> verify <SHA256SUMS>.asc against an imported/standalone pubkey.
#
# Usage:
#   scripts/verify-release.sh --minisign <SHA256SUMS> <public_key>   [--check-sums]
#   scripts/verify-release.sh --gpg      <SHA256SUMS> <public_key.asc> [--check-sums]
#
# --check-sums additionally runs `sha256sum -c` so you confirm the actual
# binaries match the (now-authenticated) SHA256SUMS. Run it from the directory
# that contains the files SHA256SUMS lists.
#
# Expected PUBLIC key location (publish ONE, document both):
#   repo: keys/sost-release.pub          (minisign) or keys/sost-release.asc (gpg)
#   web : https://sostcore.com/keys/sost-release.pub
# See docs/RELEASE_SIGNING.md. (No real key is shipped in this change — the
# placeholder path above is where the owner installs the real public key.)
#
# Exit: 0 verified, 1 signature INVALID, 2 usage, 3 missing tool, 4 missing input.
set -uo pipefail

die() { echo "ERROR: $*" >&2; exit "${2:-2}"; }

[ $# -ge 3 ] || die "usage: $0 --minisign|--gpg <SHA256SUMS> <public_key> [--check-sums]" 2
BACKEND="$1"; SUMS="$2"; PUB="$3"; shift 3
CHECK_SUMS=0
for a in "$@"; do [ "$a" = "--check-sums" ] && CHECK_SUMS=1; done

[ -r "$SUMS" ] || die "cannot read SHA256SUMS: $SUMS" 4
[ -r "$PUB" ]  || die "cannot read public key: $PUB" 4

verify_integrity() {
  [ "$CHECK_SUMS" -eq 1 ] || return 0
  echo "---- integrity: sha256sum -c $SUMS ----"
  if sha256sum -c "$SUMS"; then echo "INTEGRITY: OK"; else die "INTEGRITY: one or more files FAILED sha256 check" 1; fi
}

case "$BACKEND" in
  --minisign)
    command -v minisign >/dev/null 2>&1 || die "minisign not installed (apt install minisign)" 3
    SIG="$SUMS.minisig"
    [ -r "$SIG" ] || die "detached signature not found: $SIG" 4
    echo "---- authenticity: minisign -V ----"
    if minisign -V -p "$PUB" -m "$SUMS" -x "$SIG"; then
      echo "AUTHENTICITY: OK (SHA256SUMS signed by the holder of $PUB)"
    else
      die "AUTHENTICITY: signature INVALID — do NOT trust these binaries" 1
    fi
    verify_integrity
    ;;
  --gpg)
    command -v gpg >/dev/null 2>&1 || die "gpg not installed" 3
    SIG="$SUMS.asc"
    [ -r "$SIG" ] || die "detached signature not found: $SIG" 4
    echo "---- authenticity: gpg --verify ----"
    # Verify against the given standalone public key WITHOUT polluting the
    # user's default keyring (temporary keyring in a scratch dir).
    GNUPGHOME_TMP="$(mktemp -d)"; trap 'rm -rf "$GNUPGHOME_TMP"' EXIT
    chmod 700 "$GNUPGHOME_TMP"
    if ! GNUPGHOME="$GNUPGHOME_TMP" gpg --batch --quiet --import "$PUB" 2>/dev/null; then
      die "could not import public key $PUB" 4
    fi
    if GNUPGHOME="$GNUPGHOME_TMP" gpg --batch --verify "$SIG" "$SUMS" 2>&1; then
      echo "AUTHENTICITY: OK (SHA256SUMS signed by the key in $PUB)"
    else
      die "AUTHENTICITY: signature INVALID — do NOT trust these binaries" 1
    fi
    verify_integrity
    ;;
  *) die "unknown backend '$BACKEND' (use --minisign or --gpg)" 2 ;;
esac
echo "VERIFIED."
