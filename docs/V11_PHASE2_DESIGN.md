# V11 Phase 2 — Design Decisions

**Status**: DRAFT 1 · author: SOST consensus working group
**Branch**: `v11-phase2`
**Date**: 2026-05-02
**Scope**: SbPoW (component C) + PoP lottery with jackpot rollover (component D)

This document is **docs-only**. It captures the CTO-approved design decisions for Phase 2 after the C1 + D1 reconnaissance of the existing codebase. **No code, no constants, no CMake wiring, no test activation lands with this commit.** Subsequent commits implement the design point-by-point under the order listed in §7.

Phase 2 has **no calendar pressure**. `V11_PHASE2_HEIGHT` stays at the sentinel value `INT64_MAX` until every gate in §6 is green and the owner issues an explicit GO.

---

## 1 · Header v2 — version-field gate

### 1.1 Decision

The block header gains a v2 form at heights `>= V11_PHASE2_HEIGHT`. The `version` field (already present in `BlockHeader` at `include/sost/block.h:43-50`, currently always `BLOCK_HEADER_VERSION = 1`) is the wire signal:

```
height <  V11_PHASE2_HEIGHT  →  header.version == 1, 96 B header. v2 rejected.
height >= V11_PHASE2_HEIGHT  →  header.version == 2, 96 + 97 = 193 B header. v1 rejected.
```

Old nodes that receive a v2 header reject it cleanly via `version mismatch` in L2 validation (`block_validation.cpp` `ValidateBlockHeaderContext`) **without crashing on a short buffer**. The transition is sharp: the activation height itself is the first block where `version == 2` is mandatory.

### 1.2 v2 fields

```
+--------------------+-------+------------------------------------------+
| field              | size  | meaning                                  |
+--------------------+-------+------------------------------------------+
| miner_pubkey       | 33 B  | secp256k1 compressed pubkey              |
| miner_signature    | 64 B  | BIP-340 Schnorr over sig_message         |
+--------------------+-------+------------------------------------------+
```

Total v2 header: 193 B.

### 1.3 PoW seed binding

The ConvergenceX seed at `height >= V11_PHASE2_HEIGHT` mixes the miner pubkey:

```
Pre-Phase2 (V10/V11 Phase 1):
    seed = sha256(MAGIC || "SEED" || header_core_v1 || block_key
                   || nonce || extra_nonce)

Phase 2:
    seed = sha256(MAGIC || "SEED2" || header_core_v2 || block_key
                   || nonce || extra_nonce || miner_pubkey)
```

The pubkey is **part of the PoW input**, so switching pubkey re-runs the entire ConvergenceX inner loop. A pool that hands work to a key it does not control cannot delegate the proof.

### 1.4 Signature message — domain-separated

```
sig_message = sha256("SOST/POW-SIG/v11" ||
                     prev_hash ||
                     height ||
                     commit ||
                     nonce ||
                     extra_nonce ||
                     miner_pubkey)

miner_signature = schnorr_sign(miner_privkey, sig_message)
```

`commit` is the ConvergenceX output. The signature **signs the PoW commitment, not a hash that already includes the signature** — there is no circular dependency. Inputs `prev_hash`, `height`, `nonce`, `extra_nonce`, `miner_pubkey` are all bound so a signature is non-replayable across blocks, heights or pubkeys.

### 1.5 Block ID serialization (CRITICAL)

The block ID `block_hash = sha256(sha256(serialized_header))` must be **explicitly defined per version**:

- v1: serialize the 7 legacy fields (96 B), hash twice. **Unchanged from V10/V11 Phase 1.**
- v2: serialize the 7 legacy fields (96 B) **followed by** `miner_pubkey || miner_signature` (97 B), hash twice over the full 193 B.

The fork is sharp at `V11_PHASE2_HEIGHT`: at that height the v2 serialization is the canonical one and any v1 block is rejected.

### 1.6 Validation rules (post-Phase2)

A block at `height >= V11_PHASE2_HEIGHT` is valid only if **all** of:

