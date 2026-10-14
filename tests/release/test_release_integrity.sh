#!/usr/bin/env bash
# Release-integrity tooling test. Uses ONLY throwaway keys generated in a temp dir (gpg in a
# temporary GNUPGHOME, openssl Ed25519 PEMs); no real key is created, read or used.
# Covers: make-sha256sums (canonical), sign/verify (gpg + openssl), tampered sums, tampered
# binary, wrong key, pinned fingerprint, path-traversal sums, and fetch-and-verify with a
# primary mirror that is DOWN, a mirror serving a TAMPERED binary and a mirror serving a forged
# SHA256SUMS — the independent mirror must still yield a verified release.
set -uo pipefail
R="$(cd "$(dirname "$0")/../.." && pwd)"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()  { pass=$((pass+1)); echo "  PASS $1"; }
bad() { fail=$((fail+1)); echo "  FAIL $1"; }
expect() { local want="$1" name="$2"; shift 2; "$@" >"$T/last.log" 2>&1; local rc=$?
  if [ "$rc" = "$want" ]; then ok "$name (rc=$rc)"; else bad "$name (rc=$rc, want $want)"; sed 's/^/      /' "$T/last.log" | tail -5; fi; }

mkdir -p "$T/rel" "$T/keys"
printf 'node-binary\n' > "$T/rel/sost-node"; printf 'miner-binary\n' > "$T/rel/sost-miner"; printf 'cli\n' > "$T/rel/sost-cli"
expect 0 "make-sha256sums" bash "$R/scripts/release/make-sha256sums.sh" "$T/rel/SHA256SUMS" "$T/rel/sost-node" "$T/rel/sost-miner" "$T/rel/sost-cli"
[ "$(awk '{print $2}' "$T/rel/SHA256SUMS" | tr '\n' ' ')" = "sost-cli sost-miner sost-node " ] && ok "canonical sorted basenames" || bad "canonical sorted basenames"
bash "$R/scripts/release/make-sha256sums.sh" "$T/s2" "$T/rel/sost-cli" "$T/rel/sost-node" "$T/rel/sost-miner" >/dev/null
cmp -s "$T/s2" "$T/rel/SHA256SUMS" && ok "argument order does not change the file" || bad "argument order does not change the file"
expect 2 "duplicate basename refused" bash "$R/scripts/release/make-sha256sums.sh" "$T/s3" "$T/rel/sost-cli" "$T/rel/sost-cli"

# ---- openssl Ed25519 (throwaway)
openssl genpkey -algorithm ed25519 -out "$T/keys/k1.pem" 2>/dev/null; openssl pkey -in "$T/keys/k1.pem" -pubout -out "$T/keys/p1.pem"
openssl genpkey -algorithm ed25519 -out "$T/keys/k2.pem" 2>/dev/null; openssl pkey -in "$T/keys/k2.pem" -pubout -out "$T/keys/p2.pem"
expect 0 "openssl sign" bash "$R/scripts/sign-release.sh" --openssl "$T/rel/SHA256SUMS" "$T/keys/k1.pem"
expect 0 "openssl verify + check-sums" bash "$R/scripts/verify-release.sh" --openssl "$T/rel/SHA256SUMS" "$T/keys/p1.pem" --check-sums
expect 1 "openssl wrong key rejected" bash "$R/scripts/verify-release.sh" --openssl "$T/rel/SHA256SUMS" "$T/keys/p2.pem"
cp -a "$T/rel" "$T/relx"; sed -i '1s/^./0/' "$T/relx/SHA256SUMS"
expect 1 "openssl tampered SHA256SUMS rejected" bash "$R/scripts/verify-release.sh" --openssl "$T/relx/SHA256SUMS" "$T/keys/p1.pem"
cp -a "$T/rel" "$T/rely"; printf 'evil\n' > "$T/rely/sost-node"
expect 1 "tampered binary fails integrity" bash "$R/scripts/verify-release.sh" --openssl "$T/rely/SHA256SUMS" "$T/keys/p1.pem" --check-sums
expect 4 "private key passed as public key refused" bash "$R/scripts/verify-release.sh" --openssl "$T/rel/SHA256SUMS" "$T/rel/sost-cli"
mkdir -p "$T/relz"; echo "$(sha256sum "$T/rel/sost-cli" | cut -d' ' -f1)  ../sost-cli" > "$T/relz/SHA256SUMS"
bash "$R/scripts/sign-release.sh" --openssl "$T/relz/SHA256SUMS" "$T/keys/k1.pem" >/dev/null
expect 1 "signed sums with '..' entry refused at check-sums" bash "$R/scripts/verify-release.sh" --openssl "$T/relz/SHA256SUMS" "$T/keys/p1.pem" --check-sums

