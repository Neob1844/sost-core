#!/usr/bin/env bash
# fetch-and-verify.sh — download a SOST release from one or more mirrors and verify it,
# fail-closed, without trusting any mirror.
#
#   scripts/release/fetch-and-verify.sh --tag <tag> --out <dir> \
#       --backend gpg|openssl|minisign --pubkey <public key> [--fingerprint HEX] \
#       [--mirror <base URL>]... [--mirrors-file release/MIRRORS.txt] \
#       [--sums-name SHA256SUMS] [--files a,b,c]
#
# Order of trust:
#   1. SHA256SUMS + its detached signature are fetched from each mirror in order until one
#      pair verifies against --pubkey (scripts/verify-release.sh). No mirror verifies -> exit 1.
#   2. Every file named in the authenticated SHA256SUMS (or only --files) is fetched from the
#      mirrors in order; a copy whose sha256 differs is discarded and the next mirror is tried.
#   3. `sha256sum --strict -c` over the output directory.
# Mirrors may be https:// (any host: an independent domain, a second forge, an IPFS gateway)
# or file:// (offline media). Plain http:// is refused. Only PUBLIC key material is used.
#
# Exit: 0 verified, 1 verification failed, 2 usage, 3 missing tool.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
VERIFY="$HERE/../verify-release.sh"
die() { echo "ERROR: $*" >&2; exit "${2:-2}"; }
command -v curl >/dev/null 2>&1 || die "curl not installed" 3

TAG=""; OUT=""; BACKEND=""; PUB=""; FPR=""; SUMS_NAME="SHA256SUMS"; FILES=""; MIRRORS=(); MFILE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="$2"; shift ;;
    --out) OUT="$2"; shift ;;
    --backend) BACKEND="$2"; shift ;;
    --pubkey) PUB="$2"; shift ;;
    --fingerprint) FPR="$2"; shift ;;
    --mirror) MIRRORS+=("$2"); shift ;;
    --mirrors-file) MFILE="$2"; shift ;;
    --sums-name) SUMS_NAME="$2"; shift ;;
    --files) FILES="$2"; shift ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
[ -n "$OUT" ] && [ -n "$BACKEND" ] && [ -n "$PUB" ] || die "need --out, --backend and --pubkey"
case "$BACKEND" in gpg) EXT=asc ;; openssl) EXT=sig ;; minisign) EXT=minisig ;; *) die "backend must be gpg|openssl|minisign" ;; esac
case "$SUMS_NAME" in */*|..|.) die "bad --sums-name" ;; esac
if [ -n "$MFILE" ]; then
  [ -r "$MFILE" ] || die "cannot read $MFILE"
  while IFS= read -r ln; do
    ln="${ln%%#*}"; ln="$(echo "$ln" | tr -d '[:space:]')"
    [ -n "$ln" ] && MIRRORS+=("$ln")
  done < "$MFILE"
fi
[ ${#MIRRORS[@]} -gt 0 ] || die "no mirror given (--mirror / --mirrors-file)"
for i in "${!MIRRORS[@]}"; do
  m="${MIRRORS[$i]//\{tag\}/$TAG}"; m="${m%/}"
  case "$m" in https://*|file://*) ;; *) die "mirror must be https:// or file:// (got $m)" ;; esac
  case "$m" in *\{tag\}*) die "mirror needs --tag" ;; esac
  MIRRORS[$i]="$m"
done

mkdir -p "$OUT" || die "cannot create $OUT"
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
fetch() {  # url dest
  curl --fail --silent --show-error --location --proto '=https,file' --proto-redir '=https' \
       --connect-timeout 20 --max-time 1800 --max-filesize 1073741824 -o "$2" "$1"
}

# 1. authenticated SHA256SUMS
AUTH=""
for m in "${MIRRORS[@]}"; do
  d="$STAGE/sums.$RANDOM"; mkdir -p "$d"
  if fetch "$m/$SUMS_NAME" "$d/$SUMS_NAME" && fetch "$m/$SUMS_NAME.$EXT" "$d/$SUMS_NAME.$EXT"; then
    args=(--"$BACKEND" "$d/$SUMS_NAME" "$PUB"); [ -n "$FPR" ] && args+=(--fingerprint "$FPR")
    if bash "$VERIFY" "${args[@]}" >/dev/null 2>&1; then
      AUTH="$d"; echo "SHA256SUMS authenticated (fetched from $m)"; break
    fi
    echo "WARN: $m served a SHA256SUMS whose signature does NOT verify — skipped" >&2
  else
    echo "WARN: $m unavailable for $SUMS_NAME — trying next mirror" >&2
  fi
done
[ -n "$AUTH" ] || die "no mirror served an authentic $SUMS_NAME" 1
if ! awk '{ f=$2; sub(/^\*/, "", f); if (NF != 2 || f ~ /\// || f == ".." || f == "." || $1 !~ /^[0-9a-f]{64}$/) bad=1 } END { exit bad }' "$AUTH/$SUMS_NAME"; then
  die "authenticated $SUMS_NAME has a malformed or path-bearing entry — refusing" 1
fi

# 2. files, each checked against the authenticated hash
want() { [ -z "$FILES" ] && return 0; case ",$FILES," in *",$1,"*) return 0 ;; esac; return 1; }
n=0
while read -r hash name; do
  name="${name#\*}"
  want "$name" || continue
  got=""
  for m in "${MIRRORS[@]}"; do
    if fetch "$m/$name" "$STAGE/$name.part"; then
      if [ "$(sha256sum "$STAGE/$name.part" | awk '{print $1}')" = "$hash" ]; then
        mv -f "$STAGE/$name.part" "$OUT/$name"; got="$m"; break
      fi
      echo "WARN: $m served a copy of $name with the WRONG sha256 — discarded" >&2
    fi
    rm -f "$STAGE/$name.part"
  done
  [ -n "$got" ] || die "no mirror served a correct $name" 1
  echo "OK  $name  (from $got)"; n=$((n+1))
done < "$AUTH/$SUMS_NAME"
[ "$n" -gt 0 ] || die "nothing selected from $SUMS_NAME" 1

# 3. final strict check of what is on disk (selected files only)
cp "$AUTH/$SUMS_NAME" "$AUTH/$SUMS_NAME.$EXT" "$OUT/"
if [ -n "$FILES" ]; then
  (cd "$OUT" && while read -r hash name; do if want "${name#\*}"; then echo "$hash  ${name#\*}"; fi; done < "$SUMS_NAME" | sha256sum --strict -c -) || die "final integrity check failed" 1
else
  (cd "$OUT" && sha256sum --strict -c "$SUMS_NAME") || die "final integrity check failed" 1
fi
echo "VERIFIED: $n file(s) in $OUT match the signed $SUMS_NAME"