1. `header.version == 2`.
2. `miner_pubkey` is a well-formed compressed secp256k1 point (33 B, 0x02/0x03 prefix, on curve).
3. `miner_signature` is a valid BIP-340 Schnorr signature for `sig_message` under `miner_pubkey`.
4. The seed used to derive `commit` was the v2 seed including `miner_pubkey`.
5. The coinbase `OUT_COINBASE_MINER` output (50% of subsidy + fees) pays `address_from_pubkey(miner_pubkey)`.

Failure of any of (1)-(5) → block rejected.

---

## 2 · Miner key loading — wallet.json reuse + dual flag

### 2.1 Decision

No new keystore format. The miner reads from the existing wallet (`include/sost/wallet.h:14-22`, `Wallet::load_from_json` at `wallet.cpp:810-836`).

New CLI flags on `sost-miner`:

```
--wallet <path>             # path to wallet.json (mandatory from Phase 2)
--mining-key-label <label>  # which WalletKey within that wallet to use
--address <sost1...>        # optional; if set, MUST match key-derived address
```

### 2.2 Behaviour by phase

| Setting | Pre-Phase 2 (height < V11_PHASE2_HEIGHT) | Phase 2 (height >= V11_PHASE2_HEIGHT) |
|---|---|---|
| `--address` only | OK (legacy path, no signing) | **Reject at startup** — Phase 2 requires a signing key |
| `--wallet` + `--mining-key-label` | OK (signing pre-armed; signature ignored by validator) | OK (mandatory) |
| All three set, address mismatch | Abort startup with explicit error | Abort startup with explicit error |
| `--wallet` set, label not found | Abort startup | Abort startup |

The miner's coinbase miner-subsidy output address is **derived from the selected `WalletKey`**, never from a free string, on Phase 2 blocks. `--address` becomes a sanity check.

### 2.3 Memory hygiene

- The 32-byte private key lives in `WalletKey::privkey` (existing `std::array<uint8_t, 32>`). The miner copies it into its signing context at startup; the original `WalletKey` stays in the loaded wallet object.
- On exit, the miner explicitly zeroes its in-memory copy via a `secure_memzero` helper (added in Commit 3 if `sodium_memzero` is unavailable). The wallet object's own zeroing remains TODO (separate hardening task, out of Phase 2 scope).
- The privkey is **never logged**. All log lines that touch keying material print only the address or the pubkey hex, never the privkey.

---

## 3 · Schnorr — separate context + build-time gate

### 3.1 Decision

A new lazy-init secp256k1 context lives in `src/sbpow.cpp` solely for Schnorr operations:

```cpp
secp256k1_context* GetSecp256k1SchnorrCtx();  // new, sbpow-internal
```

The existing `GetSecp256k1Ctx()` (`src/tx_signer.cpp:40-55`, `SIGN | VERIFY` flags) is **untouched**. Transactions keep going through it; SbPoW does not touch the tx-signing path. Blast radius minimised.

### 3.2 Build-time gate (Commit 4)

`src/sbpow.cpp` includes a CMake feature check:

```cmake
include(CheckIncludeFile)
check_include_file("secp256k1_schnorrsig.h" SOST_HAVE_SCHNORRSIG)
if(NOT SOST_HAVE_SCHNORRSIG)
    message(FATAL_ERROR
        "V11 Phase 2 requires libsecp256k1 with the schnorrsig module. "
        "Rebuild libsecp256k1 with --enable-module-schnorrsig "
        "or upgrade the system package.")
endif()
target_compile_definitions(sost-core PRIVATE SOST_HAVE_SCHNORRSIG=1)
```

The check fires **at configure time**, not at link time, so the build error is the first thing the developer sees if their `libsecp256k1` lacks Schnorr support. Better than a `nm`-grep failure during link or a runtime abort on the first signed block.

### 3.3 Cross-platform determinism

Schnorr signatures from libsecp256k1 are deterministic by default (RFC 6979-style nonce derivation in BIP-340), so the same `(privkey, sig_message)` produces the same signature bit-for-bit on x86 and ARM. Verification is hash-based and bit-exact. No randomness is introduced.

