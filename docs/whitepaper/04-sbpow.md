# 04 — SbPoW Schnorr Scope

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## What SbPoW Schnorr is (and is not)

Under SbPoW, a miner binds their identity to a candidate block using a **BIP-340 Schnorr** signature.
This is **block-identity binding only** — it is **not** a spend scheme and never authorises moving
coins.

- Computed in a **private, separate** secp256k1 context (isolated from spend verification).
- Gated at compile time by `SOST_HAVE_SCHNORRSIG`.
- Context setup: `src/sbpow.cpp:37-80`.
- Sign: `src/sbpow.cpp:249-270`.
- Verify: `src/sbpow.cpp:304-318`.

The public site already states this scope honestly at `website/index.html:1413`: the BIP-340 Schnorr
signature is only the SbPoW block-identity binding, not the spend scheme.

## Why the separation matters

Because Schnorr here is confined to block identity and lives in its own context, it does not overlap
with the ECDSA spend path (`03-transactions-and-signatures.md`). A future post-quantum change to
*spend* signatures would not touch SbPoW, and vice versa. Do not describe SOST as "using Schnorr for
transactions" — it does not.

## Quantum note

BIP-340 Schnorr over secp256k1 is a classical (not post-quantum) primitive, so SbPoW block-identity
binding carries the same classical assumptions discussed in `05-security-model.md`. Any hardening of
SbPoW identity binding is out of scope for the transaction-signature migration described in this V3
document set and is not addressed here.
