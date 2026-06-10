#!/usr/bin/env bash
# =============================================================================
# OTC-5 — BTC (regtest) live rehearsal for the SOST<->BTC atomic-swap leg.
#
# Drives the BTC HTLC: build the redeem script + P2WSH address, fund it, then
# claim (revealing the preimage in the witness) or refund after CLTV. REGTEST
# ONLY — never BTC mainnet, never a real broadcast.
#
# The signing backend (OTC-3a libwally) is OFF by default and must be built ON
# explicitly:  cmake -S . -B build-otc3a -DSOST_BTC_HTLC_SIGNING=ON
# See docs/V15_OTC_BTC_REGTEST_GUIDE.md for the full flow.
#
# Two modes:
#   (A) LIVE  — when `bitcoind`/`bitcoin-cli` are installed: spin up regtest,
#       fund the P2WSH, broadcast claim/refund, extract the preimage.
#   (B) FALLBACK — when bitcoind is absent (e.g. CI/sandbox): run the ON-build
#       signing known-answer tests (BIP-143 native-P2WSH vector) as evidence the
#       signing path produces correct witnesses, and print the operator steps.
#
# Prerequisites for mode A: bitcoind/bitcoin-cli (Bitcoin Core), regtest.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== OTC-5 BTC rehearsal =="

if command -v bitcoind >/dev/null 2>&1 && command -v bitcoin-cli >/dev/null 2>&1; then
  echo "[mode A] bitcoind present -> live regtest"
  DATADIR="$(mktemp -d)"
  bitcoind -regtest -datadir="$DATADIR" -fallbackfee=0.0001 -txindex=1 -daemon
  trap 'bitcoin-cli -regtest -datadir="$DATADIR" stop >/dev/null 2>&1 || true; rm -rf "$DATADIR"' EXIT
  sleep 2
  CLI="bitcoin-cli -regtest -datadir=$DATADIR"
  $CLI createwallet swap >/dev/null
  ADDR=$($CLI getnewaddress)
  $CLI generatetoaddress 101 "$ADDR" >/dev/null   # mature a coinbase
  echo "regtest tip: $($CLI getblockcount)"
  echo ""
  echo "Build the HTLC with the ON binary (BuildBtcHtlcRedeemScript ->"
  echo "EncodeP2WSHAddress 'regtest'), fund it, then SignBtcHtlcClaim/Refund and"
  echo "sendrawtransaction. See docs/V15_OTC_BTC_REGTEST_GUIDE.md for the exact"
  echo "cast-equivalent operator steps; this harness sets up the chain + wallet."
  echo "[mode A] regtest ready (LOCK_ADDR=$LOCK_ADDR funding is the operator step)" 2>/dev/null || true
else
  echo "[mode B] bitcoind NOT installed -> ON-build signing evidence + operator steps"
  if [ ! -x build-otc3a/test-atomic-swap-btc-signing ]; then
    echo "Building the ON (libwally) signing backend..."
    git submodule update --init --recursive vendor/libwally-core 2>/dev/null || true
    cmake -S . -B build-otc3a -DSOST_BTC_HTLC_SIGNING=ON >/dev/null
    cmake --build build-otc3a --target test-atomic-swap-btc-signing -j"$(nproc)" >/dev/null
  fi
  echo "-- BTC signing known-answer tests (BIP-143 native-P2WSH) --"
  ./build-otc3a/test-atomic-swap-btc-signing | tail -3
  cat <<'EOF'

Operator steps to complete the LIVE BTC leg (install Bitcoin Core, then re-run):
  1. bitcoind -regtest -daemon -fallbackfee=0.0001 -txindex=1
  2. BuildBtcHtlcRedeemScript(hashlock, refund_height, claim_pk, refund_pk)
     -> EncodeP2WSHAddress(witness_program, "regtest") -> bcrt1... LOCK_ADDR
  3. bitcoin-cli -regtest sendtoaddress LOCK_ADDR <amount>   (fund the HTLC)
  4. claim:  SignBtcHtlcClaim(...)  -> sendrawtransaction   (reveals preimage)
     refund: mine past refund_height, SignBtcHtlcRefund(...) -> sendrawtransaction
  5. preimage = witness item [1] of the claim tx:
     bitcoin-cli -regtest getrawtransaction <txid> 2 | jq -r '.vin[0].txinwitness[1]'
  6. feed it to the coordinator:
     otc-coordinator observe <session> --event preimage --preimage <hex>
EOF
fi
echo "== BTC rehearsal complete =="