---

## 4 · Lottery rollover state — 5 fields in StoredBlock + 1 in BlockUndo

### 4.1 Decision

No standalone global `RolloverState`. The canonical state lives **per block** in `StoredBlock` (declared near `src/sost-node.cpp:141`), alongside the existing `miner_reward / gold_vault_reward / popc_pool_reward`. The current pending value is always `g_blocks.back().pending_lottery_after`.

New fields in `StoredBlock` (6 total — the existing three plus 3 new states + 1 new amount):

```cpp
struct StoredBlock {
    /* ... existing fields ... */
    int64_t   miner_reward;
    int64_t   gold_vault_reward;
    int64_t   popc_pool_reward;

    // V11 Phase 2 — lottery state. Zero at heights < V11_PHASE2_HEIGHT.
    uint64_t       pending_lottery_before;   // pending value at start of block
    uint64_t       pending_lottery_after;    // pending value at end of block
    bool           lottery_triggered;        // is_lottery_block(h)
    PubKeyHash     lottery_winner_pkh;       // {0} if no winner this block
    uint64_t       lottery_payout;           // 0 if no winner this block
};
```

The skeleton's `lottery::RolloverState` and `TransitionInputs/Outputs` (`include/sost/lottery.h:77-101`) become **pure-function helpers** that operate on these fields — no global state, no hidden cache. `apply_block` reads `pending_lottery_before` from the previous tip, computes the per-block transition, returns the 5 new values which the caller writes into the new `StoredBlock` instance.

### 4.2 Reorg — `BlockUndo` extension

`BlockUndo` (declared at `include/sost/utxo_set.h:36`) gains exactly **one** new field:

```cpp
struct BlockUndo {
    /* ... existing spent_utxos ... */
    uint64_t pending_lottery_before;   // pre-block pending, restored on disconnect
};
```

`pending_lottery_after`, `lottery_triggered`, `lottery_winner_pkh`, `lottery_payout` are all derivable from the disconnected block's contents (or are zero by default), so they don't need separate undo entries — the entire `StoredBlock` is removed from `g_blocks` on disconnect anyway. Only `pending_lottery_before` is needed because it's the **input** to the disconnected block, not its output.

### 4.3 Invariant — UPDATE / PAYOUT / IDLE (PUBLIC INVARIANT, DO NOT BREAK)

This invariant is mirrored in three other places: V11_SPEC.md §10.6 (on the v82 branch), `include/sost/lottery.h` top-of-file comment (on the v82 branch), and the public banner v82. Phase 2 implementation **must respect it exactly**.

```
UPDATE   on is_lottery_block(h) == true && eligibility_set(h).empty():
           pending_lottery_after  = pending_lottery_before + lottery_share(h)
           lottery_triggered      = true
           lottery_winner_pkh     = {0}
           lottery_payout         = 0
           Coinbase: 3 outputs. Miner 50%; vault and popc outputs 0.

PAYOUT   on is_lottery_block(h) == true && !eligibility_set(h).empty():
           pending_lottery_after  = 0
           lottery_triggered      = true
           lottery_winner_pkh     = pick_winner(...)
           lottery_payout         = lottery_share(h) + pending_lottery_before
           Coinbase: 4 outputs. Miner 50%; lottery winner gets payout;
                     vault and popc outputs 0.

IDLE     on is_lottery_block(h) == false:
           pending_lottery_after  = pending_lottery_before
           lottery_triggered      = false
           lottery_winner_pkh     = {0}
           lottery_payout         = 0
           Coinbase: 3 outputs, normal 50/25/25 split.
           pending_lottery_amount is NEITHER read nor written for shape.
```

**Implication: a non-triggered block NEVER pays out the jackpot, even if `pending_lottery_before > 0`.** The jackpot is preserved across non-triggered blocks unchanged and waits for the next triggered block.

This invariant is publicly documented in banner v82 (already deployed) and in `include/sost/lottery.h`. Any Phase 2 code change that violates it changes consensus rules and fails review.

### 4.4 Coinbase shape transition

