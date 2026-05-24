# Atomic Swap — BTC Signing STOP Report (Phase 4A-1)

**Branch:** `feat/atomic-swap-htlc-v13-candidate`
**Decision:** **STOP** — do not write BTC signing in this commit.
Ship disabled-stub scaffold + this report.
**Gate:** `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (unchanged).
**CMake flag:** `SOST_BTC_HTLC_SIGNING = OFF` (default) — when later
flipped ON, the build will define `SOST_BTC_HTLC_SIGNING_ENABLED` so
the wrapper can detect the future integrated backend.

---

## Why "stop and report" instead of "implement"

Writing BTC signing from scratch is the **most fund-loss-prone task in
the entire atomic-swap stack**. A redeem-script byte assembly (Phase
4A-0) is safe to write from scratch because:
  - it produces a fixed byte sequence
  - any error is loud (the address derived from the script hash is
    different, so funds go nowhere reachable by the spender)
  - tests pin the exact output bytes

In contrast, transaction signing requires:

| Component | Spec | Why it's dangerous from scratch |
|---|---|---|
| SegWit v0 tx serialization | BIP-141, BIP-144 | Witness-vs-non-witness serialization is two formats sharing one structure. A wrong serialization variant gives a tx that some nodes accept and others reject. |
| Sighash for P2WSH | BIP-143 | The sighash hashes a precise sequence of fields (`hashPrevouts`, `hashSequence`, `outpoint`, `scriptCode`, `amount`, `nSequence`, `hashOutputs`, `nLockTime`, `sighashType`). A single field wrong yields a signature that LOOKS valid (correct shape) but doesn't actually authorise the spend. Worst: it may authorise a *different* spend an attacker can exploit. |
| Bech32 / Bech32m address | BIP-173, BIP-350 | The polymod uses a 30-bit checksum over a base-32 alphabet. The reference implementation has known subtleties (`Bech32` vs `Bech32m` constant differs by one, easy to confuse). A wrong polymod yields a string that LOOKS like an address but routes funds elsewhere. |
| Signature canonicalisation | BIP-62 / BIP-66 / low-S | A non-canonical signature is rejected by node relay; a wallet that produces one finds its tx stuck in mempool. Worse: low-S enforcement protects against malleation, and getting low-S subtly wrong (e.g., using `s` instead of `n - s` at the boundary) lets miners malleate the txid. |
| SIGHASH byte | spec | `SIGHASH_ALL` vs `SIGHASH_SINGLE` vs `SIGHASH_NONE` differ by one byte appended to the signature. Wrong byte = different fields signed = wrong authorisation. |

Every line above is a documented case in the wild where projects lost
funds because of subtle from-scratch bugs in one of these primitives.

**Mitigation:** vendor an audited library or have the from-scratch
code externally reviewed. **This commit does neither — it stops, ships
the API surface as disabled stubs, and documents the path.**

---

## What ships in this commit

1. `include/sost/atomic_swap_btc_signing.h` — fixed public API surface:
   - `IsBtcHtlcSigningEnabled() -> bool`
   - `SignBtcHtlcClaim(...)` — claim path stub
   - `SignBtcHtlcRefund(...)` — refund path stub
   - `SignBtcHtlcLockFunding(...)` — lock funding tx stub
   - `EncodeP2WSHAddress(...)` — Bech32 address stub
   - `BtcSigningResult { ok, error, raw_tx_hex }`
   - `BtcAddressResult { ok, error, address }`
   The signatures pin what the future implementation must accept. The
   wallet / coordinator layers (Phase 4C-1) can be written against
   this API NOW; the future drop-in replacement will not change the
   surface.

2. `src/atomic_swap_btc_signing.cpp` — disabled stubs.
   Every function returns `BtcSigningResult{ok=false, error="...
   disabled. See docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md
   for the library selection plan and audit requirements."}`. The
   privkey parameters are accepted (to fix the API) but **never
   read**, never copied, never logged.

3. `tests/test_atomic_swap_btc_signing.cpp` — 13 assertions:
   - Build flag OFF by default.
   - SOST consensus gate stays INT64_MAX.
   - Each of the 4 gated functions returns ok=false with the
     disabled-error message and an empty result field.
   - The error message references this report file path so any caller
     hitting the stub knows where to read.

4. `CMakeLists.txt` — adds the option:
   ```
   option(SOST_BTC_HTLC_SIGNING "Enable BTC HTLC signing backend (requires vendored Bitcoin library)" OFF)
   if (SOST_BTC_HTLC_SIGNING)
       target_compile_definitions(sost-core PRIVATE SOST_BTC_HTLC_SIGNING_ENABLED=1)
   endif()
   ```
   Default OFF. When flipped ON in a future build, `IsBtcHtlcSigningEnabled()`
   still returns false until a real backend is wired in (the helper has
   an extra runtime gate to prevent accidental activation).

---

## Candidate signing libraries (next-sprint selection)

The future Phase 4A-2 sprint integrates ONE of:

### Option A — libbitcoin-system

  - **Pros:** maintained, BSD-style license, complete Bitcoin
    transaction support (SegWit + Taproot), well-tested.
  - **Cons:** heavy Boost dependency; binary size ~30 MB; adds a non-
    trivial CMake integration surface.
  - **Audit status:** maintained by libbitcoin org since 2011; widely
    used but no recent external-audit report visible.
  - **Integration shape:** `FetchContent_Declare(libbitcoin-system ...)`
    behind `SOST_BTC_HTLC_SIGNING=ON`. When the flag is OFF, the
    library is not fetched and not linked.

### Option B — libwally-core (ElementsProject)

  - **Pros:** smaller than libbitcoin-system; C with Python bindings;
    actively maintained; used by major wallets (Blockstream Green,
    Sparrow); well-fuzzed by oss-fuzz.
  - **Cons:** API is wallet-oriented; some functions require careful
    parameter conversion for raw tx construction.
  - **Audit status:** subject to active fuzz testing via oss-fuzz; no
    full external audit report visible but production deployments
    are extensive.
  - **Integration shape:** `pkg_check_modules(WALLY libwallycore)` or
    git-submodule + CMake guard.

### Option C — Bitcoin Core's `src/script/` directly

  - **Pros:** the reference implementation; the most-reviewed Bitcoin
    code in existence.
  - **Cons:** not packaged as a library; would require copying
    individual files (`script.cpp`, `interpreter.cpp`,
    `script/sigcache.cpp`, `bech32.cpp`, `key.cpp`) and their internal
    dependencies. Effectively forking a slice of Bitcoin Core.
  - **Audit status:** continuously audited as part of Bitcoin Core
    maintenance.
  - **Integration shape:** vendor a tagged release subset into
    `contracts/atomic-swap/btc-vendored/` with attribution + LICENSE.

### Option D — from-scratch with external audit

  - **Pros:** smallest binary delta; no external dependency.
  - **Cons:** every line is cryptography-critical and must be
    externally reviewed. Audit cost likely exceeds the vendoring
    cost. Slowest path to a usable backend.
  - **Audit status:** by definition, none until written.

**Recommendation:** Option B (libwally-core) for the next sprint. The
maintenance burden is small, the binary is light, fuzz coverage is
extensive, and the API maps cleanly to the SOST atomic-swap surface.
Option A is a fallback if libwally turns out to lack a feature we
need.

---

## Test-vector requirements before flipping the flag

Before `SOST_BTC_HTLC_SIGNING_ENABLED` may be defined in a release
build, the wrapper implementation MUST pass at least the following
deterministic test vectors:

| Vector source | What it verifies |
|---|---|
| BIP-143 test vectors (P2WSH branch) | Sighash byte-equality for known inputs |
| BIP-173 test vectors (Bech32 valid + invalid lists) | Address encoding correctness |
| BIP-350 test vectors (Bech32m) | If Taproot support is added |
| Bitcoin Core `test/data/script_tests.json` (HTLC-shaped subset) | Script execution semantics |
| Hand-built SOST <-> testnet vectors | End-to-end happy path on Bitcoin testnet (no mainnet) |
| Hand-built timeout vectors | Refund path triggers exactly at refund_height |
| Hand-built wrong-preimage vectors | Spend with wrong preimage rejected by Bitcoin nodes |

These vectors live in a future
`tests/test_atomic_swap_btc_signing_vectors.cpp` and run with the
existing CTest framework. The flag flip commit must be accompanied by
a green run of that test binary.

---

## Activation prerequisites

The flag flip
(`SOST_BTC_HTLC_SIGNING=ON` AND a real backend wired) is NOT
sufficient on its own. The full SOST atomic-swap activation
(`ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = V14_HEIGHT`) requires:

  1. This signing backend integrated and the test vectors above all
     green.
  2. Phase 4B-1 EVM contract (already done on this branch, commit
     `52d2fce`).
  3. Phase 4C-1 cross-chain coordinator state machine.
  4. End-to-end testnet swaps (SOST testnet ↔ Bitcoin testnet ↔
     Sepolia ETH ↔ Sepolia ERC-20). Happy path AND timeout-refund
     path verified on real chains.
  5. External cryptographic + economic review of the full stack
     (SOST consensus rules R17-R24 + BTC redeem script + BTC signing
     backend + EVM contract + coordinator).

See `docs/reviews/ATOMIC_SWAP_PRE_ACTIVATION_REVIEW.md` for the full
re-flip checklist.

---

## Sprint plan (Phase 4A-2 — when ready)

```
Day 1-2: vendor libwally-core via CMake FetchContent under
         SOST_BTC_HTLC_SIGNING=ON. Build + smoke test in isolation.

Day 3:   wire SignBtcHtlcClaim against the library. Pass BIP-143
         test vectors. Verify the produced raw_tx_hex byte-equals
         a known-good hand-crafted hex (this is the load-bearing test).

Day 4:   wire SignBtcHtlcRefund + SignBtcHtlcLockFunding. Same
         vector-equality discipline.

Day 5:   wire EncodeP2WSHAddress against BIP-173 vectors. Validate
         the address derived from a known witness program matches
         the bitcoin-cli `decodescript` output for that script.

Day 6:   regtest end-to-end smoke. Spin up a local Bitcoin regtest
         node, fund a wallet, lock 0.1 BTC into an HTLC built by our
         library, claim with the preimage, refund a second HTLC
         after timeout. Both flows complete cleanly.

Day 7:   testnet end-to-end smoke. Same flow on Bitcoin testnet.
         Document tx hashes for replay.

Day 8-9: external review handoff. Package the diff + the BIP test
         vectors + the regtest + testnet artefacts for the auditor.

Day 10+: address audit findings. Once GREEN, schedule the flag flip
         commit AND the gate flip commit in the same release.
```

This sprint is **independent of SOST consensus work**. It can happen
in parallel with V13 deployment, V14 planning, or any other protocol
sprint. The wallet / coordinator layers that consume this API can be
written today against the disabled stubs and the future activation is
a no-API-change wire-up.
