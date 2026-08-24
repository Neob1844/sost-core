# 08 — Activation and Governance (summary)

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

This is a **summary**. The detailed activation plan lives in `docs/PQ_ACTIVATION_PLAN_V3.md`.

## Explicit statement

**Any post-quantum activation is a consensus change.** It requires a **separate, reviewed, audited,
and publicly announced** upgrade. **It is NOT this PR and NOT this document set.** Nothing here flips
a switch, sets a height, or changes a validation rule.

## Current activation state

- Prototype sentinel: `PQ_ACTIVATION_HEIGHT = INT64_MAX`, meaning "never active". This is the same
  never-active sentinel already used by `POPC_V15_ACTIVATION_HEIGHT` and `atomic_swap_htlc_active_at`.
- The reserved governance placeholder is `include/sost/proposals.h:44` — proposal id 8
  "post_quantum", status `DEFINED`, all heights `-1`. It is **inert** and changes no behaviour.
  Its label still reads "SPHINCS+/Dilithium" (historical naming); V3 notes this should eventually be
  reworded to ML-DSA (FIPS 204) but that rewording changes nothing on-chain.

## Preconditions for any future activation

1. Completed prototype and testnet soak (`06-post-quantum-roadmap.md`).
2. A performance model with real measured timings (currently RESULTS_PENDING_COMPUTE_ENV).
3. An external security audit (none exists today).
4. A finalised, non-provisional `alg_id` registry.
5. A published, separate consensus upgrade with an announced signaling/activation mechanism.

## Governance framing

Activation would follow SOST's existing consensus-change process (see `docs/SOST_GOVERNANCE_MODEL.md`
and `docs/FORK_MECHANISM_AND_FUTURE_CONSENSUS.md`), not an ad-hoc merge. No fixed dates or heights
are proposed here by design.

## Cross-references

- Detailed plan: `docs/PQ_ACTIVATION_PLAN_V3.md`
- Roadmap phases: `06-post-quantum-roadmap.md`