`coinbase_split()` (`src/emission.cpp:6`) becomes height + triggered + eligibility-aware:

```cpp
struct CoinbaseSplit {
    int64_t miner;
    int64_t gold_vault;
    int64_t popc_pool;
    int64_t lottery_winner;     // new — 0 except in PAYOUT
    int64_t total_reward;
};

CoinbaseSplit coinbase_split(int64_t reward,
                             int64_t height,
                             bool triggered,
                             bool eligibility_empty,
                             uint64_t pending_lottery_before);
```

`ValidateCoinbaseConsensus()` (`src/tx_validation.cpp:507`) gains the same parameters and matches the shape exactly:

| State | outputs | miner | vault | popc | lottery |
|---|---|---|---|---|---|
| Pre-Phase 2 | 3 | reward−2q | q | q | — |
| Phase 2 IDLE | 3 | reward−2q | q | q | — |
| Phase 2 UPDATE | 3 | reward/2 | 0 | 0 | — (and `pending += reward/2`) |
| Phase 2 PAYOUT | 4 | reward/2 | 0 | 0 | reward/2 + `pending_before` |

where `q = reward / 4`.

---

## 5 · Eligibility scan — lazy + cache, benchmark-gated

### 5.1 Decision

The first implementation is **deterministic lazy scan** over `g_blocks` with memoization keyed by `(tip_height, tip_block_hash)`. No incremental index. No new persistent data structure on disk.

```cpp
// Pseudo-API; final names land in Commit 6.
const std::vector<PubKeyHash>& eligibility_set_at(int64_t h);
void invalidate_eligibility_cache();   // called on connect/disconnect/reorg
```

Cache invalidation rule: every `connect_block`, `disconnect_block`, or `try_reorganize` clears the cache entirely. Simpler than tracking per-height invalidation; the cache hit rate matters only within a single validation/RPC round.

### 5.2 Determinism

`PubKeyHash` (20-byte `std::array<uint8_t, 20>`) sorted **lexicographically** by raw byte order. This matches the natural `operator<` of `std::array<uint8_t, 20>` and is byte-identical on x86 and ARM. No locale-dependent comparator, no string conversions.

The 30-block reward exclusion window is computed by walking `g_blocks[h-30 .. h-1]` and collecting their miner pubkey hashes — straight scan, no extra index.

### 5.3 Benchmark gate (G4.5 — new)

A new gate is added to the activation checklist:

```
G4.5: bench/test — eligibility_set_at(h) must complete in < 50 ms on a
      chain of 10,000 blocks with 9 distinct miners, measured on a
      single-thread x86_64 4 GHz reference machine.
```

If the benchmark fails, **Commit 6.5** introduces an incremental index `miner_first_seen: PubKeyHash → int64_t` updated on connect/disconnect with the same cache invalidation rules. This branch is conditional and not part of the initial commit budget.

---

## 6 · `V11_PHASE2_HEIGHT` — activation criteria

### 6.1 Initial value

```cpp
inline constexpr int64_t V11_PHASE2_HEIGHT = INT64_MAX;
```

This is the sentinel value. While set, none of the Phase 2 code paths execute on real chain heights. The constant lives in `params.h` and is only changed in **Commit 10** ("V11_PHASE2_HEIGHT decision (final)").

### 6.2 GO criteria — ALL must be true

A concrete activation height is set ONLY when:

| # | Gate | Definition |
|---|---|---|
| a | C+D unit tests green | All Phase 2 unit tests pass: `test-sbpow-phase2`, `test-lottery-phase2`, plus regression on `test-casert-v11`, `test-convergencex-v11`, `test-transcript-v2`. |
| b | SbPoW adversarial suite | At least 10 adversarial test cases pass (malformed pubkey, tampered sig, replay across blocks, wrong pubkey, etc. — see Commit 4). |
| c | Lottery reorg suite | At least 3 reorg test cases pass: triggered-block disconnect restores `pending`; non-triggered-block disconnect is no-op; deep reorg crossing both states restores correctly. |
| d | Monte Carlo | `tools/lottery_simulation.py` shows dominant lottery share **< 15 %** in current network shape (1 dominant 70 %, 4 medium 4–9 %, 4 small). |
| e | RNG cross-platform | `pick_winner()` produces bit-identical output on x86 (mandatory) and ARM (best-effort if hardware available). |
| f | Owner GO | Explicit human authorisation. |

