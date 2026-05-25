# Atomic Swap — BTC test vector gap

**Status:** PLAN ONLY. Captures the official BTC test vectors that
the future Phase C real signing backend MUST pass before any flip of
`SOST_BTC_HTLC_SIGNING=ON` or `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT`.

**Companion artifact:** `tests/test_atomic_swap_btc_test_vectors.cpp`
(the executable harness). Sections in this doc match sections in the
test file. Vectors marked PENDING in the test output correspond
one-to-one with the vectors listed below.

**Context:** Phase B per the atomic-swap master command. Until
libwally-core is vendored (see
`docs/design/ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md`), the SOST
codebase has no Bech32 / Bech32m encoder, no BIP-143 sighash
implementation, and no Schnorr / ECDSA signing path for Bitcoin.
This document is the contract Phase C must satisfy, expressed as
test vectors with known expected outputs.

---

## 1. BIP-173 Bech32 (mainnet/testnet/regtest hrp = "bc"/"tb"/"bcrt")

Reference: <https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki>

### 1.1 Valid vectors (must round-trip cleanly)

The harness loads 5 representative vectors from the BIP's full set.
Phase C MUST also verify the full battery below:

| encoded | hrp | data part bits (5-bit groups, hex) | notes |
|---|---|---|---|
| `A12UEL5L` | `a` | (empty data) | min length |
| `a12uel5l` | `a` | (empty data) | lowercase |
| `abcdef1qpzry9x8gf2tvdw0s3jn54khce6mua7lmqqqxw` | `abcdef` | hex from BIP | |
| `split1checkupstagehandshakeupstreamerranterredcaperredlc445v` | `split` | hex from BIP | mixed-case attack rejected, all-lowercase OK |
| `?1ezyfcl` | `?` | (empty data) | non-alphanumeric hrp |
| `BC1QW508D6QEJXTDG4Y5R3ZARVARY0C5XW7KV8F3T4` | `bc` | hex from BIP | P2WPKH mainnet |
| `tb1qrp33g0q5c5txsp9arysrx4k6zdkfs4nce4xj0gdcccefvpysxf3qccfmv3` | `tb` | hex from BIP | P2WSH testnet |
| `bc1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7k7grplx` | `bc` | hex from BIP | P2WPKH-like SegWit v1 (would now be Bech32m per BIP-350) |

### 1.2 Invalid vectors (must be rejected)

| encoded | reason for rejection |
|---|---|
| `10a06t8` | empty HRP |
| `1qzzfhee` | HRP "1" with checksum miss |
| `A1G7SGD8` | invalid checksum |
| `a12UEL5L` | mixed case |
| `x1b4n0q5v` | invalid character `b` in data part |
| `li1dgmt3` | checksum miss |
| `de1lg7wt\xff` | invalid trailing byte |
| `tb1pw508d6qejxtdg4y5r3zarvary0c5xw7kw508d6qejxtdg4y5r3zarvary0c5xw7k7grplx` | SegWit v1 encoded as Bech32 (must be Bech32m, see §2) |
| `BC1QR508D6QEJXTDG4Y5R3ZARVARYV98GJ9P` | invalid program length for SegWit v0 |
| `bc1zw508d6qejxtdg4y5r3zarvaryvqyzf3du` | invalid program length |

Phase C's Bech32 decoder MUST reject every entry in 1.2 and accept
every entry in 1.1. Round-trip property: decode(encode(x)) == x for
all valid (hrp, witness version, witness program) tuples.

---

## 2. BIP-350 Bech32m (Taproot / SegWit v1+)

Reference: <https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki>

### 2.1 Valid vectors

| encoded | hrp |
|---|---|
| `A1LQFN3A` | `a` |
| `a1lqfn3a` | `a` |
| `an83characterlonghumanreadablepartthatcontainsthetheexcludedcharactersbio1tt5tgs` | very long |
| `abcdef1l7aum6echk45nj3s0wdvt2fg8x9yrzpqzd3ryx` | `abcdef` |
| `?1v759aa` | `?` |

### 2.2 Notes

The default HTLC path in
`include/sost/atomic_swap_btc.h::BuildBtcHtlcRedeemScript()` produces
a SegWit v0 P2WSH script. SegWit v0 outputs use plain Bech32 (§1),
not Bech32m. Bech32m is only needed if a counterparty insists on
receiving the BTC leg into a Taproot (P2TR) address. The vectors
here exist so that future Taproot-capable HTLC variants have a ready
verification harness, but Phase C is allowed to defer §2 to a
follow-up commit if Taproot support is not in the initial scope.

---

## 3. P2WSH witness program generation (EXECUTABLE TODAY)

P2WSH witness program = `SHA-256(redeem_script)`.

The harness today calls:

```cpp
auto script = BuildBtcHtlcRedeemScript(hashlock, refund_height,
                                       claim_pkh, refund_pkh);
Bytes32 witness_program = BtcHtlcWitnessProgram(script);
Bytes32 manual          = sost::sha256(script.data(), script.size());
assert(witness_program == manual);
```

The assertion passes with the current codebase. No Phase C dependency.

For a fixed input tuple
`(hashlock = 0x01..0x20, refund_height = 1008, claim_pkh = 0xA0..0xB3,
refund_pkh = 0xB0..0xC3)`,
the witness_program printed by the harness can be pinned as a fixed
expected output once Phase C lands — this gives Phase C a "no
regression" guard.

---

## 4. HTLC redeem script hash determinism (EXECUTABLE TODAY)

