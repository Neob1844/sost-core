# Atomic Swap — BTC Counterparty Implementation Decision (Phase 4A-0)

**Branch:** `feat/atomic-swap-htlc-v13-candidate`
**Status:** design decision + minimal pure script-builder scaffolding.
**Gate:** `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT = INT64_MAX` (sentinel OFF).

This document fixes the engineering decisions for the BTC side of SOST
atomic swaps. The companion code (`include/sost/atomic_swap_btc.h` +
`src/atomic_swap_btc.cpp` + `tests/test_atomic_swap_btc_script.cpp`)
implements the **smallest safe subset**: deterministic redeemScript byte
assembly with no signing, no broadcast, no address derivation, and no
private key handling.

---

## 1. Vendor a library or implement minimal builder?

**Decision: minimal builder, no vendoring.**

The SOST repo already links:

  - `libsecp256k1` (ECDSA + Schnorr) — already used for SbPoW signatures.
  - `OpenSSL::Crypto` (SHA-256, RIPEMD-160) — already used for hash160,
    tx hashing, and PoPC commitments.

For the BTC HTLC we need only:

  - SHA-256 of the redeem script (for the future P2WSH witness program) —
    we already have this via OpenSSL.
  - Bitcoin opcode constants — fixed bytes (`OP_IF=0x63`, `OP_SHA256=0xa8`,
    `OP_EQUALVERIFY=0x88`, `OP_CHECKSIG=0xac`, `OP_ELSE=0x67`,
    `OP_CHECKLOCKTIMEVERIFY=0xb1`, `OP_DROP=0x75`, `OP_ENDIF=0x68`).
  - Pushdata encoding (`<N> + data` for N <= 75; `OP_PUSHDATA1/2/4` for
    longer) — trivial to implement in <30 lines.
  - ScriptNum minimal encoding for the absolute locktime — standard
    Bitcoin canonical encoding, <30 lines.

Vendoring `libbitcoin-system` or `bitcoin-core/src/script/*` would add
**megabytes of code**, an entire build system (cmake-conan or boost
dependency tree), and a maintenance surface that dwarfs the actual swap
requirement. None of that buys us safety we cannot achieve with 100
lines of well-tested byte assembly.

**However:** the moment we move beyond "redeemScript byte assembly" into
*signing* a Bitcoin transaction, that calculation flips. Signing
requires:

  - Bitcoin transaction serialization (varint, version, witness fields,
    SIGHASH variants).
  - BIP-143 / BIP-341 sighash calculation for SegWit / Taproot.
  - Bech32 / Bech32m address encoding (BIP-173 / BIP-350).
  - Careful handling of the SIGHASH byte and signature canonicalisation.

That second tier is not in this commit. When we get there (Phase 4A-2 or
4A-3) the choice will be between vendoring a Bitcoin library OR writing
~1,500 lines of cryptography-critical C++ that needs external review.

## 2. Recommended library choices and tradeoffs

For Phase 4A-0 (this commit) — **none required**. We use only the
existing `OpenSSL::Crypto` SHA-256.

For Phase 4A-1+ (when signing is needed) — three candidate paths:

| Library | Pros | Cons |
|---|---|---|
| `libbitcoin-system` | Battle-tested, full Bitcoin Core compatibility | C++17, Boost dependency, ~30MB build |
| `bitcoin-core/secp256k1` Schnorr extras | Already linked | Bitcoin-Core script engine is internal, not exposed as library |
| Custom minimal | Smallest binary, no new deps | Cryptography-critical code, requires external audit |

**Recommendation when Phase 4A-1 lands:** prefer vendoring
`libbitcoin-system` with a feature flag (`SOST_BTC_HTLC_SIGNING=ON`). Keep
default OFF so the existing build stays bit-identical for non-swap
operators.

## 3. Exact BTC HTLC script type

**Decision: P2WSH (BIP-141 SegWit v0).**

The redeem script is the BIP-199-style 6-leaf HTLC:

```
OP_IF
    OP_SHA256 <hashlock_32B> OP_EQUALVERIFY
    <claim_pubkey_33B> OP_CHECKSIG
OP_ELSE
    <refund_height_N> OP_CHECKLOCKTIMEVERIFY OP_DROP
    <refund_pubkey_33B> OP_CHECKSIG
OP_ENDIF
```

The witness program is `sha256(redeemScript)` (32 bytes). The P2WSH
address is `bech32(0, sha256(redeemScript))` and is computed by the
wallet at spend-time, not by this builder.

**Taproot (P2TR, BIP-341):** considered for Phase 4A-3 as a fee
optimisation. Not in scope for Phase 4A-0. Requires tap-leaf script
construction, x-only public keys, BIP-340 Schnorr signatures, and
Bech32m address encoding — all post-MVP.

## 4. Hashlock choice

**Decision: SHA-256(preimage), preimage = exactly 32 bytes.**

This matches the SOST-side hashlock byte-for-byte:

```cpp
// SOST consensus (src/tx_validation.cpp R21):
Bytes32 computed = sha256(preimage.data(), preimage.size());
if (computed != hashlock) return Fail(R21, "preimage mismatch");
```

```
// Bitcoin Script side:
OP_SHA256 <hashlock_32B> OP_EQUALVERIFY
```

Same primitive, same byte length, same result. A preimage that satisfies
the SOST claim also satisfies the BTC claim and vice versa. That
cross-chain compatibility is the load-bearing property of the atomic swap.

## 5. Timeout choice

**Decision: CLTV absolute block-height locktime.**

`OP_CHECKLOCKTIMEVERIFY` checks against the transaction's `nLockTime`
field (absolute, not relative). The refund_height in the redeem script
is a Bitcoin block height (NOT a SOST block height). The wallet selects
the BTC refund_height such that BTC's refund window opens **strictly
before** the SOST refund window (T2_btc < T1_sost) by a safety margin.

For initial bring-up the safety margin will be ~6 BTC blocks (~60 min)
plus the longest expected SOST block propagation latency. The exact
choice is documented in the timeout-margin section of the
implementation plan and revisited after external economic review.

The CSV (relative locktime, `OP_CHECKSEQUENCEVERIFY`) variant is NOT
used. Absolute heights are easier to reason about across two
asynchronous chains and easier to coordinate at the UI level.

## 6. Required deterministic test vectors

The redeem-script builder is pure byte assembly. Tests use hand-checked
fixed inputs and assert exact byte output. Three vectors:

  - **V1 (small height):** hashlock = `00 00 .. 00` (32B), refund_height = 0,
    pubkeys = `02 00 .. 00` (33B each). Smallest possible script;
    exercises edge case of zero ScriptNum encoding.
  - **V2 (typical):** hashlock = `de ad be ef .. 32B`, refund_height = 15000
    (3-byte ScriptNum), claim_pubkey = `02 11 22 .. 33B`,
    refund_pubkey = `03 aa bb .. 33B`. Realistic shape.
  - **V3 (large height):** refund_height = 0x7FFFFFFF (largest int32);
    confirms multi-byte ScriptNum encoding and the high-bit sign-extension
    rule does not over-allocate bytes.

Each vector also checks the SHA-256 of the produced script (the future
P2WSH witness program). The expected SHA-256 is computed at test write
time by hand-running `sha256sum` on the hex bytes; the test asserts the
builder reproduces the same hash.

## 7. Why writing full BTC script/signing from scratch is dangerous

The redeemScript byte assembly is safe to write from scratch because:

  - It produces a known byte sequence.
  - Tests pin the exact output.
  - Errors are visible (wrong bytes -> different sha256 -> different
    address -> coins go to the wrong place but **fail loudly** on the
    receiver's side, not silently to the attacker).

In contrast, **signing** is unsafe to write from scratch because:

  - BIP-143/BIP-341 sighash must hash the exact set of fields in the
    exact order; a single field wrong yields a valid-looking signature
    that BTC nodes reject but that an attacker could exploit via
    fault-injection at the wallet boundary.
  - Bech32 / Bech32m has a complex polymod that is easy to get subtly
    wrong; wrong checksum -> wrong address -> funds lost.
  - SIGHASH_ALL vs SIGHASH_SINGLE vs SIGHASH_NONE — a wrong byte enables
    transaction malleation by miners.
  - Low-S enforcement (BIP-66) — a non-canonical signature is rejected by
    relay; an old wallet might produce one and lose its tx forever in
    the mempool.

Each of those is the kind of bug that loses real money silently. They
demand either an audited library or external cryptographic review of
the from-scratch code.

**This commit ships only the safe subset.** Signing comes later, with
either a vendored library OR external review of the from-scratch path.

## 8. File plan for the next commit

This commit adds:

  - `include/sost/atomic_swap_btc.h` — public API surface (4 functions):
      * `BuildBtcHtlcRedeemScript(hashlock, refund_height, claim_pubkey, refund_pubkey) -> bytes`
      * `BtcHtlcWitnessProgram(redeem_script_bytes) -> Bytes32`
      * `EncodeScriptNumMinimal(int64) -> bytes` (helper, useful for the
        future signing module)
      * `EncodePushdata(bytes) -> bytes` (helper, same)
  - `src/atomic_swap_btc.cpp` — implementation (<200 lines, no I/O,
    no signing, no addresses, no keys).
  - `tests/test_atomic_swap_btc_script.cpp` — 3 deterministic vectors
    plus 3 helper-unit tests (ScriptNum encoding edge cases).
  - `CMakeLists.txt` — wire the new test executable.

The NEXT commit (Phase 4A-1, **not in this PR**) will be either:

  - Add `libbitcoin-system` as a CMake `FetchContent` dependency with a
    `SOST_BTC_HTLC_SIGNING=OFF` default flag, OR
  - Write the from-scratch BIP-143 sighash + signing path under explicit
    external review.

That decision belongs to the next sprint, not this one.