### 6.3 Lead time

The activation height **must be at least 5,000 blocks ahead** of the height at which the Phase 2 binary is published to `origin/main`. This gives miners time to upgrade. At the 600 s target, 5,000 blocks ≈ 35 days.

### 6.4 Activation commit

The exact height is set in a **separate** commit ("v11 Phase 2: activate at block N"), at the very end, after a/b/c/d/e/f are all green. That commit changes only `params.h`, `docs/V11_SPEC.md` §11.2, and the skeleton TODO comments.

---

## 7 · Commit plan after this design doc

Sequence on branch `v11-phase2`. Each commit is reviewed independently. **No merge to `main` until all 10 are green and §6 GO criteria are met.**

| # | Commit | Scope |
|---|---|---|
| 1 | docs: V11 Phase 2 design decisions | **THIS COMMIT** — design only |
| 2 | phase2 C: SbPoW header v2 + serialization + tests | `block.h/cpp`, `BlockHeader::Serialize/DeserializeFrom` height-gated; tests for v1/v2 roundtrip and malformed-v2 rejection |
| 3 | phase2 C: SbPoW miner integration + privkey loading | `--wallet`, `--mining-key-label` flags; signing in `sost-miner.cpp` between line 1107 (witnesses) and 1118 (submit); secure_memzero helper |
| 4 | phase2 C: SbPoW validator + adversarial tests + Schnorr build gate | `ValidateBlockSbPoW()` in `block_validation.cpp` L2; CMake Schnorr feature check; replace 10 TODOs in `test_sbpow_phase2.cpp` with real adversarial cases; wire in CMakeLists |
| 5 | phase2 D: lottery frequency function + constants | `params.h` constants (`V11_PHASE2_HEIGHT = INT64_MAX`, `LOTTERY_HIGH_FREQ_WINDOW = 5000`, `LOTTERY_REWARD_EXCLUSION_WINDOW = 30`, `LOTTERY_RNG_DOMAIN`); `is_triggered()` pure function |
| 6 | phase2 D: eligibility set lazy scan + cache | `eligibility_set_at()` in `lottery.cpp`; cache invalidation hooked into `connect_block`/`disconnect_block`/`try_reorganize`; benchmark `tools/eligibility_bench.cpp` |
| 6.5 | (conditional) phase2 D: incremental `miner_first_seen` index | Only if Commit 6 fails the 50 ms benchmark |
| 7 | phase2 D: pending_lottery_amount state + undo data | 5-field extension to `StoredBlock`; 1-field extension to `BlockUndo`; chain.json serialization with backward-compat read |
| 8 | phase2 D: coinbase shape change + ValidateCoinbaseConsensus + lottery tests | Modified `coinbase_split()` signature; `tx_validation.cpp:507` height-aware; replace 15 TODOs in `test_lottery_phase2.cpp`; wire in CMakeLists |
| 9 | phase2: Monte Carlo simulation + results doc | `tools/lottery_simulation.py`; `docs/V11_PHASE2_SIMULATION.md` |
| 10 | phase2: V11_PHASE2_HEIGHT activation (final) | Set the concrete height in `params.h` after gates a–f |

Branch hygiene: every commit must confirm `git branch --show-current == v11-phase2` before staging. **Do not commit to `main`.**

---

## 8 · Consensus invariants — checklist

Phase 2 code must preserve all of these. Any change that breaks one is a consensus break and gets reverted.

