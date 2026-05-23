# Atomic Swap HTLC — Implementation Map (Phase 0 Audit)

**Audit scope:** existing SOST consensus, mempool, validation, wallet,
RPC, CLI, and test surfaces. Identifies the precise files that a future
Phase 3 atomic-swap implementation would have to touch, plus the
existing reference patterns (BOND_LOCK / ESCROW_LOCK / capsules / Gold
Vault Slice 1) that the HTLC implementation should mirror.

**Audit verdict:** the SOST codebase is **well-positioned** to host an
HTLC primitive. The transaction model is a clean UTXO design with
typed outputs and per-output payloads; two reserved-but-currently-
inactive output types (0x10 BOND_LOCK, 0x11 ESCROW_LOCK) already prove
the "reserve a type byte, gate its activation by height" pattern. Two
existing INT64_MAX-sentinel activation gates (Beacon II-B,
Gold Vault Slice 1) prove the "scaffolding without behaviour change"
pattern. HTLC can land **identically** under these patterns.

---

## 1. Transaction model

**File:** `include/sost/transaction.h`

```
TxInput  { prev_txid[32], prev_index u32, signature[64], pubkey[33] }
TxOutput { amount i64, type u8, pubkey_hash[20], payload<=512 }
Transaction { version u32, tx_type u8, inputs[], outputs[] }
txid = double-SHA256(serialize(tx))
```

**Existing output types (currently active):**

| Constant | Value | Meaning |
|---|---|---|
| `OUT_TRANSFER`         | 0x00 | normal transfer |
| `OUT_COINBASE_MINER`   | 0x01 | coinbase miner share |
| `OUT_COINBASE_GOLD`    | 0x02 | coinbase gold-vault share |
| `OUT_COINBASE_POPC`    | 0x03 | coinbase PoPC-pool share |
| `OUT_COINBASE_LOTTERY` | 0x04 | V11-Phase-2 lottery payout |

**Existing output types (RESERVED, currently inactive):**

| Constant | Value | Meaning |
|---|---|---|
| `OUT_BOND_LOCK`   | 0x10 | bond lock until height |
| `OUT_ESCROW_LOCK` | 0x11 | escrow lock until height + beneficiary |
| `OUT_BURN`        | 0x20 | reserved, NOT activated, never planned |

**Free slots for HTLC** (proposed allocations for Phase 3):

| Constant (PROPOSED) | Value | Meaning |
|---|---|---|
| `OUT_HTLC_LOCK`   | 0x12 | hashlock + refund_height + claim_pkh + refund_pkh |
| `OUT_HTLC_CLAIM`  | 0x13 | spend path: preimage + claim_pkh signature |
| `OUT_HTLC_REFUND` | 0x14 | spend path: refund_pkh signature after timeout |

Note: it is also possible to encode CLAIM and REFUND not as new output
types but as new transaction-level operations (in `tx_type`) that spend
the LOCK output. Phase 1 plan discusses both shapes.

---

## 2. Activation-gate precedents

**Files containing INT64_MAX-sentinel activation constants:**

- `include/sost/params.h:857` — `BEACON_IIB_THRESHOLD_ACTIVATION_HEIGHT = INT64_MAX`
- `include/sost/gold_vault_slice1.h:76` — `GV_SLICE1_ACTIVATION_HEIGHT = INT64_MAX`

**Pattern (verbatim):**
1. Constant declared in a header.
2. Helper function `<feature>_active_at(int64_t height) -> bool` returns
   `false` while the constant is INT64_MAX.
3. ALL call sites in src/ go through the helper (never reference the
   constant directly).
4. Activation = replace INT64_MAX with a finite height in a single
   one-line commit; rollback = the reverse.