# ---- gpg (throwaway, temporary GNUPGHOME)
if command -v gpg >/dev/null 2>&1; then
  export GNUPGHOME="$T/gnupg"; mkdir -m 700 "$GNUPGHOME"
  gpg --batch --quiet --passphrase '' --quick-gen-key "throwaway-test-1 <t1@example.invalid>" ed25519 sign 1d 2>/dev/null
  gpg --batch --quiet --passphrase '' --quick-gen-key "throwaway-test-2 <t2@example.invalid>" ed25519 sign 1d 2>/dev/null
  F1="$(gpg --with-colons --fingerprint t1@example.invalid | awk -F: '$1=="fpr"{print $10; exit}')"
  F2="$(gpg --with-colons --fingerprint t2@example.invalid | awk -F: '$1=="fpr"{print $10; exit}')"
  gpg --batch --armor --export "$F1" > "$T/keys/g1.asc"; gpg --batch --armor --export "$F2" > "$T/keys/g2.asc"
  expect 0 "gpg sign" bash "$R/scripts/sign-release.sh" --gpg "$T/rel/SHA256SUMS" "$F1"
  unset GNUPGHOME
  expect 0 "gpg verify + check-sums" bash "$R/scripts/verify-release.sh" --gpg "$T/rel/SHA256SUMS" "$T/keys/g1.asc" --check-sums
  expect 0 "gpg pinned fingerprint ok" bash "$R/scripts/verify-release.sh" --gpg "$T/rel/SHA256SUMS" "$T/keys/g1.asc" --fingerprint "$F1"
  expect 1 "gpg signature by another key rejected" bash "$R/scripts/verify-release.sh" --gpg "$T/rel/SHA256SUMS" "$T/keys/g2.asc"
  expect 1 "gpg wrong pinned fingerprint rejected" bash "$R/scripts/verify-release.sh" --gpg "$T/rel/SHA256SUMS" "$T/keys/g1.asc" --fingerprint "$F2"
  cp "$T/rel/SHA256SUMS.asc" "$T/relx/SHA256SUMS.asc"
  expect 1 "gpg tampered SHA256SUMS rejected" bash "$R/scripts/verify-release.sh" --gpg "$T/relx/SHA256SUMS" "$T/keys/g1.asc"
else
  echo "  SKIP gpg not installed"
fi

# ---- fetch-and-verify across mirrors (file:// stands in for https mirrors)
mkdir -p "$T/m_tampered" "$T/m_forged" "$T/m_good"
cp "$T/rel/"* "$T/m_good/"
cp "$T/rel/"* "$T/m_tampered/"; printf 'evil\n' > "$T/m_tampered/sost-node"
cp "$T/rel/"* "$T/m_forged/"; printf 'evil\n' > "$T/m_forged/sost-node"
printf '%s  sost-node\n' "$(printf 'evil\n' | sha256sum | cut -d' ' -f1)" > "$T/m_forged/SHA256SUMS"
expect 0 "fetch: primary DOWN, tampered mirror, then independent good mirror" \
  bash "$R/scripts/release/fetch-and-verify.sh" --backend openssl --pubkey "$T/keys/p1.pem" --out "$T/out1" \
    --mirror "file://$T/m_missing" --mirror "file://$T/m_tampered" --mirror "file://$T/m_good"
grep -q "WRONG sha256" "$T/last.log" && ok "tampered copy was detected and discarded" || bad "tampered copy was detected and discarded"
cmp -s "$T/out1/sost-node" "$T/rel/sost-node" && ok "output binary is the genuine one" || bad "output binary is the genuine one"
expect 0 "fetch: forged SHA256SUMS mirror skipped" \
  bash "$R/scripts/release/fetch-and-verify.sh" --backend openssl --pubkey "$T/keys/p1.pem" --out "$T/out2" \
    --mirror "file://$T/m_forged" --mirror "file://$T/m_good"
grep -q "does NOT verify" "$T/last.log" && ok "forged sums detected" || bad "forged sums detected"
expect 1 "fetch: only bad mirrors -> fail closed" \
  bash "$R/scripts/release/fetch-and-verify.sh" --backend openssl --pubkey "$T/keys/p1.pem" --out "$T/out3" \
    --mirror "file://$T/m_forged" --mirror "file://$T/m_tampered"
[ ! -e "$T/out3/sost-node" ] && ok "nothing unverified left in the output" || bad "nothing unverified left in the output"
expect 2 "fetch: plain http mirror refused" \
  bash "$R/scripts/release/fetch-and-verify.sh" --backend openssl --pubkey "$T/keys/p1.pem" --out "$T/out4" --mirror "http://example.invalid/x"
expect 0 "fetch: --files subset" \
  bash "$R/scripts/release/fetch-and-verify.sh" --backend openssl --pubkey "$T/keys/p1.pem" --out "$T/out5" --files sost-cli \
    --mirror "file://$T/m_good"
[ -f "$T/out5/sost-cli" ] && [ ! -e "$T/out5/sost-node" ] && ok "subset only" || bad "subset only"
grep -q "^https://github.com/" "$R/release/MIRRORS.txt" && ok "MIRRORS.txt lists a publication point outside sostcore.com" || bad "MIRRORS.txt lists a publication point outside sostcore.com"

echo "release integrity: $pass passed, $fail failed"
[ "$fail" -eq 0 ]
