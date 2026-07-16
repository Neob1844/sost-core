# 12 — Changelog

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## V3 — 2026-07-02 (this document set)

**V3 supersedes V2** (`docs/PQ_MIGRATION_V2.md`, PR #37). V2/PR #37 is left intact and is not
deleted or contradicted without note.

### What V3 adds

- A canonical content tree under `docs/whitepaper/` (`00-status.md` … `12-changelog.md`) that is the
  single source of truth for SOST cryptography statements.
- `docs/WHITEPAPER_MANIFEST.md` — an inventory of every doc surface that mentions crypto, a SYNC
  MATRIX of crypto claims to surfaces, and a MANDATORY CHECKLIST for contributors.
- Corrected, consistent terminology: **ML-DSA (FIPS 204)** (from CRYSTALS-Dilithium), **ML-KEM
  (FIPS 203)** as a KEM (not a signature), **SLH-DSA (FIPS 205)** as a backup.
- The correct signature threat framing ("collect public keys now, forge later" via Shor), explicitly
  distinguished from the "harvest now, decrypt later" KEM/encryption framing.
- A revised, **PROVISIONAL** crypto-agility `alg_id` registry that **reassigns ids relative to V2**
  (V2 used `0x02`=ML_DSA_65, `0x10`=HYBRID_44; V3 uses `0x01`=ML_DSA_44, `0x02`=HYBRID_ECDSA_ML_DSA_44).
  No protocol conflict because `PQ_ACTIVATION_HEIGHT = INT64_MAX` (unused).
- Hybrid defined as **AND** (both ECDSA and ML-DSA must verify); OR-hybrid explicitly rejected.
- Explicit removal of fixed calendar dates/heights; website dates (2027/2028/2030) marked **not
  canonical**.

### What V3 does NOT change

- No consensus rule, no validation behaviour, no activation. `PQ_ACTIVATION_HEIGHT` remains
  `INT64_MAX`.
- The inert reserved proposal at `include/sost/proposals.h:44` (still labelled "SPHINCS+/Dilithium")
  is unchanged; V3 only notes it should eventually be reworded to ML-DSA.

## V2 — prior iteration (PR #37)

`docs/PQ_MIGRATION_V2.md`. Introduced the earlier migration framing and the original `alg_id`
assignments now superseded by V3. Retained for history.

---
*Author: NeoB. No AI attribution.*
