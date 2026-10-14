#!/usr/bin/env bash
# verify-release.sh — verify a release's SHA256SUMS authenticity against the
# SOST PUBLIC release key, and (optionally) verify the binaries' integrity
# against SHA256SUMS.
#
# This is the script a third party runs. It needs ONLY public material:
#   - the SHA256SUMS file,
#   - its detached signature (.minisig, .asc or .sig),
#   - the SOST public key.
# It never needs — and must never be given — any private key.
#
# Backends:
#   minisign -> verify <SHA256SUMS>.minisig against a minisign public key.
#   gpg      -> verify <SHA256SUMS>.asc against a standalone public key, in a temporary
#               keyring; the signature must be a VALIDSIG made by that key (fingerprint
#               checked), so a signature by any other key is rejected.
#   openssl  -> verify <SHA256SUMS>.sig (raw Ed25519) against an Ed25519 public-key PEM.
#
# Usage:
#   scripts/verify-release.sh --minisign <SHA256SUMS> <public_key>      [--check-sums]
#   scripts/verify-release.sh --gpg      <SHA256SUMS> <public_key.asc>  [--check-sums]
#   scripts/verify-release.sh --openssl  <SHA256SUMS> <public_key.pem>  [--check-sums]
#   Optional: --fingerprint <hex> (gpg: the signer fingerprint must equal it)
#             --sig <path>        (signature somewhere other than <SHA256SUMS>.<ext>)
#
# --check-sums additionally runs `sha256sum --strict -c` in the directory that holds
# SHA256SUMS, so you confirm the actual binaries match the (now-authenticated) SHA256SUMS.
# Entries with an absolute path or a ".." component are refused.
#
# Expected PUBLIC key location (publish ONE, document both):
#   repo: keys/sost-release.pub (minisign) / keys/sost-release.asc (gpg) / keys/sost-release.pem (openssl)
#   web : https://sostcore.com/keys/ and the GitHub release page (second, independent host)
# See docs/RELEASE_SIGNING.md. (No real key is shipped in this change.)
#
# Exit: 0 verified, 1 signature or integrity INVALID, 2 usage, 3 missing tool, 4 missing input.
set -uo pipefail

die() { echo "ERROR: $*" >&2; exit "${2:-2}"; }

[ $# -ge 3 ] || die "usage: $0 --minisign|--gpg|--openssl <SHA256SUMS> <public_key> [--check-sums] [--fingerprint HEX] [--sig PATH]" 2
BACKEND="$1"; SUMS="$2"; PUB="$3"; shift 3
CHECK_SUMS=0; FPR=""; SIG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --check-sums) CHECK_SUMS=1 ;;
    --fingerprint) FPR="$(echo "${2:-}" | tr -d ' ' | tr 'a-f' 'A-F')"; shift ;;
    --sig) SIG="${2:-}"; shift ;;
    *) die "unknown option $1" 2 ;;
  esac
  shift
done

[ -r "$SUMS" ] || die "cannot read SHA256SUMS: $SUMS" 4
[ -r "$PUB" ]  || die "cannot read public key: $PUB" 4

verify_integrity() {
  [ "$CHECK_SUMS" -eq 1 ] || return 0
  echo "---- integrity: sha256sum --strict -c $(basename "$SUMS") ----"
  # refuse path tricks before touching the filesystem
  if awk '{ f=$2; sub(/^\*/, "", f); if (f ~ /^\// || f ~ /(^|\/)\.\.(\/|$)/ || NF < 2) bad=1 } END { exit bad }' "$SUMS"; then :; else
    die "INTEGRITY: SHA256SUMS contains an absolute path or '..' entry — refusing" 1
  fi
  if (cd "$(dirname "$SUMS")" && sha256sum --strict -c "$(basename "$SUMS")"); then
    echo "INTEGRITY: OK"
  else
    die "INTEGRITY: one or more files FAILED the sha256 check" 1
  fi
}

case "$BACKEND" in
  --minisign)
    command -v minisign >/dev/null 2>&1 || die "minisign not installed (apt install minisign)" 3
    SIG="${SIG:-$SUMS.minisig}"
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
    SIG="${SIG:-$SUMS.asc}"
    [ -r "$SIG" ] || die "detached signature not found: $SIG" 4
    echo "---- authenticity: gpg --verify (temporary keyring) ----"
    GNUPGHOME_TMP="$(mktemp -d)"; trap 'rm -rf "$GNUPGHOME_TMP"' EXIT
    chmod 700 "$GNUPGHOME_TMP"
    if ! GNUPGHOME="$GNUPGHOME_TMP" gpg --batch --quiet --import "$PUB" 2>/dev/null; then
      die "could not import public key $PUB" 4
    fi
    KEYFPRS="$(GNUPGHOME="$GNUPGHOME_TMP" gpg --batch --with-colons --fingerprint 2>/dev/null | awk -F: '$1=="fpr"{print $10}')"
    [ -n "$KEYFPRS" ] || die "no key found in $PUB" 4
    if [ -n "$FPR" ] && ! echo "$KEYFPRS" | grep -qx "$FPR"; then
      die "public key $PUB does not have the pinned fingerprint $FPR" 1
    fi
    STATUS="$(GNUPGHOME="$GNUPGHOME_TMP" gpg --batch --status-fd 1 --verify "$SIG" "$SUMS" 2>/dev/null)"
    SIGNER="$(echo "$STATUS" | awk '$2=="VALIDSIG"{print $3; exit}')"
    PRIMARY="$(echo "$STATUS" | awk '$2=="VALIDSIG"{print $NF; exit}')"
    if echo "$STATUS" | grep -q "^\[GNUPG:\] GOODSIG" && [ -n "$SIGNER" ] && \
       { echo "$KEYFPRS" | grep -qx "$SIGNER" || echo "$KEYFPRS" | grep -qx "$PRIMARY"; } && \
       { [ -z "$FPR" ] || [ "$SIGNER" = "$FPR" ] || [ "$PRIMARY" = "$FPR" ]; }; then
      echo "AUTHENTICITY: OK (SHA256SUMS signed by $PRIMARY)"
    else
      die "AUTHENTICITY: signature INVALID or not made by the key in $PUB — do NOT trust these binaries" 1
    fi
    verify_integrity
    ;;
  --openssl)
    command -v openssl >/dev/null 2>&1 || die "openssl not installed" 3
    SIG="${SIG:-$SUMS.sig}"
    [ -r "$SIG" ] || die "detached signature not found: $SIG" 4
    openssl pkey -pubin -in "$PUB" -noout -text_pub 2>/dev/null | grep -q "ED25519" || \
      die "public key $PUB is not an Ed25519 public-key PEM" 4
    echo "---- authenticity: openssl pkeyutl -verify (Ed25519) ----"
    if openssl pkeyutl -verify -pubin -inkey "$PUB" -rawin -in "$SUMS" -sigfile "$SIG" >/dev/null 2>&1; then
      echo "AUTHENTICITY: OK (SHA256SUMS signed by the holder of $PUB)"
    else
      die "AUTHENTICITY: signature INVALID — do NOT trust these binaries" 1
    fi
    verify_integrity
    ;;
  *) die "unknown backend '$BACKEND' (use --minisign, --gpg or --openssl)" 2 ;;
esac
echo "VERIFIED."
