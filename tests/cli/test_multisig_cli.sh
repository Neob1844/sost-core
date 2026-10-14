#!/usr/bin/env bash
# =============================================================================
# test_multisig_cli.sh — sost-cli offline multisig workflow (V17), no node needed.
#   createmultisig -> (PSST emitted by test-multisig-psst) -> signtx x3 (independent
#   wallets) -> combinetx -> verifytx ; refusals (network/CHAIN_ID/tamper/no key) and
#   the wallet rules of spec §10.3.
# Usage: test_multisig_cli.sh <build-dir>
# =============================================================================
set -uo pipefail
B="${1:?build dir}"
CLI="$B/sost-cli"; EMIT="$B/test-multisig-psst"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); }
bad(){ FAIL=$((FAIL+1)); echo "  FAIL: $*"; }
check(){ local name="$1"; shift; if "$@"; then ok; else bad "$name"; fi; }
priv(){ printf '%064x' "$1"; }

# --- createmultisig (keys of privs 1..5 given in a shuffled order) -------------
declare -A PUB
for i in 1 2 3 4 5 9; do
  "$CLI" --wallet "$W/w$i.json" newwallet >/dev/null 2>&1
  A=$("$CLI" --wallet "$W/w$i.json" importprivkey "$(priv $i)" 2>/dev/null | grep -oE 'sost1[0-9a-f]{40}')
  PUB[$i]=$("$CLI" --wallet "$W/w$i.json" getpubkey "$A" 2>/dev/null | tr -d '[:space:]')
done
check "getpubkey returns 33-byte hex" test "${#PUB[1]}" -eq 66
OUT=$("$CLI" createmultisig 3 "${PUB[4]}" "${PUB[2]}" "${PUB[5]}" "${PUB[1]}" "${PUB[3]}" --out "$W/pol.json" 2>&1)
check "createmultisig sorts keys and reproduces the spec 3-of-5 address" \
  grep -q 'sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7' <<<"$OUT"
check "policy file carries the MSH vector" grep -q '6b53fe0baa7da53368ba82cad9e6fe5c7c09f0f9' "$W/pol.json"
check "createmultisig --network dev gives the devnet HRP" \
  bash -c "'$CLI' createmultisig 3 ${PUB[1]} ${PUB[2]} ${PUB[3]} ${PUB[4]} ${PUB[5]} --network dev | grep -q dsostms1q9448lst4f762vmgh2pv4k0xlew8cz0sly5ayfew"
check "createmultisig refuses a duplicate key" bash -c "! '$CLI' createmultisig 2 ${PUB[1]} ${PUB[1]} ${PUB[2]} >/dev/null 2>&1"
check "createmultisig refuses M > N" bash -c "! '$CLI' createmultisig 4 ${PUB[1]} ${PUB[2]} ${PUB[3]} >/dev/null 2>&1"
UNC="04${PUB[1]:2}"
check "createmultisig refuses an uncompressed (0x04) key" bash -c "! '$CLI' createmultisig 1 $UNC >/dev/null 2>&1"
check "createmultisig refuses an existing --out file" bash -c "! '$CLI' createmultisig 1 ${PUB[1]} --out '$W/pol.json' >/dev/null 2>&1"

# --- PSST template for a 3-of-5 vault spend ------------------------------------
"$EMIT" emit "$W" >/dev/null
check "PSST template emitted" test -s "$W/tx.json"

# --- independent offline signers ------------------------------------------------
check "signer 1 signs" bash -c "'$CLI' --wallet '$W/w1.json' signtx '$W/tx.json' --out '$W/s1.json' --yes >/dev/null 2>&1"
check "signer 2 signs" bash -c "'$CLI' --wallet '$W/w2.json' signtx '$W/tx.json' --out '$W/s2.json' --yes >/dev/null 2>&1"
check "signer 5 signs" bash -c "'$CLI' --wallet '$W/w5.json' signtx '$W/tx.json' --out '$W/s5.json' --yes >/dev/null 2>&1"
check "signer 4 signs" bash -c "'$CLI' --wallet '$W/w4.json' signtx '$W/tx.json' --out '$W/s4.json' --yes >/dev/null 2>&1"
check "signtx without 'yes' does not sign" bash -c "echo no | '$CLI' --wallet '$W/w3.json' signtx '$W/tx.json' --out '$W/s3.json' >/dev/null 2>&1; test ! -e '$W/s3.json'"
check "signtx refuses a wallet with no policy key" bash -c "! '$CLI' --wallet '$W/w9.json' signtx '$W/tx.json' --out '$W/x.json' --yes >/dev/null 2>&1"
check "signtx refuses a network mismatch" bash -c "! '$CLI' --wallet '$W/w3.json' signtx '$W/tx.json' --network testnet --out '$W/x.json' --yes >/dev/null 2>&1"
M_CID=3ed1273b38ad28c61f591fed49dd8ec8f4684953f17ad371f5c3d741c1d1a2e4
T_CID=301a71e109f7728f83c4fd96d114231c13fafd98a6cb1533caa1267fd385bec3
sed "s/$M_CID/$T_CID/" "$W/tx.json" > "$W/tx_wrongcid.json"
check "signtx refuses a wrong CHAIN_ID" bash -c "! '$CLI' --wallet '$W/w3.json' signtx '$W/tx_wrongcid.json' --out '$W/x.json' --yes >/dev/null 2>&1"
# tamper: change the payment amount inside unsigned_hex
sed 's/00ca9a3b00000000/01ca9a3b00000000/' "$W/tx.json" > "$W/tx_tampered.json"
check "tamper produced a different file" bash -c "! cmp -s '$W/tx.json' '$W/tx_tampered.json'"
check "signtx refuses a tampered unsigned_hex" bash -c "! '$CLI' --wallet '$W/w3.json' signtx '$W/tx_tampered.json' --out '$W/x.json' --yes >/dev/null 2>&1"

