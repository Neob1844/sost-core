# 11 — Glossary

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

- **ECDSA** — Elliptic Curve Digital Signature Algorithm; SOST's current spend signature scheme.
- **secp256k1** — the elliptic curve used by SOST for ECDSA spend signatures and (in a separate
  context) BIP-340 Schnorr.
- **LOW-S** — canonical form requiring the signature's `s` value to be in the lower half of the curve
  order; rejecting the high-S sibling removes malleability (`src/tx_signer.cpp:210-277`).
- **Schnorr / BIP-340** — a signature scheme; in SOST used **only** for SbPoW block-identity binding,
  never for spending (`src/sbpow.cpp`).
- **SbPoW** — Signature-bound Proof of Work; the mechanism where a miner binds identity to a block
  via a BIP-340 Schnorr signature.
- **ML-DSA** — Module-Lattice Digital Signature Algorithm; the NIST post-quantum signature standard
  in FIPS 204, standardised by NIST from CRYSTALS-Dilithium. Research/prototype in SOST, not active.
- **ML-KEM** — Module-Lattice Key Encapsulation Mechanism (FIPS 203); a **KEM for key
  establishment**, **not** a signature scheme. Not used by SOST for spend.
- **SLH-DSA** — Stateless Hash-based Digital Signature Algorithm (FIPS 205); a hash-based **backup**
  signature, not an automatic replacement; sizes are parameter-set dependent.
- **FIPS 204** — NIST standard for ML-DSA (signatures).
- **FIPS 203** — NIST standard for ML-KEM (key encapsulation).
- **FIPS 205** — NIST standard for SLH-DSA (hash-based signatures).
- **crypto-agility** — the ability to switch signature algorithms without a monolithic break, here
  via a 1-byte `alg_id` in a versioned witness.
- **hybrid AND** — a spend that requires **both** ECDSA **and** ML-DSA to verify (conjunctive); a
  forgery must break **both**. OR-hybrids are rejected because breaking either scheme would suffice.
- **witness** — the variable-length signature/key envelope proposed (provisional tx version 2) to
  carry post-quantum signatures; contrast the current fixed 64+33 `TxInput` layout.
- **alg_id** — a 1-byte selector in the versioned witness naming the signature algorithm
  (`0x00` legacy ECDSA, `0x01` ML-DSA-44, `0x02` hybrid, reserved values otherwise; PROVISIONAL).
- **sighash** — the message digest a signature commits to (what is actually signed for an input).
- **domain separation** — using distinct contexts/prefixes so signatures for one purpose (e.g. SbPoW
  identity) cannot be replayed as another (e.g. spend); SbPoW uses a separate secp256k1 context.
