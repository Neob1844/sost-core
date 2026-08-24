# ADR-002 — Hybrid means ECDSA AND ML-DSA (conjunctive), not OR

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

- **Status:** Accepted-for-research
- **Date:** 2026-07-02
- **Author:** NeoB

## Context

A hybrid signature combines a classical scheme (ECDSA secp256k1, mainnet-active
today) with a post-quantum scheme (ML-DSA-44, FIPS 204, NIST level 2) so that
the transition period is protected against both a classical break and a future
quantum break. The crypto-agility registry (ADR-001) reserves `0x02` for a
hybrid mode. The design question is the *combining rule*: must **both**
signatures verify (AND / conjunctive), or is **either** sufficient (OR /
disjunctive)?

The quantum threat model for signatures matters here (see also the note below):
an adversary can collect public keys revealed on-chain today and, once a
cryptographically-relevant quantum computer exists, use Shor's algorithm to
recover the ECDSA private key from the public key and forge ECDSA signatures.
During the migration window we may also face undiscovered weaknesses in a young
PQ implementation. Hybrid exists precisely so that a break in *one* scheme is
not fatal.

## Decision

`HYBRID_ECDSA_ML_DSA_44` (alg_id `0x02`) requires **both** the ECDSA signature
**and** the ML-DSA-44 signature to verify over the transaction. This is
**conjunctive (AND)** semantics. If either signature is missing, malformed, or
fails verification, the input is **rejected**. There is no path in which a single
valid signature authorises a hybrid spend.

## Alternatives considered

1. **OR-hybrid (disjunctive):** accept the spend if *either* the ECDSA *or* the
   ML-DSA signature verifies. **Rejected.** OR-hybrid gives an attacker the
   *union* of the attack surfaces, not the intersection: an adversary who breaks
   **either** scheme can forge a valid spend. If the classical scheme falls to a
   quantum computer, OR-hybrid provides *zero* post-quantum protection because
   the ECDSA branch alone still authorises spends. OR-hybrid is strictly weaker
   than the weaker of its two components — the opposite of the intended goal.
2. **PQ-only (ML-DSA-44 alone, alg_id `0x01`):** no classical component.
   Not rejected as a concept — it is a distinct registry entry and a valid
   end-state — but it is not "hybrid." It drops the defence-in-depth that a young
   PQ implementation benefits from during transition: any undiscovered flaw in
   the PQ scheme or its implementation would be un-backstopped. Hybrid is the
   safer *transition* mode; PQ-only is a later destination.

## Pros

- **Security is the intersection, not the union:** forging a hybrid spend
  requires breaking **both** ECDSA **and** ML-DSA-44. An attacker with a quantum
  computer (ECDSA broken) still cannot spend without also breaking ML-DSA.
- Backstops a young PQ implementation: an undiscovered ML-DSA implementation flaw
  is covered by the still-required ECDSA signature, and vice versa.
- Clean, unambiguous validation rule: two verifications, both must pass.

## Risks

- **Larger witnesses:** a hybrid input carries both signatures and both public
  keys (ECDSA 64/33 + ML-DSA-44 2420/1312), stressing per-tx and per-block size
  limits — see ADR-003 for the size accounting and consensus limits.
- **Higher verification cost:** two verifications per input instead of one.
- **Both keys must be managed:** losing or mishandling either key breaks the
  spend; wallet UX must make the dual-key nature explicit (see ADR-007).
- AND semantics remove the "graceful degradation" some operators might expect
  from OR — that removal is intentional and must be documented for integrators.

## Consensus impact

**NONE now — research only, activates nothing.** Would be a consensus change if
ever activated; deferred, not in this PR. The hybrid path is inert while
`PQ_ACTIVATION_HEIGHT = INT64_MAX`. Any future activation of alg_id `0x02` is a
separate consensus proposal (ADR-005).

## Notes

- Signature threat framing (not "harvest now, decrypt later" — that is the
  KEM/encryption risk): an adversary COLLECTS public keys now from revealed
  pubkeys on-chain and FORGES signatures later once a quantum computer exists
  (Shor recovers the private key from the public key). Funds at revealed pubkeys
  (spent-from / reused addresses) are exposed; funds at unrevealed pubkeys
  (hash-locked, never spent) expose only the hash until spend time — a smaller
  window, though mempool exposure at spend creates a front-running window.
- ML-KEM (FIPS 203) is a KEM, not a signature scheme, and is not part of this
  hybrid decision.
- Related: ADR-001 (registry), ADR-003 (witness layout/sizes),
  ADR-007 (wallet dual-key UX). Prior iteration: docs/PQ_MIGRATION_V2.md (PR #37).
