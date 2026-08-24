# 02 — Consensus Surfaces That Touch Signatures

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## Two consensus signature surfaces

SOST consensus verifies signatures in exactly two places, with two different primitives and two
different purposes.

### 1. Spend verification — ECDSA secp256k1 (canonical LOW-S)

A transaction input is only valid if its ECDSA signature verifies against the committed public key
and is in canonical LOW-S form. Relevant code:

- Low-S check: `IsLowS` at `src/tx_signer.cpp:210`; `EnforceLowS` at `src/tx_signer.cpp:223`.
- Range/canonicality: `ValidateRSRange` (a LOW-S violation is error class **E5**) at
  `src/tx_signer.cpp:247` and `:277`.
- Curve verification: `secp256k1_ecdsa_verify` at `src/tx_signer.cpp:374`.
- Per-input verification entry point: `VerifyTransactionInput` at `src/tx_signer.cpp:551`.
- Header comment describing the scheme: `src/tx_signer.cpp:8,19`.

LOW-S enforcement removes signature malleability by rejecting the high-S sibling of every valid
signature. This is consensus-critical: two encodings of the same signature must not both be valid.

### 2. Block-identity binding — BIP-340 Schnorr (SbPoW only)

Under SbPoW, a miner binds identity to a candidate block with a BIP-340 Schnorr signature computed
in a **private, separate** secp256k1 context, gated at compile time by `SOST_HAVE_SCHNORRSIG`.

- Context setup: `src/sbpow.cpp:37-80`.
- Sign: `src/sbpow.cpp:249-270`.
- Verify: `src/sbpow.cpp:304-318`.

This Schnorr signature is **never** a spend authorisation. It does not appear in any `TxInput`
witness and cannot move coins.

## Why this is stated carefully

The distinction is easy to misread as "SOST uses Schnorr for transactions" — it does not. The public
site states the correct scope at `website/index.html:1413`: spend is ECDSA/LOW-S; Schnorr is
SbPoW block-identity binding only.

## Consensus and post-quantum

Any post-quantum change to spend verification would be a **new** consensus rule, gated behind a
versioned witness (see `03-transactions-and-signatures.md`) and an activation mechanism
(`08-activation-and-governance.md`). None of that is active: the prototype sentinel is
`PQ_ACTIVATION_HEIGHT = INT64_MAX` ("never active").