- [ ] Pre-Phase 2 blocks (`height < V11_PHASE2_HEIGHT`) follow V10 / V11 Phase 1 rules **bit-for-bit** — no path through `lottery_*`, no `version=2` accepted, no `pending_lottery_*` written.
- [ ] **Sharp activation**: the block at height `V11_PHASE2_HEIGHT` is the first block that requires `version=2`. There is no overlap window.
- [ ] **Lottery IDLE invariant**: a non-triggered block never pays out the jackpot. Coinbase is 3 outputs, normal `50/25/25` split. `pending_lottery_amount` is unread and unwritten.
- [ ] **Lottery UPDATE invariant**: an empty-eligibility triggered block accumulates the share, emits 3 outputs (vault and popc both 0), no winner.
- [ ] **Lottery PAYOUT invariant**: a non-empty-eligibility triggered block pays `share + pending_before` to one deterministically-selected winner; `pending` clears to 0.
- [ ] **Reorg correctness**: disconnecting any block restores `pending_lottery_before` from undo data. Disconnecting an IDLE block is a no-op for `pending`.
- [ ] **Block ID stability**: the v1 block ID at `height < V11_PHASE2_HEIGHT` is unchanged from V11 Phase 1. Only the v2 block ID at `height >= V11_PHASE2_HEIGHT` is new.
- [ ] **PoW seed binding**: at `height >= V11_PHASE2_HEIGHT`, the seed includes `miner_pubkey`. Any block whose `commit` was derived from a seed without the pubkey is rejected.
- [ ] **Signature binding**: the signature signs `prev_hash || height || commit || nonce || extra_nonce || miner_pubkey`. The signature is non-replayable across blocks, heights, or pubkeys.
- [ ] **Coinbase miner address binding**: the `OUT_COINBASE_MINER` output address must equal `address_from_pubkey(miner_pubkey)`.
- [ ] **Determinism**: every state transition is a pure function of (chain state at h-1, block at h). No randomness, no wall-clock, no platform-dependent operations.
- [ ] **Cross-platform**: x86 and ARM produce bit-identical block IDs, signatures, eligibility sets, winner picks, and `pending_lottery_*` transitions.

---

## 9 · Open risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| R1 | libsecp256k1 on some VPS images ships without `--enable-module-schnorrsig`. | Build-time `check_include_file` in Commit 4 fails configure with explicit instruction, not a runtime abort. Owner can rebuild libsecp256k1 with the flag before merging Phase 2. |
| R2 | Eligibility scan exceeds 50 ms on the production chain when it grows to 50k+ blocks (post-Phase 2 activation). | Commit 6.5 (incremental `miner_first_seen` index) is pre-budgeted. Activation gates include the benchmark. |
| R3 | A reorg crossing the Phase 2 activation boundary (very unlikely but theoretically possible if the activation block is reorged out). | Reorg test in Commit 7 explicitly covers `disconnect of block at height V11_PHASE2_HEIGHT`. The undo path resets `pending_lottery_before = 0` and reverts to v1 rules for any earlier height. |
| R4 | Wallet keystore exposure on miner machines. The miner now holds a real privkey at runtime. | Commit 3 documents the threat model. Mitigation: `secure_memzero` on exit; never log the key; recommend running the miner under a dedicated user with restrictive file permissions on `wallet.json`. Hardware wallet integration is out of Phase 2 scope but tracked separately. |
| R5 | Pool operators try to bypass SbPoW by sharing a single key across workers. | This is **explicitly** the cost of pooling under SbPoW: the operator either trusts every worker with the key (risk of theft) or accepts that no pooling is possible. SbPoW addresses the pool-without-key topology, not raw hashrate centralisation. Documented in V11_SPEC.md §3.6. |
| R6 | Coinbase shape change breaks legacy block-explorer parsers. | Phase 2 PAYOUT blocks have 4 outputs instead of 3. Banner v82 is the public notice. The explorer's own parser (`website/sost-explorer.html` block-detail render) must be updated in the same PR as Commit 8 to render the lottery winner output cleanly. |
| R7 | Monte Carlo result fails the < 15 % dominant-lottery-share gate. | Activation does not happen. The gate is the contract: if simulation shows dominant capturing the lottery, the design is broken. Re-evaluate eligibility/exclusion parameters before retrying. |
| R8 | Signing latency on low-end miner hardware (Raspberry Pi class). | Schnorr signing is < 1 ms on x86; ARM cores typically 2–4 ms. Bench in Commit 4 enforces < 5 ms ceiling. If a target platform exceeds 5 ms, that platform is documented as unsupported for Phase 2 mining (separate from validation, which is universal). |

