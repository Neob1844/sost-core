# BTC HTLC — live bitcoind-regtest end-to-end (OTC-3a)

**Status:** DONE (regtest / review-only). This is the real `bitcoind`-regtest
round-trip that the `BTC_ATOMIC_SWAP_RUNBOOK` and `V15_OTC_BTC_REGTEST_GUIDE`
described as the remaining validation and that had been owner-waived (never
actually run against a live node). It has now been run.

**Safety invariants (unchanged):** `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX`
(SOST HTLC consensus gate stays OFF); `SOST_BTC_HTLC_SIGNING` OFF by default
(default build byte-identical, all signing fns `ok=false`); regtest ONLY, never
mainnet, never a real broadcast; no EVM change, no VPS change, no consensus change.

## Environment
- Bitcoin Core `bitcoind`/`bitcoin-cli` **v27.1**, `-regtest -txindex=1 -fallbackfee=0.0001`.
- SOST built with `-DSOST_BTC_HTLC_SIGNING=ON` (vendored libwally-core release_1.5.3,
  isolated bundled secp256k1) → real `BuildBtcHtlcRedeemScript`, BIP-143 segwit-v0
  sighash, Low-R/Low-S ECDSA, P2WSH witness assembly, `EncodeP2WSHAddress`,
  `SignBtcHtlcClaim` / `SignBtcHtlcRefund`.
- A small regtest driver links the SOST swap objects and calls the exact public API
  (`BuildBtcHtlcRedeemScript`→`BtcHtlcWitnessProgram`→`EncodeP2WSHAddress`, then
  `SignBtcHtlcClaim`/`SignBtcHtlcRefund`). bitcoind is used only as the consensus
  oracle: fund the P2WSH, broadcast the SOST-signed spends, confirm acceptance.

## Pre-checks (offline, ON backend)
- `test-atomic-swap-btc-signing` (ON): **121 passed / 0 failed**, incl. the BIP-143
  native-P2WSH known-answer vector (privkey `b8f28a77…` → pubkey `036d5c20…`).
  A passing ON run is a known-answer test against the Bitcoin spec.

## CLAIM path (preimage reveal) — real regtest txs
1. HTLC redeem script + P2WSH `bcrt1q…` address built by the SOST code.
2. Funded 0.5 BTC to the P2WSH; funding confirmed.
3. SOST-signed claim tx (306 bytes) **broadcast and ACCEPTED** by Bitcoin Core,
   confirmed (1 conf).
4. Witness stack has **4 items**; witness[1] = the 32-byte preimage, and it
   **matches** the agreed secret — i.e. the claim reveals the cross-chain secret
   on-chain exactly as the SOST↔BTC binding requires.

## REFUND path (CLTV timeout) — real regtest txs, incl. negative case
1. Second HTLC with `refund_height = tip+6`, funded 0.5 BTC.
2. **Negative:** refund tx broadcast BEFORE `refund_height` → **rejected `non-final`
   (error -26)** — CLTV enforced by real Bitcoin consensus, as intended.
3. Mined past `refund_height` (tip 114 ≥ 112); the same refund tx (271 bytes) is then
   **broadcast and ACCEPTED**, confirmed (1 conf). Witness has **3 items**
   (`sig`, `<empty>`→OP_ELSE, redeem_script); tx `nLockTime = 112 = refund_height`.

## What this proves
The SOST BTC HTLC redeem script, P2WSH address encoding, BIP-143 sighash and
witness assembly produce transactions that **real Bitcoin Core accepts on both
spend paths**, and that the timelock is enforced by consensus (early refund
rejected). Combined with the EVM leg (`forge test` 57/57) and the SOST-side C++
suite (ctest, atomic-swap targets), all three legs of the swap are now exercised
in test — never on mainnet, never with real funds.

## Still NOT done (unchanged from OTC-3a §7)
- `SignBtcHtlcLockFunding` remains a stub (funding done via `bitcoin-cli sendtoaddress`).
- External cryptographic + adversarial fee/locktime review before any thought of
  flipping `SOST_BTC_HTLC_SIGNING` on outside a lab.
- Mainnet BTC and any activation-height discussion remain out of scope.

## Reproduce
```
cmake -S . -B build-otc3a -DSOST_BTC_HTLC_SIGNING=ON -DCMAKE_BUILD_TYPE=Release \
  -DSOST_ENABLE_PHASE2_SBPOW=ON -DSOST_TESTNET_FORKS=OFF
cmake --build build-otc3a --target test-atomic-swap-btc-signing -j$(nproc)
./build-otc3a/test-atomic-swap-btc-signing         # 121/0 (ON)
# driver + regtest orchestration: see scripts/otc_rehearsal_btc_regtest.sh and
# docs/V15_OTC_BTC_REGTEST_GUIDE.md §5. NOTE: pass lock_txid to the signer in
# libwally internal (little-endian) byte order — reverse the big-endian txid that
# bitcoin-cli displays, or the claim/refund spends the wrong outpoint
# (bad-txns-inputs-missingorspent).
```
