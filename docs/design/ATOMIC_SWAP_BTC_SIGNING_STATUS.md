# Atomic Swap — BTC signing status (Phase C.9 snapshot)

Where the BTC half of the SOST ↔ BTC atomic swap stands today, what
is already tested, what is intentionally still gated, and what is
missing to reach TESTNET READY.

## TL;DR

```
Branch:            feat/atomic-swap-htlc-v13-candidate
Latest C.* phase:  C.9 (this document)
Mainnet status:    SAFETY-CLOSED — every consensus and build gate
                   is OFF. No path to mainnet activation exists in
                   the code today.
Local test status: build OFF default works; build ON wires real
                   libwally signing for CLAIM/REFUND on regtest /
                   testnet (input-explicit only, no wallet, no
                   broadcast).
Next step:         fill in the bitcoind regtest harness body
                   (tests/harnesses/sost_btc_regtest.py).
```

## What is wired

| Layer | Status | Where it lives |
|---|---|---|
| BIP-173 / BIP-350 Bech32 address encode + decode | ✅ via libwally | `tests/test_atomic_swap_btc_test_vectors.cpp` §1, §3; `src/atomic_swap_btc_signing.cpp::EncodeP2WSHAddress` |
| P2WSH redeem script for the SOST HTLC | ✅ pure SOST code, no deps | `src/atomic_swap_btc.cpp::BuildBtcHtlcRedeemScript` |
| BIP-143 SegWit v0 sighash (P2WSH variant) | ✅ via libwally, byte-for-byte against the published BIP-143 vector `82dde6e4f1e94d02c2b7ad03d2115d691f48d064e9d52f58194a6637e4194391` | `tests/test_atomic_swap_btc_test_vectors.cpp` §5 |
| ECDSA Low-R / Low-S signing of a 32-byte message | ✅ via libwally `wally_ec_sig_from_bytes` + `EC_FLAG_GRIND_R` | `src/atomic_swap_btc_signing.cpp::SignBtcEcdsaTestVector` (Phase C.5) |
| DER signature encoding + sighash byte append | ✅ via libwally `wally_ec_sig_to_der` | `src/atomic_swap_btc_signing.cpp::SignBtcEcdsaTestVector` (Phase C.5) |
| ECDSA verification | ✅ via libwally `wally_ec_sig_verify` | `src/atomic_swap_btc_signing.cpp::VerifyBtcEcdsaTestVector` (Phase C.5) |
| CLAIM witness stack (4 elements: sig, preimage, 0x01, script) | ✅ | `src/atomic_swap_btc_signing.cpp::BuildBtcHtlcClaimWitness` (Phase C.6) |
| REFUND witness stack (3 elements: sig, empty, script) | ✅ | `src/atomic_swap_btc_signing.cpp::BuildBtcHtlcRefundWitness` (Phase C.6) |
| Unsigned segwit spending tx builder (1-in/1-out) | ✅ via libwally `wally_tx_init_alloc` + `wally_tx_add_raw_input` + `wally_tx_add_raw_output` | `src/atomic_swap_btc_signing.cpp::BuildBtcSpendingTxUnsignedHex` (Phase C.6) |
| **Public `SignBtcHtlcClaim`** (signed full tx hex) | ✅ in ON builds (input-explicit, no wallet) | `src/atomic_swap_btc_signing.cpp::SignBtcHtlcClaim` (Phase C.7) |
| **Public `SignBtcHtlcRefund`** (signed full tx hex) | ✅ in ON builds | `src/atomic_swap_btc_signing.cpp::SignBtcHtlcRefund` (Phase C.7) |
| Public `SignBtcHtlcLockFunding` | ❌ still disabled stub. Needs a UTXO selector and a fee estimator that this scope skipped intentionally. | `src/atomic_swap_btc_signing.cpp::SignBtcHtlcLockFunding` |
| bitcoind regtest happy-path harness | 🛠 SKIP scaffold only — bitcoind not on PATH today; Phase C.9+ will fill the body. | `tests/harnesses/sost_btc_regtest.py` (Phase C.8) |
| External cryptographic audit | ❌ not engaged | n/a |

