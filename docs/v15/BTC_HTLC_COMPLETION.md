# BTC Atomic Swap — HTLC completion (OTC-6)

Completes the BTC Atomic Swap code end-to-end **around** the already-complete
pure signing module, WITHOUT changing consensus, the deployed V15 node, miners,
or the BTC gate default. **BTC stays OFF in production** (Option A). This branch
(`feat/btc-atomic-swap-complete`, off `main` @ V15/25000) adds the layers the
inventory flagged as MISSING/PARTIAL.

## What existed before (unchanged, verified COMPLETE)
The pure signing module `atomic_swap_btc_signing.*` already did — behind
`SOST_BTC_HTLC_SIGNING=ON` + libwally — redeem-script, funding/claim/refund
signing, witnesses, BIP-143 sighash (Low-R), preimage extraction, txid. It never
touches the network by design.

## What OTC-6 adds (this branch)

| Component | File | State | Test |
|-----------|------|-------|------|
| **Bitcoin backend** (broadcast + getrawtx + status + height + feerate + listunspent) over JSON-RPC, injectable transport | `src/bitcoin_backend.cpp`, `include/sost/bitcoin_backend.h` | **COMPLETE** | `test-bitcoin-backend` 29/29 |
| **Null backend** (fail-closed default) + **factory** gated on `SOST_BTC_ATOMIC_SWAP_ENABLED` + `BTC_RPC_*` | same | **COMPLETE** | same |
| **Swap state machine** (Created→…→Redeemed/Refunded/Failed), idempotent, double-spend guard | `src/btc_swap_state.cpp`, `include/sost/btc_swap_state.h` | **COMPLETE** | `test-btc-swap-state` 34/34 |
| **Persistable record** (funding txid/vout/amount, redeem script, refund height, claim/refund txids, preimage) + serialize/parse | same | **COMPLETE** | same |
| **Funding coin-selection** (accumulative largest-first, SegWit vsize fee model, dust-aware change) | `src/btc_funding.cpp`, `include/sost/btc_funding.h` | **COMPLETE** | `test-btc-funding` 26/26 |
| **Funding orchestration** (selection → gated `SignBtcHtlcLockFunding`) | same | **COMPLETE (gated)** | same |
| **BTC-leg watch decision** (Wait/WaitConfirmations/Claim/Refund/Done), reorg-aware | `src/btc_watch.cpp`, `include/sost/btc_watch.h` | **COMPLETE** | `test-btc-watch` 26/26 |
| **Restart-recovery store** (0600 file, atomic write) | same | **COMPLETE** | same |
| **Chain reconciliation** (idempotent check-before-send; no double-spend on restart) | same | **COMPLETE** | same |
| **Dashboard gating** (BTC mirrors `SOST_BTC_ATOMIC_SWAP_ENABLED`, default OFF → "Coming soon") | `website/js/atomic-swap-evm.js`, `website/atomic-swap.html` | **COMPLETE** | manual |

Total new unit assertions: **115** (29+34+26+26), all green in Option A (BTC OFF)
and Option B (BTC ON). No regression in the existing atomic-swap suite.

## Fund-safety invariants preserved
- **Option A is always deployable.** With `SOST_BTC_HTLC_SIGNING=OFF` the node
  builds with **0 libwally/BTC symbols** and no bitcoind dependency. The factory
  hands back a `NullBitcoinBackend`; every backend call fails closed.
- **Runtime gate default OFF.** A live backend is constructed ONLY when
  `SOST_BTC_ATOMIC_SWAP_ENABLED=1` AND `BTC_RPC_*` are all set.
- **No consensus reach.** None of OTC-6 is called from consensus; it is
  wallet/OTC tooling. Private keys are never stored or logged. The preimage is
  persisted only in a 0600 file.
- **No double-spend on recovery.** The state machine's `changed` flag + chain
  reconciliation mean a retry after a crash re-broadcasts nothing.

## The one thing still pending (owner-waived here)
End-to-end **real `bitcoind`-regtest validation** (fund→lock→confirm→claim-with-
preimage; timeout→refund; adversarial) — the "true blocker" from
`BTC_HTLC_COMPLETION_PLAN.md`. The code is complete and unit-green, but a real
BTC round-trip has NOT been run (no bitcoind in this environment; owner waived
the heavy validation). Until that runs, treat the byte-order/sighash of the
signed spending path as **unvalidated against a live network** — which is exactly
why BTC stays gated OFF. This is `OPTION B: CODE READY, NOT ACTIVATED`.

See `BTC_ATOMIC_SWAP_RUNBOOK.md` for how to configure + run the regtest
validation and how to (eventually) enable BTC.
