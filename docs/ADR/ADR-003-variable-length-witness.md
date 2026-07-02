# ADR-003 — Versioned variable-length witness (tx version 2)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

- **Status:** Provisional
- **Date:** 2026-07-02
- **Author:** NeoB

## Context

The current `TxInput` serialization is **fixed-length**: a 64-byte signature
(`std::array<Byte,64>`, include/sost/transaction.h:72) followed by a 33-byte
compressed public key (`std::array<Byte,33>`, 02/03 prefix,
include/sost/transaction.h:73), written and read as exactly 64 + 33 bytes with
**no length prefix** (`SerializeTo` src/transaction.cpp:210-217; `DeserializeFrom`
src/transaction.cpp:220-225). The per-input serialized size today is 133 bytes
(src/tx_validation.cpp:77). The transaction version field is
`uint32_t version{1}` (include/sost/transaction.h:109).

This fixed layout **physically cannot hold a post-quantum signature.** ML-DSA-44
signatures are 2420 bytes and public keys 1312 bytes (FIPS 204, NIST level 2);
ML-DSA-65 is 3309/1952; ML-DSA-87 is 4627/2592. A 64-byte-only field cannot
represent any of these. A hybrid input (ADR-002) must carry *both* an ECDSA
64/33 pair *and* an ML-DSA 2420/1312 pair. Therefore PQ requires a **new,
versioned, variable-length witness** — this is the structural reason ADR-001's
alg_id registry is necessary but not sufficient on its own.

## Decision

Define **tx version 2** (PROVISIONAL, not active) as a versioned witness
envelope with:

1. **A 1-byte `alg_id`** per input, from the ADR-001 registry, selecting the
   scheme.
2. **Explicit length prefixes** for each variable-length field (signature blob,
   public key blob; two of each in hybrid mode), so a parser never relies on an
   implied fixed width. Each length is encoded as **`len_be16` — an unsigned
   16-bit integer, big-endian (network byte order), occupying exactly 2 bytes**.
   There is deliberately **no `CompactSize`, varint, short form or alternative
   prefix**: a fixed width has exactly one representation of each value and needs
   no shortest-form canonicalisation rule (all proposed component sizes are below
   65536 bytes; largest is ML-DSA-87's 4627-byte signature). See ADR decision D8
   in `docs/PQ_DECISION_LOG_V3.md` and the normative spec
   `docs/PQ_TX_FORMAT_V3.md §5`. A component exceeding 65535 bytes would require a
   **new witness version**, never a re-interpretation of the V3 length field.
3. **Exact-size enforcement per alg_id.** The length prefixes are parse-level
   framing only; consensus validation additionally requires each field to be
   *exactly* the size mandated by the alg_id's scheme. Reference sizes (FIPS
   204 / current ECDSA):

   | alg_id | signature bytes | public key bytes |
   |--------|-----------------|------------------|
   | `0x00` LEGACY_ECDSA | 64 | 33 |
   | `0x01` ML_DSA_44 | 2420 | 1312 |
   | `0x02` HYBRID_ECDSA_ML_DSA_44 | 64 (ECDSA) + 2420 (ML-DSA) | 33 + 1312 |
   | `0x03` ML_DSA_65 (reserved) | 3309 | 1952 |
   | `0x04` ML_DSA_87 (reserved) | 4627 | 2592 |
   | `0x10` SLH_DSA (reserved) | parameter-set dependent | parameter-set dependent |

   A field whose declared length does not match the exact size for its alg_id is
   **rejected** — no padding, no truncation, no "accept if at least N."

**tx version 1 (fixed 64/33) remains the only mainnet-valid form.** Version 2 is
defined for prototype/testnet study only.

### Size-limit interaction (informational)

The variable-length witness must fit within existing consensus limits, which are
unchanged by this ADR:
- `MAX_TX_BYTES_CONSENSUS = 100000` (include/sost/consensus_constants.h:15)
- `MAX_BLOCK_BYTES_CONSENSUS = 1000000` (include/sost/consensus_constants.h:16)
- `MAX_TX_BYTES_STANDARD = 16000` (include/sost/tx_validation.h:26)
- `MAX_BLOCK_TXS_CONSENSUS = 65536` (include/sost/block_validation.h:37)
- `MAX_BLOCK_TX_COUNT = 4096` (include/sost/mempool.h:22)

A single ML-DSA-44 input (~2420 + 1312 = 3732 bytes of witness plus framing) is
far larger than today's 133-byte input; hybrid inputs are larger still. This is
noted as a research consideration (fewer PQ inputs fit per tx/block); this ADR
proposes **no change** to any limit.

## Alternatives considered

1. **Keep the fixed 64/33 layout.** Rejected — it cannot represent a 2420-byte
   ML-DSA signature at all. This is a hard structural blocker, not a preference.
2. **New output/script types per scheme** rather than a versioned witness.
   Rejected for the same reasons as ADR-001: type proliferation and per-scheme
   bespoke logic, versus one versioned envelope with uniform length-prefixed
   parsing and per-alg_id exact-size checks.

## Pros

- Can represent ECDSA, ML-DSA (all parameter sets), hybrid, and future schemes
  in one uniform framing.
- Explicit length prefixes remove reliance on implied widths — safer parsing.
- Exact-size enforcement per alg_id closes malleability/overflow gaps a naive
  "variable length" would open.
- Versioning (`version{1}` → 2) keeps legacy txs byte-for-byte unchanged.

## Risks

- Variable-length parsing is a classic source of deserialization bugs
  (length-prefix trust, integer overflow, resource exhaustion) — every field
  must be bounded before allocation and exact-size checked after.
- Larger witnesses reduce PQ tx/block density against unchanged size limits;
  any limit change would be its own consensus decision, explicitly out of scope.
- A version-2 parser must never be reachable on mainnet until a deliberate
  activation; accidental acceptance of version 2 would be a consensus fault.

## Consensus impact

**Would be a consensus change if ever activated — deferred, not in this PR.**
tx version 2 and the variable-length witness are PROVISIONAL and inert;
`PQ_ACTIVATION_HEIGHT = INT64_MAX`. Mainnet accepts only version-1 fixed 64/33
inputs. No size limit is changed. Activation is a separate future consensus
proposal (ADR-005).

## Notes

- Cited layout: include/sost/transaction.h:72-73, src/transaction.cpp:210-217
  and :220-225, src/tx_validation.cpp:77, include/sost/transaction.h:109.
- Related: ADR-001 (alg_id registry), ADR-002 (hybrid carries both pairs),
  ADR-004 (PQ library behind an interface), ADR-005 (no activation).
- Prior iteration: docs/PQ_MIGRATION_V2.md (PR #37), superseded by V3.
