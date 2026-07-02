# 07 — Wallet Migration (summary)

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

This is a **summary**. The detailed design lives in `docs/PQ_WALLET_MIGRATION_V3.md`.

## The wallet migration problem

Today a wallet holds one secp256k1 key per address and produces one ECDSA signature per input
(`03-transactions-and-signatures.md`). A post-quantum migration means wallets must, in a future
prototype, additionally manage an ML-DSA (FIPS 204) key and produce a variable-length witness under
a provisional tx version 2. ML-DSA keys and signatures are large (ML-DSA-44: 1312-byte public key,
2420-byte signature), so backup, storage, and UX all change.

## Design principles (research)

- **Opt-in, not forced.** Legacy ECDSA (`alg_id 0x00`) inputs remain valid; nothing invalidates
  existing coins.
- **Hybrid first.** Where a post-quantum spend is offered, the HYBRID (`0x02`) ECDSA-AND-ML-DSA
  path is preferred so a forgery requires breaking **both** schemes.
- **Move-to-safety guidance.** Because revealed public keys are the exposed set
  (`05-security-model.md`), wallets should discourage address reuse and, if a migration ever
  activates, guide users to spend from exposed addresses into post-quantum-protected ones.
- **No silent key rotation.** Any key-scheme change must be explicit and user-visible.

## What is NOT decided

- No key-derivation path, backup format, or address prefix is finalised here.
- No activation exists; `PQ_ACTIVATION_HEIGHT = INT64_MAX` ("never active").
- The `sost2` address idea shown aspirationally on the website is **not canonical** under V3.

## Cross-references

- Detailed plan: `docs/PQ_WALLET_MIGRATION_V3.md`
- Security rationale: `05-security-model.md`
- Sizes: `09-performance-and-limits.md`
