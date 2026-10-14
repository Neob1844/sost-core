#!/usr/bin/env bash
# make-sha256sums.sh — write a canonical SHA256SUMS for a set of release files.
#
#   scripts/release/make-sha256sums.sh <out SHA256SUMS> <file>...
#
# Canonical form (so two builders of the same reproducible build produce byte-identical sums):
#   * one line per file "<sha256>  <basename>" (text mode, two spaces), basenames only;
#   * sorted by basename with LC_ALL=C; duplicate basenames are refused;
#   * written atomically (tmp + rename), never includes the output file itself.
# Sign the result with scripts/sign-release.sh on the OFFLINE machine; verify with
# scripts/verify-release.sh. No key is read here.
set -euo pipefail
die() { echo "ERROR: $*" >&2; exit 2; }
[ $# -ge 2 ] || die "usage: $0 <out SHA256SUMS> <file>..."
OUT="$1"; shift
declare -A seen=()
lines=()
for f in "$@"; do
  [ -f "$f" ] && [ -r "$f" ] || die "not a readable file: $f"
  b="$(basename "$f")"
  [ "$(readlink -f "$f")" != "$(readlink -f "$OUT" 2>/dev/null || echo /nonexistent)" ] || die "refusing to hash the output file itself"
  [ -z "${seen[$b]:-}" ] || die "duplicate basename: $b"
  case "$b" in *[[:space:]]*|*\\*) die "basename with whitespace/backslash not allowed: $b" ;; esac
  seen[$b]=1
  h="$(sha256sum "$f" | awk '{print $1}')"
  lines+=("$h  $b")
done
tmp="$OUT.tmp.$$"
printf '%s\n' "${lines[@]}" | LC_ALL=C sort -k2,2 > "$tmp"
mv -f "$tmp" "$OUT"
echo "wrote $OUT ($# file(s))"
