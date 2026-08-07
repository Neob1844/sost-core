# BTC Atomic Swap HTLC — completion plan & honest state (FASE 1)

Answers "why is BTC fail-closed, and is it solvable?" and classifies every component. Verified against
the code at HEAD, not an old summary. **BTC is NOT a missing implementation — it is a real
libwally-core backend deliberately kept OFF + fail-closed until validated against a real Bitcoin node.**

## Why it is fail-closed (two deliberate safety decisions, not a bug)
1. **CMake `option(SOST_BTC_HTLC_SIGNING …) default OFF`** (CMakeLists.txt:413). OFF → the four signing
   entry points compile as inert stubs (`disabled_result()`, `ok=false`). ON → it builds the vendored
   `vendor/libwally-core` via ExternalProject and compiles the REAL libwally implementation
   (`SOST_BTC_HTLC_SIGNING_HAS_LIBWALLY`).
2. **`IsBtcHtlcSigningEnabled()` returns `false` even with the flag ON** (atomic_swap_btc_signing.cpp:46-62)
   — a second gate "until a real signing backend has been wired AND the operator explicitly toggles a
   runtime acknowledgement." So even an ON build refuses to sign.

Neither is a hidden defect; both fail closed (no fake-signed tx, no fund-loss path).

## Component classification (verified)
| Component | State | Evidence |
|-----------|-------|----------|
| HTLC redeem-script construction | **COMPLETE** | `BuildBtcHtlcRedeemScript`; test `atomic-swap-btc-script` |
| ECDSA sign/verify + pubkey derivation (test vectors) | **COMPLETE (real libwally)** | `DeriveBtcCompressedPubkey`, `SignBtcEcdsaTestVector`; test `atomic-swap-btc-test-vectors` |
| HTLC **claim** signing | **IMPLEMENTED (libwally, behind flag)** | `SignBtcHtlcClaim` — real `wally_tx_*` + sig |
| HTLC **refund** signing | **IMPLEMENTED (libwally, behind flag)** | `SignBtcHtlcRefund` |
| HTLC **lock funding** signing | **IMPLEMENTED (libwally, behind flag)** | `SignBtcHtlcLockFunding` (P2WPKH scriptCode, sha256, sig) |
| Tx serialization / witness / txid | **IMPLEMENTED (libwally)** | `BuildBtcSpendingTxUnsignedHex`, `BuildBtcHtlc{Claim,Refund}Witness`, `ComputeBtcTxid` |
| Preimage extraction (witness/tx) | **IMPLEMENTED** | `ExtractBtcHtlcPreimageFrom{WitnessStack,TxHex}` |
| Sighash / change / fee | **PARTIAL** (caller-supplied fee/change; segwit sighash in the sign path) | signing functions take amounts/fee from the caller |
| **UTXO / funding selection** | **BY DESIGN OPERATOR-PROVIDED** (no auto-selection from a node) | funding sign takes the input the caller supplies |
| **Broadcast / bitcoind RPC backend** | **MISSING (by design)** — the operator broadcasts the raw signed hex, exactly like the SOST-side CLI flow; no embedded bitcoind connection exists | grep: no bitcoind/sendrawtransaction/listunspent client in src/ |
| Runtime enable | **GATED HARD-OFF** | `IsBtcHtlcSigningEnabled()==false` |
| Persistence / restart-recovery | **PARTIAL** | `atomic_swap_watcher` persists swapId/txid/preimage/state (documented) |

## What OPTION B (real BTC) actually requires
1. Build with `SOST_BTC_HTLC_SIGNING=ON` (compiles the libwally path). — being verified now (build-btc-on).
2. Wire `IsBtcHtlcSigningEnabled()` behind an explicit config gate (default OFF for Option A).
3. Confirm the operator-broadcast design is acceptable (raw hex out → operator `sendrawtransaction`),
   OR add a thin optional bitcoind-RPC broadcast helper (does NOT couple SOST consensus to bitcoind).
4. **VALIDATION against a real bitcoind regtest** (fund → lock → confirm → redeem-with-preimage; and
   timeout → refund; + adversarial cases). **This is the true blocker** and needs a Bitcoin node.

## The honest limit
Everything except (4) is code and can be brought to "compiles + unit-green". **(4) cannot be done here**:
no `bitcoind`, and the owner waived the heavy/regtest validation (no second machine). Marking BTC signing
"REAL/READY" for real-fund custody WITHOUT a single real-Bitcoin round-trip would be dishonest — a subtle
sighash/serialization error is a silent fund-loss. So:

- **OPTION A (V15 + EVM, BTC OFF): READY** — the default build; BTC stays fail-closed; no bitcoind dependency.
- **OPTION B (V15 + EVM + real BTC): code can reach BUILDABLE + unit-green, but NOT READY** until a real
  bitcoind-regtest validation is run. That validation is the one external step still outstanding.

## Guarantee
Option A must remain deployable at all times. The BTC gate stays a config switch (default OFF); the SOST
node must build + run + serve V15 with `SOST_BTC_HTLC_SIGNING=OFF` and no `bitcoind` present.