# --- verify / combine -----------------------------------------------------------
"$CLI" verifytx "$W/s1.json" >/dev/null 2>&1; RC=$?
check "verifytx on 1-of-3 signatures exits 2 (incomplete)" test "$RC" -eq 2
"$CLI" combinetx "$W/s1.json" "$W/s2.json" --out "$W/c12.json" > "$W/c12.out" 2>&1
check "combinetx 2 sigs -> complete: no" grep -q 'complete: no' "$W/c12.out"
"$CLI" combinetx "$W/s1.json" "$W/s2.json" "$W/s5.json" --out "$W/c.json" > "$W/c.out" 2>&1
check "combinetx 3 sigs -> complete: yes + final_hex" bash -c "grep -q 'complete: yes' '$W/c.out' && grep -q '^final_hex [0-9a-f]*' '$W/c.out'"
"$CLI" verifytx "$W/c.json" > "$W/v.out" 2>&1; RC=$?
check "verifytx complete PSST exits 0 with RESULT: VALID" bash -c "test $RC -eq 0 && grep -q 'RESULT: VALID' '$W/v.out'"
"$CLI" combinetx "$W/s1.json" "$W/s2.json" "$W/s4.json" "$W/s5.json" --out "$W/c4.json" > "$W/c4.out" 2>&1
# signers' key indexes: priv5=0 priv1=1 priv2=2 priv4=3 -> lowest three = {0,1,2} = same set as c.json
check "combinetx with 4 sigs selects the M lowest indexes (same final tx as {0,1,2})" \
  bash -c "test \"\$(grep '^final_hex' '$W/c4.out')\" = \"\$(grep '^final_hex' '$W/c.out')\""
check "combinetx refuses a file of another template" bash -c "! '$CLI' combinetx '$W/s1.json' '$W/tx_tampered.json' --out '$W/x2.json' >/dev/null 2>&1"
FINAL=$(grep '^final_hex' "$W/c.out" | awk '{print $2}')
"$CLI" verifytx "$FINAL" > "$W/vh.out" 2>&1; RC=$?
check "verifytx on raw hex: structure ok, signatures unverified (exit 3)" bash -c "test $RC -eq 3 && grep -q 'STRUCTURE OK' '$W/vh.out'"
"$CLI" verifytx "02${FINAL:2:20}" >/dev/null 2>&1; RC=$?
check "verifytx on truncated hex fails" test "$RC" -eq 1

# --- wallet rules (spec §10.3) ----------------------------------------------------
MS=sostms1q9448lst4f762vmgh2pv4k0xlew8cz0slyxnu6j7
Z40=0000000000000000000000000000000000000000
Z64=0000000000000000000000000000000000000000000000000000000000000000
check "wallet_refuses_msh_as_htlc_claimant" bash -c "'$CLI' createhtlclock $Z64 0 100000 $Z40 $Z64 50000 $MS $Z40 50000 1000 2>&1 | grep -q 'cannot be an HTLC claimant'"
check "wallet_refuses_msh_in_bond_lock (escrow beneficiary)" bash -c "'$CLI' --wallet '$W/w1.json' create-escrow 1 100 $MS 2>&1 | grep -q 'BOND/ESCROW'"
check "legacy send to a sostms address refused" bash -c "'$CLI' --wallet '$W/w1.json' send $MS 1 2>&1 | grep -q 'version-2 transaction'"

echo "=== multisig-cli: $PASS passed, $FAIL failed ==="
[[ "$FAIL" -eq 0 ]]