---

## 10 · Source pointers (from C1 + D1 reconnaissance)

For the implementer, the existing code anchors:

**Header / serialization**
- `include/sost/block.h:43-50` — `BlockHeader` struct (current 7 fields)
- `include/sost/block.h:36` — `BLOCK_HEADER_VERSION = 1`
- `src/block.cpp:54-64` — `BlockHeader::SerializeTo()`
- `src/block.cpp:70-78` — `BlockHeader::Serialize()` (96 B fixed)
- `src/block.cpp:84-107` — `BlockHeader::DeserializeFrom()`
- `src/block.cpp:113-121` — `ComputeBlockHash()`

**Validation**
- `include/sost/block_validation.h:58` — `ValidateBlockStructure` (L1)
- `include/sost/block_validation.h:65` — `ValidateBlockHeaderContext` (L2, height in scope)
- `include/sost/block_validation.h:116` — `ValidateBlockTransactionsConsensus` (L3)
- `include/sost/block_validation.h:126` — `ConnectValidatedBlockAtomic` (L4)

**Crypto**
- `CMakeLists.txt:66` — secp256k1 already linked
- `src/tx_signer.cpp:23-54` — existing ECDSA context (do not modify)
- `include/sost/crypto.h:5` — `sha256()`
- `include/sost/serialize.h:38-68` — LE helpers

**Wallet**
- `include/sost/wallet.h:14-22` — `WalletKey` struct
- `src/wallet.cpp:810-836` — `Wallet::load_from_json`
- `include/sost/tx_signer.h:24-26` — `PubKey`, `PubKeyHash` aliases

**Miner**
- `src/sost-miner.cpp:83` — `g_miner_pkh` (current address-only path)
- `src/sost-miner.cpp:153` — `build_coinbase_tx()`
- `src/sost-miner.cpp:725-1347` — `mine_one_block()`
- `src/sost-miner.cpp:1107` — witnesses ready
- `src/sost-miner.cpp:1118` — `rpc_submit_block_full()` (signing inserts here)

**Chain state**
- `src/sost-node.cpp:141` — `g_blocks` (vector of `StoredBlock`)
- `src/sost-node.cpp:146` — `g_block_undos`
- `src/sost-node.cpp:4802` — `load_chain()`
- `src/sost-node.cpp:5266` — `save_chain_internal()`
- `src/sost-node.cpp:3883-4100` — `try_reorganize()`
- `src/sost-node.cpp:3715` — `g_utxo_set.ConnectBlock()` undo creation
- `include/sost/utxo_set.h:36` — `BlockUndo` struct (extend with `pending_lottery_before`)

**Coinbase / subsidy**
- `src/emission.cpp:6-8` — `coinbase_split()` (current 50/25/25)
- `src/sost-miner.cpp:153` — coinbase build (vault + popc decode 177, 183)
- `src/tx_validation.cpp:507` — `ValidateCoinbaseConsensus`
- `src/tx_validation.cpp:581-602` — split enforcement (replace with state-aware version)
- `include/sost/subsidy.h:8` — `sost_subsidy_stocks(height)`

**Lottery skeleton (already on `main` from Phase 2 skel commit `111d405`)**
- `include/sost/lottery.h` — pure-function API surface
- `src/lottery.cpp` — abort-on-call stubs
- `tests/test_lottery_phase2.cpp` — 15 TODO assertions
- `include/sost/sbpow.h`, `src/sbpow.cpp`, `tests/test_sbpow_phase2.cpp` — SbPoW counterparts

---

## 11 · Sign-off

This design freezes the rules. Subsequent commits implement them — no improvisation on consensus. If any implementation step finds an existing repo invariant that contradicts the design, the implementer **stops and reports**; the design is updated here before code lands.

— SOST consensus working group, 2026-05-02