## What stays OFF

| Gate | Value | Purpose |
|---|---|---|
| `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` | `INT64_MAX` | SOST consensus refuses every LOCK / CLAIM / REFUND tx until this is flipped to a real height. The four htlc-* CLI commands carry the same gate. |
| `SOST_BTC_HTLC_SIGNING` (CMake) | `OFF` (default) | When OFF, the entire signing surface in `src/atomic_swap_btc_signing.cpp` returns `disabled_result()`. The four legacy stubs AND the new Phase C.5/C.6/C.7 helpers are all inert. |
| `IsBtcHtlcSigningEnabled()` (runtime) | returns `false` always | Defence in depth. Even when the build flag is ON, this runtime probe stays `false` until a separate explicit operator opt-in lands. |

You cannot reach mainnet from the current source tree without
flipping AT LEAST the first two gates AND adding a non-trivial
operator path that does not exist yet. Both of those changes would
have to ship as their own auditable commit + announcement.

## How to build + run the ON path locally

The default build path (`SOST_BTC_HTLC_SIGNING=OFF`) requires
nothing beyond the normal SOST build dependencies. To exercise the
real signing path locally:

```bash
# 1. Initialise the libwally submodule (one-time).
git submodule update --init --recursive vendor/libwally-core

# 2. Build the vendored libwally static library + secp256k1-zkp.
tools/build_libwally.sh
# Produces:
#   vendor/libwally-core/src/.libs/libwallycore.a (~3.4 MB)
#   vendor/libwally-core/src/secp256k1/.libs/libsecp256k1.a (~2.3 MB)
#   vendor/libwally-core/src/secp256k1/.libs/libsecp256k1_precomputed.a (~1.1 MB)

# 3. Configure + build SOST with the signing backend enabled.
cmake -S . -B build-atomic-libwally \
      -DCMAKE_BUILD_TYPE=Release \
      -DSOST_ENABLE_PHASE2_SBPOW=ON \
      -DSOST_BTC_HTLC_SIGNING=ON
cmake --build build-atomic-libwally -j"$(nproc)"

# 4. Run the signing-side test binary. With libwally wired, it
#    covers Phase C.5/C.6/C.7 happy-path + adversarial assertions
#    in addition to the OFF-mode disabled-error invariants.
./build-atomic-libwally/test-atomic-swap-btc-signing
# Expected: "Summary: 80 passed, 0 failed"

# 5. Run the BTC vector binary too (Bech32 + BIP-143 sighash byte
#    matches against the published BIP value).
./build-atomic-libwally/test-atomic-swap-btc-test-vectors
# Expected: "executable PASS : 36, executable FAIL : 0"
```

The default build still works unchanged:

```bash
cmake -S . -B build-atomic-audit \
      -DCMAKE_BUILD_TYPE=Release \
      -DSOST_ENABLE_PHASE2_SBPOW=ON
cmake --build build-atomic-audit -j"$(nproc)"
./build-atomic-audit/test-atomic-swap-btc-signing
# Expected: "Summary: 45 passed, 0 failed" — every signing
# function reports the disabled-error envelope; no libwally is
# touched; no .a files are linked.
```

## How to run the regtest harness (scaffold today)

```bash
python3 -m pytest tests/harnesses/sost_btc_regtest.py -v
```

Without `bitcoind` + `bitcoin-cli` installed:

```
test_bitcoind_detection_runs              PASSED
test_btc_regtest_happy_path_claim         SKIPPED  (bitcoind not on PATH)
test_btc_regtest_happy_path_refund        SKIPPED  (bitcoind not on PATH)
```

With them installed (today):

```
test_bitcoind_detection_runs              PASSED
test_btc_regtest_happy_path_claim         SKIPPED  (scaffold body not yet implemented)
test_btc_regtest_happy_path_refund        SKIPPED  (scaffold body not yet implemented)
```

The two SKIP messages are different on purpose so the operator
can tell "tool missing" from "Phase C.9 still pending".

## Why mainnet is still closed

