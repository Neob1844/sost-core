# 03 — Transactions and Signatures (canonical)

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

**This document is the canonical description of the current SOST transaction signature scheme.** All
other surfaces (README, website, marketing) are downstream copies that must agree with it.

## The current spend scheme: ECDSA secp256k1, compact LOW-S

- **Curve/algorithm:** ECDSA over secp256k1 (via libsecp256k1).
- **Signature encoding:** compact **64 bytes**, `r || s` big-endian.
- **Canonicality:** enforced **LOW-S** — the high-S sibling is rejected (non-malleable).
- **Public key:** compressed **33 bytes**, prefix `0x02`/`0x03`.

Source of truth in code:

- Header comment: `src/tx_signer.cpp:8,19`.
- LOW-S: `IsLowS` `src/tx_signer.cpp:210`; `EnforceLowS` `:223`; `ValidateRSRange`
  (LOW-S violation = **E5**) `:247` / `:277`.
- Verify: `secp256k1_ecdsa_verify` `src/tx_signer.cpp:374`; `VerifyTransactionInput` `:551`.
- Public statement: `README.md:196` ("Signature | ECDSA secp256k1 (libsecp256k1) with LOW-S").

## The fixed TxInput layout

```
struct TxInput {
    Hash256  prev_txid;                 // 32 bytes raw
    uint32_t prev_index;                // u32 LE
    std::array<Byte, 64> signature;     // compact ECDSA (r||s) — FIXED 64
    std::array<Byte, 33> pubkey;        // compressed pubkey       — FIXED 33
};
```

- `signature` is a fixed `std::array<Byte,64>` — `include/sost/transaction.h:72`.
- `pubkey` is a fixed `std::array<Byte,33>` (compressed 02/03) — `include/sost/transaction.h:73`.
- Serialised as **fixed 64 + 33 bytes with NO length prefix**:
  `SerializeTo` at `src/transaction.cpp:210-217`, `DeserializeFrom` at `src/transaction.cpp:220-225`.
- Per-input serialized size today is therefore **133 bytes**:
  `prev_txid(32) + prev_index(4) + signature(64) + pubkey(33)` (`src/tx_validation.cpp:77`).

The transaction version field is `uint32_t version{1}` (`include/sost/transaction.h:109`).

## Why the fixed layout blocks post-quantum signatures

The 64/33 byte input fields are **fixed-width arrays with no length prefix**. A post-quantum
signature cannot fit: ML-DSA-44 alone is a **2420-byte** signature and a **1312-byte** public key
(FIPS 204). There is simply nowhere to put those bytes in the current encoding, and widening the
fixed arrays would be a hard, non-agile break that could never carry more than one algorithm.

## Motivation for a versioned, variable-length witness (PROVISIONAL)

To carry a post-quantum signature *without* breaking legacy inputs, V3 research proposes a
**versioned witness envelope** — provisionally **transaction version 2** — that is
**variable-length** and carries a 1-byte `alg_id` selecting the signature algorithm:

- `0x00` LEGACY_ECDSA_SECP256K1 (today's 64/33 fixed layout)
- `0x01` PQ_ML_DSA_44 (FIPS 204, NIST L2)
- `0x02` HYBRID_ECDSA_ML_DSA_44 (**both** ECDSA **and** ML-DSA-44 must verify — AND semantics)
- `0x03` ML_DSA_65_RESERVED, `0x04` ML_DSA_87_RESERVED, `0x10` SLH_DSA_RESERVED, `0xFF` INVALID
- Any other `alg_id` value is **deterministically rejected**, never ignored.

All of the above is **PROVISIONAL and not active**. This registry reassigns ids relative to V2 (V2
used `0x02`=ML_DSA_65 and `0x10`=HYBRID_44); V3 supersedes V2. There is no protocol conflict because
`PQ_ACTIVATION_HEIGHT = INT64_MAX` (the versioned path is never reached on mainnet). The `version{1}`
mainnet transactions are entirely unaffected.

## Cross-references

- Registry and phase model: `06-post-quantum-roadmap.md`, `docs/PQ_MIGRATION_V3.md`.
- Size/limits impact: `09-performance-and-limits.md`, `docs/PQ_PERFORMANCE_MODEL_V3.md`.
- Definitions: `11-glossary.md`.