This scaffolding commit places `ATOMIC_SWAP_HTLC_ACTIVATION_HEIGHT` in
`include/sost/atomic_swap.h` following this pattern. **In contrast to
Beacon-II-B and GV-Slice-1, the HTLC helper currently has ZERO call
sites in src/** — because the Phase 3 implementation (output types,
validation, serialization, wallet) has not yet been written. This is
intentional: the scaffolding adds no behaviour to validate.

---

## 3. Validation pipeline

**File:** `src/tx_validation.cpp`, `include/sost/tx_validation.h`

The validation entry is:

```
TxValidationResult ValidateTransactionConsensus(
    const Transaction& tx,
    const IUtxoView& utxos,
    const TxContext& ctx);
```

Phase 3 work points (NOT touched by this scaffolding commit):

| File | Line(s) | What Phase 3 would add |
|---|---|---|
| `src/tx_validation.cpp` | ~152, ~171, ~202, ~281, ~395 | New rule branches for `OUT_HTLC_LOCK / CLAIM / REFUND` parallel to the existing `OUT_BOND_LOCK / OUT_ESCROW_LOCK` rules, gated by `atomic_swap_htlc_active_at(height)`. |
| `src/tx_validation.cpp` | rule R11 (~395) | Add HTLC types to the active-types whitelist gated by activation height. |
| `include/sost/tx_validation.h` | constants block | Add `HTLC_LOCK_PAYLOAD_LEN`, `HTLC_CLAIM_PAYLOAD_LEN`, `HTLC_REFUND_PAYLOAD_LEN` constants. |
| `include/sost/transaction.h` | enum block | Add 3 new `OUT_HTLC_*` constants. |
| `include/sost/transaction.h` | helpers block | Add `ReadHashlock`, `ReadRefundHeight`, `ReadClaimPkh`, `ReadRefundPkh`, etc. parallel to the existing `ReadLockUntil` / `ReadBeneficiaryPkh`. |

---

## 4. Mempool acceptance

**File:** `src/mempool.cpp`, `include/sost/mempool.h`

Entry: `MempoolAcceptResult Mempool::AcceptToMempool(const Transaction&)`.

Phase 3 would add:
- Acceptance rules for HTLC_LOCK transactions (require `value >= DUST_THRESHOLD`,
  refund_height in the future, well-formed payload).
- Acceptance rules for HTLC_CLAIM transactions (require valid preimage in
  witness, signature against claim_pubkey, refund_height not yet reached).
- Acceptance rules for HTLC_REFUND transactions (require refund_height
  reached, signature against refund_pubkey).
- Replay protection: same outpoint cannot be claimed twice.

---

## 5. Block validation

**File:** `src/block_validation.cpp`, `include/sost/block_validation.h`

Three-layer pipeline:
- **L1** `ValidateBlockStructure` — purely structural.
- **L2** `ValidateBlockHeaderContext` — header consensus.
- **L3** `ValidateBlockTransactionsConsensus` — applies
  `ValidateTransactionConsensus` to every tx in the block.

Phase 3 inherits HTLC validation through L3 automatically once
`ValidateTransactionConsensus` knows about HTLC. No L1/L2 changes
required.

---

## 6. Wallet, RPC, CLI

**Files:**
- `src/wallet.cpp`, `include/sost/wallet.h`
- `src/sost-rpc.cpp`
- `src/sost-cli.cpp` (capsule-mode plumbing already exists at line 686)
- `src/tx_send.cpp`, `src/tx_signer.cpp`

Phase 3 would add:
- Wallet helpers to construct HTLC_LOCK, HTLC_CLAIM, HTLC_REFUND transactions.
- RPC endpoints: `createhtlclock`, `claimhtlc`, `refundhtlc`, `decodehtlc`,
  `gethtlcstatus`.
- CLI flags: `--htlc-hashlock`, `--htlc-refund-height`, `--htlc-claim-pkh`,
  `--htlc-refund-pkh`, `--htlc-preimage` (for claim).
- Mempool / chain watch loop in the wallet to surface the swap's state
  (pending / claimable / claimed / refundable / refunded / expired).

**ZERO of these touched by this scaffolding commit.**

---

## 7. Test infrastructure

**Directory:** `tests/`

Existing pattern: `tests/test_<feature>.cpp` + CMake target. Example:
`tests/test_v13_lottery_cooldown_fork.cpp`, `tests/test_sbpow_adversarial.cpp`.

Phase 3 would add (minimum 20 tests):
- `tests/test_atomic_swap_htlc_lock_valid.cpp`
- `tests/test_atomic_swap_htlc_claim_before_timeout.cpp`
- `tests/test_atomic_swap_htlc_refund_after_timeout.cpp`
- `tests/test_atomic_swap_htlc_wrong_preimage_rejected.cpp`
- `tests/test_atomic_swap_htlc_claim_after_timeout_rejected.cpp`
- `tests/test_atomic_swap_htlc_refund_before_timeout_rejected.cpp`
- `tests/test_atomic_swap_htlc_double_claim_rejected.cpp`
- `tests/test_atomic_swap_htlc_refund_after_claim_rejected.cpp`
- `tests/test_atomic_swap_htlc_claim_after_refund_rejected.cpp`
- `tests/test_atomic_swap_htlc_malformed_rejected.cpp`
- `tests/test_atomic_swap_htlc_wrong_hash_algo_rejected.cpp`
- `tests/test_atomic_swap_htlc_wrong_recipient_rejected.cpp`
- `tests/test_atomic_swap_htlc_wrong_amount_rejected.cpp`
- `tests/test_atomic_swap_htlc_wrong_swap_id_rejected.cpp`
- `tests/test_atomic_swap_htlc_replay_across_heights_rejected.cpp`
- `tests/test_atomic_swap_htlc_pre_activation_rejected.cpp`
- `tests/test_atomic_swap_htlc_post_activation_accepted_only_if_valid.cpp`
- `tests/test_atomic_swap_htlc_serialization_roundtrip.cpp`
- `tests/test_atomic_swap_htlc_mempool_rejects_invalid.cpp`
- `tests/test_atomic_swap_htlc_block_validator_rejects_invalid.cpp`
- `tests/test_atomic_swap_htlc_reorg_behaviour.cpp`

**ZERO test files added by this scaffolding commit.**

---

## 8. Counterparty-chain interaction (off-chain to SOST consensus)

The SOST side of an atomic swap is entirely on-chain SOST validation.
**SOST consensus is not allowed to depend on the state of any other
chain.** All counterparty-chain coordination (BTC, ETH, USDT, USDC,
BNB, PAXG, XAUT) is the wallet-side responsibility:

- The SOST wallet constructs and signs the SOST-side HTLC.
- The user (or a wallet plugin) constructs and signs the counterparty
  HTLC on the other chain.
- The shared `hashlock` and the timeout discipline (T1 > T2) are
  enforced socially by the wallet UI — neither chain knows the other
  exists at the consensus level.

This isolation is **load-bearing**: under no circumstances may SOST
consensus pull state from the BTC or Ethereum networks. Doing so would
introduce an external oracle dependency that would break the
deterministic-replay guarantees of the SOST chain.

Detailed asset-specific design lives in
`docs/design/ATOMIC_SWAP_ASSETS_BTC_ETH_USDT_USDC_BNB_PAXG_XAUT.md`.

---

## 9. Summary — what this scaffolding commit changes

| File | Status | Change |
|---|---|---|
| `include/sost/atomic_swap.h` | **NEW** | One activation constant (INT64_MAX) + one inline helper. No call sites. |
| `docs/design/ATOMIC_SWAP_IMPLEMENTATION_MAP.md` | **NEW** | This file. |
| `docs/design/ATOMIC_SWAP_HTLC_IMPLEMENTATION_PLAN.md` | **NEW** | Phase 1 design plan. |
| `docs/design/ATOMIC_SWAP_ASSETS_BTC_ETH_USDT_USDC_BNB_PAXG_XAUT.md` | **NEW** | Phase 2 asset design. |
| `website/api/explorer_version.json` | modified | Cache-buster + release note. |
| `src/*.cpp`, `include/sost/transaction.h`, all other src/include files | **UNTOUCHED** | Zero behaviour change. |

The activation constant equals `INT64_MAX`. The helper is never called
from any .cpp file in this commit. By construction, every existing
block-validation, transaction-validation, mempool, wallet, and RPC
path is bit-identical to the pre-commit state.