Atomic swap requires four orthogonal things to be true at the same
time, only one of which is in the SOST source tree today:

1. **SOST-side cryptography** — LOCK / CLAIM / REFUND validation
   rules, helpers, RPC, CLI. ✅ Done (Phase 3 series).
2. **BTC-side cryptography** — Bitcoin signature production that
   spends the P2WSH HTLC correctly. ✅ Done in lab (Phase C.7),
   but not yet exercised against a real Bitcoin node.
3. **Cross-chain coordination** — wallet state machine that
   matches T1 > T2 timeouts, prevents the responder from claiming
   SOST after refunding BTC, etc. ✅ State machine done (Phase
   4C-1, 39/39 tests); needs to be exercised against real-time
   tx flow.
4. **Counterparty BTC node access** — a Bitcoin node that the
   user can broadcast through. NOT a SOST concern — it is a
   wallet integration step.

Even with all four green, the activation requires:

- `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` flipped to `V14_HEIGHT`
  (= `15000`) in a coordinated hard fork.
- `SOST_BTC_HTLC_SIGNING` flipped to `ON` in the mainnet build
  recipe and the runtime `IsBtcHtlcSigningEnabled()` returning
  `true` (currently hard-wired to `false`).
- External cryptographic audit signed off on the BTC signing
  usage (libwally usage in C.5–C.7) AND the Solidity EVM
  counterpart (already 52/52 Foundry tests, but not externally
  audited).

Nothing in the current branch reaches any of those flips
automatically. They are all manual, single-purpose commits with
their own pre-deploy checklist (`docs/release/ATOMIC_SWAP_PRE_DEPLOY_CHECKLIST.md`).

## Checklist toward TESTNET READY

These are the items remaining BEFORE the atomic swap can be
exercised end-to-end against Bitcoin testnet (not mainnet):

- [ ] Install bitcoind on the dev machine. The harness scaffold
      will then enter the SCAFFOLD-BODY-PENDING SKIP path.
- [ ] Phase C.9+: implement the harness body
      (`tests/harnesses/sost_btc_regtest.py`):
  - [ ] Spin up bitcoind regtest in a temporary datadir.
  - [ ] Mine ≥101 blocks for coinbase maturation.
  - [ ] Build a SOST HTLC redeem script + derive its P2WSH
        bcrt1q… address via `EncodeP2WSHAddress`.
  - [ ] Fund the address from the regtest wallet.
  - [ ] Call `SignBtcHtlcClaim` to produce a signed claim tx;
        broadcast via `bitcoin-cli sendrawtransaction`; mine a
        block; assert the claimer received the funds and the
        preimage is visible in the witness on chain.
  - [ ] Same path for REFUND with `refund_height` past tip; mine
        enough blocks to pass CLTV; broadcast refund; assert
        refunder received the funds.
  - [ ] Tear down regtest + wipe tempdir on every test exit
        (including failure paths).
- [ ] Repeat the same harness shape on Bitcoin testnet (small
      tBTC amounts only), with the testnet `bitcoind` running
      locally. Document the testnet operator runbook.
- [ ] Wire `SignBtcHtlcLockFunding` (still a disabled stub):
      needs a UTXO selector + fee estimator. Decide whether the
      SOST CLI ships its own selector or delegates to a
      bitcoind/Bitcoin-RPC call.
- [ ] Add CI: a GitHub Actions workflow that installs bitcoind +
      runs the regtest harness on every PR. (Today the harness
      skips cleanly in CI, so adding it is a one-line YAML
      change once the body exists.)
- [ ] External cryptographic audit of: libwally call sites in
      `src/atomic_swap_btc_signing.cpp`, the witness assembly in
      `BuildBtcHtlc{Claim,Refund}Witness`, the BIP-143 sighash
      invocation, the sighash type byte appending, the
      destination-address decode path, AND the resulting raw tx
      hex against a battery of malicious inputs (oversize
      script, malformed bech32, weird HRP, etc.).

After all of the above are GREEN, only then does it make sense to
draft the mainnet activation commit (the two-gate flip described
in the "Why mainnet is still closed" section).
