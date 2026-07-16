# 06 — Post-Quantum Research Roadmap (phases, no dates)

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## No dates, no heights — only phase labels and conditions

This roadmap uses **phase labels (A–J)** and **entry conditions**. It contains **no calendar dates
and no block heights**. Any date currently visible on the website (e.g. 2027/2028/2030 on
`website/sost-security.html:634-637`) is **aspirational and NOT canonical** under V3. The detailed
plan lives in `docs/PQ_MIGRATION_V3.md`.

## Conceptual phases

- **Phase A — Framing & threat model.** Establish the correct signature threat framing (collect
  keys now, forge later; not "harvest now, decrypt later"). See `05-security-model.md`.
- **Phase B — Crypto-agility registry.** Define the 1-byte `alg_id` registry and the versioned
  witness envelope (provisional tx version 2). Provisional, not active.
- **Phase C — Prototype ML-DSA-44 witness.** Implement FIPS 204 ML-DSA-44 verification behind the
  `PQ_ACTIVATION_HEIGHT = INT64_MAX` sentinel; prototype/testnet only.
- **Phase D — Hybrid AND scheme.** Add HYBRID_ECDSA_ML_DSA_44 (`0x02`): both signatures must verify.
- **Phase E — Testnet activation & soak.** Exercise the witness on testnet; measure size and cost.
- **Phase F — Performance modelling.** Quantify tx/block impact from FIPS 204 sizes
  (`09-performance-and-limits.md`, `docs/PQ_PERFORMANCE_MODEL_V3.md`). Timings
  RESULTS_PENDING_COMPUTE_ENV.
- **Phase G — Wallet migration design.** Key derivation, dual-key custody, address handling
  (`07-wallet-migration.md`, `docs/PQ_WALLET_MIGRATION_V3.md`).
- **Phase H — External security audit.** No audit has occurred; this is a precondition, not a claim.
- **Phase I — Governance & activation proposal.** A separate, reviewed, announced consensus upgrade
  (`08-activation-and-governance.md`, `docs/PQ_ACTIVATION_PLAN_V3.md`).
- **Phase J — Legacy handling & optional deprecation.** Conditions (not dates) for winding down
  legacy ECDSA-only spends, if ever adopted.

## Reserved / backup algorithms

The registry reserves `0x03` ML_DSA_65 and `0x04` ML_DSA_87 (higher NIST levels) and `0x10`
SLH-DSA (FIPS 205, hash-based backup). SLH-DSA is a **backup**, not an automatic replacement; its
sizes are parameter-set dependent (`11-glossary.md`, `09-performance-and-limits.md`).

## Non-goals of this roadmap

- It does not activate anything.
- It does not fix any date or height.
- It does not claim quantum resistance or audit completion.