For any tuple `(hashlock, refund_height, claim_pkh, refund_pkh)`:
- Two consecutive calls to `BuildBtcHtlcRedeemScript()` MUST produce
  byte-identical output.
- The `sha256()` of that output MUST be byte-identical too.
- Changing any single byte of any input MUST produce a different
  output (avalanche property).
- Changing only the refund_height (by 1) MUST produce a different
  hash — this prevents two HTLCs with different timeouts from
  accidentally sharing a UTXO.

All four properties are verified today. No Phase C dependency.

---

## 5. BIP-143 SegWit v0 sighash (Native P2WSH variant)

Reference: <https://github.com/bitcoin/bips/blob/master/bip-0143.mediawiki>
"Native P2WSH" example, captured verbatim in the harness:

| field | value |
|---|---|
| raw unsigned tx (hex) | `0100000002fe3dc9208094f3ffd12645477b3dc56f60ec4fa8e6f5d67c565d1c6b9216b36e0000000000ffffffff0815cf020f013ed6cf91d29f4202e8a58726b1ac6c79da47c23d1bee0a6925f80000000000ffffffff0100f2052a010000001976a914a30741f8145e5acadf23f751864167f32e0963f788ac00000000` |
| scriptCode (hex) | `21026dccc749adc2a9d0d89497ac511f760f45c47dc5ed9cf352a58ac706453880aeadab21038d27d72ba1dc81c5fa0aac0aada3a1c5d3eb6f8e2b33a55fcc637c69e5d4e4ac5fac` |
| input amount (sat) | `4900000000` |
| expected sighash | `82dde6e4f1e94d02c2b7ad03d2115d691f48d064e9d52f58194a6637e4194391` |

Phase C MUST:
1. Compute the BIP-143 sighash from these inputs (with `SIGHASH_ALL`
   = 0x01) and assert byte-equality with the expected sighash.
2. Reject malformed `scriptCode` (length 0, negative implied
   pushdata length, etc.) with a clear error.
3. Reject negative `input amount`.
4. NEVER accept SIGHASH_NONE or SIGHASH_SINGLE in the HTLC path —
   only SIGHASH_ALL is meaningful for atomic swaps. (This is a
   policy gate, not a BIP-143 requirement, but the harness will
   enforce it.)

---

## 6. Additional HTLC-specific Phase C vectors (to be authored)

These vectors do not exist in any BIP because they describe the
specific BIP-199 HTLC redeem script we build:

1. **CLAIM path success.** Given a redeem script `R`, a preimage `p`
   with `SHA-256(p) == hashlock(R)`, a claim signature `s` valid
   under `claim_pkh(R)`, and a funding tx outpoint `O`, the spending
   tx MUST validate under standard script rules.
2. **CLAIM path with wrong preimage MUST fail.** Same as 6.1 but
   `SHA-256(p) != hashlock(R)`.
3. **CLAIM path with valid preimage but wrong signature MUST fail.**
4. **REFUND path success.** After `block.height >= refund_height(R)`,
   a refund signature valid under `refund_pkh(R)` MUST be sufficient
   to spend.
5. **REFUND path before timeout MUST fail.**
6. **REFUND path with valid signature but wrong pubkey MUST fail.**

These six adversarial vectors are mirror images of the SOST-side
HTLC validation rules R19-R24 already in
`src/tx_validation.cpp`. Phase C should implement them against
libwally + bitcoin-core's regtest to get end-to-end coverage.

---

## 7. Verification matrix

| section | executable today | requires Phase C | requires Taproot |
|---|---|---|---|
| §1 BIP-173 Bech32 vectors | data only | yes (encode/decode) | no |
| §2 BIP-350 Bech32m vectors | data only | yes (encode/decode) | yes |
| §3 P2WSH witness program | YES | no | no |
| §4 redeem script determinism | YES | no | no |
| §5 BIP-143 sighash | data only | yes (full sighash) | no |
| §6 HTLC-specific vectors | scaffolding only | yes (end-to-end) | no |

When all "data only" / "yes" cells turn green in the Phase C
harness output, the BTC-side coverage that audit will need is in
place. Until then the harness exits 0 with PASS for §3 + §4 and
PENDING for everything else.

---

## 8. Out of scope for this commit

- Implementing Bech32 / Bech32m encoders in pure SOST C++ (would
  duplicate libwally; explicitly avoided per the atomic-swap master
  command's "no from-scratch crypto" rule).
- Implementing BIP-143 sighash in pure SOST C++ (same reason).
- Implementing Schnorr or ECDSA signing (Phase C territory; gated
  behind libwally per §1 of the integration review doc).
- Wiring the test vectors into CI / GitHub Actions (deferred until
  the harness can actually execute against libwally).
- Bitcoin testnet / regtest end-to-end coverage (Phase 4D / Phase E
  territory, NOT in scope for Phase B).

---

**Audit trail:**
- `tests/test_atomic_swap_btc_test_vectors.cpp` — executable harness
  that loads every vector listed above and asserts the executable
  subset on every test run.
- `CMakeLists.txt` — adds the new `test-atomic-swap-btc-test-vectors`
  binary and registers it with CTest.
- `docs/design/ATOMIC_SWAP_BTC_SIGNING_STOP_REPORT.md` — original
  decision not to implement BTC signing from scratch.
- `docs/design/ATOMIC_SWAP_LIBWALLY_INTEGRATION_REVIEW.md` — Phase A
  libwally integration plan that Phase C will follow.
