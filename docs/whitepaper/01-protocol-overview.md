# 01 — Protocol Overview (crypto placement)

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## Scope of this document

This is a neutral map of **where cryptographic signatures sit** in SOST. It intentionally does
**not** restate proof-of-work parameters, emission schedule, supply cap, or difficulty rules — those
live in the consensus source and existing specs (`docs/V13_SPEC.md`, `docs/V11_SPEC.md`, and the
`include/sost/consensus_constants.h` header). Read this only for the cryptographic surface.

## The three places cryptography lives

1. **Spend authorisation (per transaction input).** Every non-coinbase input carries an ECDSA
   secp256k1 signature and a compressed public key. This is the *only* signature a wallet produces
   to move funds. Detailed in `03-transactions-and-signatures.md`.

2. **Block-identity binding (SbPoW).** A miner binds identity to a candidate block using a BIP-340
   Schnorr signature under a *separate, private* secp256k1 context. This never authorises a spend
   and never appears in a transaction witness. Detailed in `04-sbpow.md`.

3. **Address commitment.** Outputs commit to `RIPEMD160(SHA256(pubkey))` (a 20-byte hash), so a
   recipient's public key is not revealed on-chain until the coin is spent. This hashing is the
   basis of the quantum-exposure argument in `05-security-model.md`.

## Why the boundary matters

Keeping spend (ECDSA) and block-identity (Schnorr) cleanly separated means a change to the spend
scheme — such as a future post-quantum witness — does **not** touch SbPoW, and vice versa. This
separation is what makes a *versioned, opt-in* migration path feasible without a monolithic rewrite.

## What is not here

- No emission/supply/difficulty numbers (see existing consensus docs).
- No activation dates or heights for any post-quantum change.
- No claim of quantum resistance.

## Next

- `02-consensus.md` — the consensus surfaces that actually touch signature verification.
- `06-post-quantum-roadmap.md` — the conceptual research phases.
