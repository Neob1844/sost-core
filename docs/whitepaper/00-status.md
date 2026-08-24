# 00 — Implementation Status

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## Honest one-paragraph summary

SOST today spends coins with classical **ECDSA over secp256k1**, using compact 64-byte
signatures in canonical **LOW-S** form (`README.md:196`, `src/tx_signer.cpp`). The only other
signature primitive in consensus is **BIP-340 Schnorr**, and it is used *exclusively* to bind a
miner's identity to a block under SbPoW — never to authorise a spend (`src/sbpow.cpp`,
`website/index.html:1413`). SOST is **not** post-quantum secure today, and this V3 document set does
**not** make it so. Everything about ML-DSA (FIPS 204), the crypto-agility algorithm registry, and
the hybrid ECDSA-AND-ML-DSA scheme described in these docs is **research and prototype only**. There
is **no activation height, no calendar date, and nothing merged into consensus.** The prototype
activation sentinel is `PQ_ACTIVATION_HEIGHT = INT64_MAX`, i.e. "never active", the same
never-active sentinel already used by `POPC_V15_ACTIVATION_HEIGHT` and `atomic_swap_htlc_active_at`.

## What is mainnet-active

| Surface | Primitive | Status |
| --- | --- | --- |
| Transaction spend authorisation | ECDSA secp256k1, compact 64-byte `r\|\|s`, canonical LOW-S | Active |
| SbPoW block-identity binding | BIP-340 Schnorr (gated by `SOST_HAVE_SCHNORRSIG`) | Active |
| Address commitment | RIPEMD160(SHA256(pubkey)) — 20-byte pubkey hash | Active |

## What is research / prototype only

- ML-DSA (FIPS 204, standardised by NIST from CRYSTALS-Dilithium) witness format.
- The provisional 1-byte `alg_id` crypto-agility registry (see `11-glossary.md` and
  `06-post-quantum-roadmap.md`).
- The hybrid scheme requiring **both** ECDSA **and** ML-DSA-44 to verify (conjunctive AND).
- A provisional transaction **version 2** witness envelope.

## What is explicitly NOT active

- Any post-quantum transaction validation on mainnet.
- Any ML-DSA, ML-KEM, or SLH-DSA verification in consensus.
- Any activation height or date. There is none, by design, at this stage.

## What SOST does NOT claim

SOST does not claim to be "quantum-safe" or "post-quantum secure", and does not claim ML-DSA is
active. The public site already states this honestly under a "NOT CLAIMED" panel
(`website/index.html:1413`).

## Where to read more

- Current signature scheme: `03-transactions-and-signatures.md`
- SbPoW Schnorr scope: `04-sbpow.md`
- Research roadmap (phase labels, no dates): `06-post-quantum-roadmap.md`
- Detailed migration plan: `docs/PQ_MIGRATION_V3.md`

*V3 supersedes V2 (`docs/PQ_MIGRATION_V2.md`, PR #37). See `12-changelog.md`.*
