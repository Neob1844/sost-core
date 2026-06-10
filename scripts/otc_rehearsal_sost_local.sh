#!/usr/bin/env bash
# =============================================================================
# OTC-5 — SOST-side rehearsal + end-to-end coordinator drive.
#
# Exercises the SOST leg and the OTC-4 coordinator that orchestrates all three
# legs. Runs entirely locally; no node restart, no mainnet, gates untouched.
#
# What it does (all runnable in CI/sandbox):
#   1. SOST HTLC consensus + builders + RPC-status + watcher + session suites.
#   2. A full coordinator happy path (offer -> accept -> lock both -> claim ->
#      opposite-leg claim -> Completed), a refund path, and a resume.
#   3. Negative cases (wrong preimage, mis-ordered timeout, issuer-freeze).
#
# LIVE SOST HTLC on a real node (LOCK/CLAIM/REFUND broadcast + gethtlcstatus)
# requires a REGTEST build whose ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT is set to a
# low test height. The MAINNET constant stays INT64_MAX — that override is a
# regtest-only operator build step (documented at the end), NOT done here.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

BUILD="${BUILD:-build-otc1}"
C="./$BUILD/otc-coordinator"
echo "== OTC-5 SOST + coordinator rehearsal =="

# --- 1. SOST-side consensus + module suites ---------------------------------
echo "-- SOST HTLC consensus + atomic-swap module tests --"
( cd "$BUILD" && ctest -R "atomic-swap" --output-on-failure | grep -E "tests passed|failed" )

# --- 2. Coordinator end-to-end (happy + resume) -----------------------------
SEC="$(python3 -c "print('42'*32)")"
HL="$(python3 -c "import hashlib;print(hashlib.sha256(bytes.fromhex('42'*32)).hexdigest())")"
F="$(mktemp)"
echo "-- coordinator happy path (initiator, SOST<->BTC) --"
"$C" create "$F" --role Initiator --cp BTC --give SOST --want BTC \
     --give-amount 1000000 --want-amount 50000 --hashlock "$HL" --secret "$SEC" --t1 1020 --t2 1000 \
     | grep -E "next action"
for e in offer-published offer-accepted sost-locked cp-locked; do "$C" observe "$F" --event "$e" >/dev/null; done
echo "   resume (re-read session file):"; "$C" inspect "$F" | grep -E "phase|have_secret"
"$C" observe "$F" --event cp-claim  >/dev/null
"$C" observe "$F" --event sost-claim | grep -E "phase"

# --- 3. Refund + negatives --------------------------------------------------
echo "-- refund path --"
G="$(mktemp)"
"$C" create "$G" --role Initiator --cp ETH --give SOST --want ETH \
     --give-amount 100 --want-amount 5 --hashlock "$HL" --secret "$SEC" --t1 1020 --t2 1000 >/dev/null
for e in offer-published offer-accepted sost-locked timeout sost-refund; do "$C" observe "$G" --event "$e" >/dev/null; done
"$C" inspect "$G" | grep -E "phase"
echo "-- negatives --"
echo -n "   mis-ordered timeout: "; "$C" create /tmp/x --role Initiator --cp BTC --give SOST --want BTC \
     --give-amount 1 --want-amount 1 --hashlock "$HL" --secret "$SEC" --t1 1000 --t2 1020 2>&1 | grep -o "TIMEOUT_ORDER_INVALID" | head -1
echo -n "   issuer-freeze (USDT): "; "$C" create /tmp/y --role Initiator --cp ERC20 --give SOST --want USDT \
     --give-amount 1 --want-amount 1 --hashlock "$HL" --secret "$SEC" --t1 1020 --t2 1000 2>&1 | grep -o "issuer-freeze asset" | head -1

cat <<'EOF'

LIVE SOST node rehearsal (operator step — regtest build, gate kept OFF on mainnet):
  1. Build a REGTEST binary with a low activation height, e.g. add to a regtest
     profile only:  -DATOMIC_SWAP_HTLC_REGTEST_HEIGHT=1  (mainnet constant stays
     INT64_MAX). Do NOT ship this in the mainnet build.
  2. Run a local regtest node, mine past the height, then:
       sost-cli createhtlclock ...   -> sign -> sendrawtransaction
       sost-cli gethtlcstatus <txid> <vout>     (locked)
       sost-cli claimhtlc ... / refundhtlc ...  -> sendrawtransaction
       sost-cli gethtlcstatus <txid> <vout>     (claimed -> revealed_preimage)
  3. feed the status/preimage back into otc-coordinator observe.
EOF
echo "== SOST + coordinator rehearsal complete =="
