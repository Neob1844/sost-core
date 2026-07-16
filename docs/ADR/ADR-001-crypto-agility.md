# ADR-001 — Crypto agility via a 1-byte alg_id registry

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

- **Status:** Accepted-for-research (PROVISIONAL registry values)
- **Date:** 2026-07-02
- **Author:** NeoB

## Context

Spend authorisation on SOST mainnet today is a single, hardcoded scheme: ECDSA
over secp256k1, compact 64-byte signatures (`r||s` big-endian) with canonical
LOW-S enforcement (README.md:196; src/tx_signer.cpp:8,19; `IsLowS`
src/tx_signer.cpp:210; `EnforceLowS` src/tx_signer.cpp:223; `ValidateRSRange`
src/tx_signer.cpp:247/:277; `secp256k1_ecdsa_verify` src/tx_signer.cpp:374;
`VerifyTransactionInput` src/tx_signer.cpp:551). The witness carries no scheme
identifier — the algorithm is implied by the fixed serialization
(include/sost/transaction.h:72-73; src/transaction.cpp:210-217).

A one-scheme-implied-by-layout design means that introducing any new signature
algorithm (for example a post-quantum scheme such as ML-DSA, FIPS 204) requires
a new hard fork *each time*. Post-quantum cryptography is an evolving field:
ML-DSA is standardised, SLH-DSA (FIPS 205) exists as a hash-based backup, and
future parameter sets or schemes may become necessary. A protocol that can only
change signature schemes via ad-hoc hard forks is brittle.

This supersedes the registry proposed in V2 (docs/PQ_MIGRATION_V2.md, PR #37),
which used a different id assignment. See ADR-000-style note below on the
reassignment.

## Decision

Adopt a **versioned, alg_id-tagged witness**: a single 1-byte `alg_id`
carried inside a versioned witness envelope, so new signature schemes can be
registered and validated without a fresh hard fork for each scheme (the
activation of *any* PQ scheme remains a separate future consensus decision — see
ADR-005; the envelope itself is what removes the per-scheme fork tax).

The V3 registry (PROVISIONAL — supersedes V2):

| alg_id | Name | Meaning |
|--------|------|---------|
| `0x00` | `LEGACY_ECDSA_SECP256K1` | Today's 64/33 fixed layout (ECDSA secp256k1) |
| `0x01` | `PQ_ML_DSA_44` | ML-DSA-44, FIPS 204, NIST security level 2 |
| `0x02` | `HYBRID_ECDSA_ML_DSA_44` | ECDSA **AND** ML-DSA-44 must both verify (AND semantics — see ADR-002) |
| `0x03` | `ML_DSA_65_RESERVED` | Reserved (FIPS 204, NIST level 3) |
| `0x04` | `ML_DSA_87_RESERVED` | Reserved (FIPS 204, NIST level 5) |
| `0x10` | `SLH_DSA_RESERVED` | Reserved (FIPS 205, hash-based backup; parameter-set dependent) |
| `0xFF` | `INVALID` | Never valid |

**Any other value is deterministically REJECTED, never "ignored."** An unknown
alg_id is a hard validation failure, not a soft skip, so that consensus cannot
diverge on unassigned identifiers.

### Reassignment note (V2 → V3)

V3 **reassigns** ids relative to V2 (V2 used `0x02` = ML_DSA_65 and `0x10` =
HYBRID_44). This reassignment is safe today because the PQ path is entirely
inert: `PQ_ACTIVATION_HEIGHT = INT64_MAX` means no PQ witness is ever accepted on
mainnet, so no transaction can depend on either id assignment. The registry is
marked **PROVISIONAL** everywhere and must be frozen before any activation
proposal.

## Alternatives considered

1. **Hardcode a single PQ scheme** (e.g. ML-DSA-44 only). Rejected: repeats the
   current one-scheme-implied brittleness — a later move to ML-DSA-65/87 or to
   SLH-DSA as a hash-based fallback would again require a full hard fork, and
   offers no clean hybrid path.
2. **Introduce new output/script types per scheme** instead of an alg_id tag.
   Rejected: proliferates output types, complicates wallet/explorer handling,
   and still couples each new scheme to bespoke consensus logic rather than a
   uniform dispatch on a single tagged field.

## Pros

- New schemes register as table entries, not new forks — a single validation
  dispatch on `alg_id`.
- Uniform handling across wallet, RPC, explorer, and node.
- Explicit reserved ids document intent (ML-DSA-65/87, SLH-DSA) without
  committing to them.
- Deterministic rejection of unknown ids removes a class of consensus-split bugs.

## Risks

- A registry is a coordination point: the id↔scheme mapping must be frozen and
  reviewed before activation; a wrong or ambiguous mapping is a consensus bug.
- Marking values PROVISIONAL is only safe while the path is inert (INT64_MAX);
  discipline is required to freeze before any activation proposal.
- An alg_id field is metadata an attacker can set arbitrarily in a crafted tx —
  exact-size and scheme-specific validation per id is mandatory (see ADR-003).

## Consensus impact

**NONE now.** The registry is inert: `PQ_ACTIVATION_HEIGHT = INT64_MAX`
(the same "never active" sentinel used by `POPC_V15_ACTIVATION_HEIGHT` and
`atomic_swap_htlc_active_at`). No mainnet transaction is validated against any
non-`0x00` alg_id. Assigning or reassigning ids here changes no consensus rule.
Activation of any tagged scheme would be a separate future consensus proposal
(ADR-005) — not this PR.

## Notes

- Related: ADR-002 (hybrid = AND), ADR-003 (variable-length witness),
  ADR-005 (no mainnet activation).
- The legacy inert placeholder proposal (include/sost/proposals.h:44, id 8
  "post_quantum", status DEFINED, heights -1) still carries the historical label
  "SPHINCS+/Dilithium." V3 notes this should eventually be reworded to
  ML-DSA / SLH-DSA terminology; that rewording changes no behaviour.
- Prior iteration: docs/PQ_MIGRATION_V2.md (PR #37), which V3 supersedes.
