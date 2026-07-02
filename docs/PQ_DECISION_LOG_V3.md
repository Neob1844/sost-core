# PQ Decision Log — V3 (RESEARCH / DOCS ONLY)

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

> Chronological record of the V3 post-quantum design decisions. V3 supersedes
> `docs/PQ_MIGRATION_V2.md` (PR #37), which remains intact and is not contradicted without note.
> ML-DSA is the FIPS 204 signature standard (standardised by NIST from CRYSTALS-Dilithium);
> ML-KEM (FIPS 203) is a KEM, not a signature; SLH-DSA (FIPS 205) is a hash-based backup.

---

## Entry — 2026-07-02 — NeoB

### D1. Crypto-agility 1-byte `alg_id` registry
- **Context.** SOST spends today use a fixed ECDSA layout (`include/sost/transaction.h:72-73`).
  Any PQ path needs an extensible way to name the scheme that authorised a spend.
- **Decision.** Adopt a **1-byte `alg_id`** carried in the versioned witness, with the V3 registry:
  - `0x00` LEGACY_ECDSA_SECP256K1 (today's 64/33 fixed layout)
  - `0x01` PQ_ML_DSA_44 (FIPS 204, NIST L2)
  - `0x02` HYBRID_ECDSA_ML_DSA_44 (both must verify — AND)
  - `0x03` ML_DSA_65_RESERVED
  - `0x04` ML_DSA_87_RESERVED
  - `0x10` SLH_DSA_RESERVED
  - `0xFF` INVALID
  Any other value is **deterministically REJECTED**, never ignored.
- **Note on V2.** This **REASSIGNS** ids versus V2 (V2 used `0x02` = ML-DSA-65 and `0x10` = HYBRID-44).
  V3 **supersedes** V2. There is no protocol conflict because `PQ_ACTIVATION_HEIGHT = INT64_MAX`
  (the registry is unused on mainnet). V2 / PR #37 stays intact as the prior iteration.
- **Alternatives.** Multi-byte id (rejected: unnecessary now, 256 values suffice); reuse V2 ids
  (rejected: V3 cleanup preferred while nothing is live).
- **Status.** **PROVISIONAL.**

### D2. Hybrid = AND, not OR
- **Context.** A hybrid spend can require either scheme (OR) or both (AND).
- **Decision.** HYBRID (`0x02`) requires **ECDSA AND ML-DSA-44** to both verify (conjunctive).
- **Rationale.** OR-hybrid lets an attacker who breaks *either* scheme forge a spend; AND forces the
  attacker to break **both**, so the hybrid is at least as strong as the stronger leg.
- **Alternatives.** OR-hybrid (rejected — strictly weaker); single-scheme-only (rejected — no
  defence-in-depth during transition).
- **Status.** **ACCEPTED** (as a design principle; not active).

### D3. Variable-length versioned witness under tx version 2
- **Context.** The current input layout is a **fixed** `signature[64]` + `pubkey[33]` with **no
  length prefix** (`include/sost/transaction.h:72-73`; `src/transaction.cpp:210-225`). ML-DSA keys
  and signatures are far larger and variable across schemes.
- **Decision.** Introduce a **variable-length, versioned witness** envelope gated by **tx version 2**
  (current field is `uint32_t version{1}` at `include/sost/transaction.h:109`). Legacy tx version 1
  is untouched.
- **Alternatives.** Widen the fixed arrays (rejected — wastes space for legacy, still not
  extensible); overload existing fields (rejected — breaks determinism and old parsers).
- **Status.** **PROVISIONAL.**

### D4. PQ library isolation behind an abstract interface
- **Context.** PQ implementations vary in license, maintenance, and side-channel posture.
- **Decision.** Access any PQ primitive through an **abstract crypto interface**; prefer the
  **NIST reference implementation** and/or **liboqs**. **No PQ library is added to the build** at
  this stage.
- **Rationale.** Swappability, auditability, and keeping unvetted code out of consensus paths.
- **Alternatives.** Vendoring a single library directly into consensus code (rejected — coupling,
  audit surface).
- **Status.** **PROVISIONAL** (interface design; nothing wired into the build).

### D5. No mainnet activation — INT64_MAX sentinel
- **Context.** The codebase uses a height of `INT64_MAX` to mean "never active" (as with
  `POPC_V15_ACTIVATION_HEIGHT` and `atomic_swap_htlc_active_at`).
- **Decision.** `PQ_ACTIVATION_HEIGHT = INT64_MAX`. No date, no height, not merged. The inert
  placeholder proposal (`include/sost/proposals.h:44`, id 8 "post_quantum", status DEFINED,
  heights -1, legacy "SPHINCS+/Dilithium" label) stays inert; eventual reword to ML-DSA changes
  no behaviour.
- **Alternatives.** Schedule a tentative height (rejected — nothing is audited or benchmarked).
- **Status.** **DEFERRED** (activation intentionally not scheduled).

### D6. Whitepaper-as-code
- **Context.** PQ design must stay in sync with the canonical project narrative.
- **Decision.** Treat `docs/whitepaper` as canonical and keep it synchronised via a sync script;
  V3 PQ docs live under `docs/` and reference the whitepaper rather than forking claims.
- **Alternatives.** Maintain PQ narrative separately (rejected — drift risk).
- **Status.** **ACCEPTED** (documentation process).

### D7. Wallet migration is opt-in
- **Context.** Migrating funds reveals pubkeys and creates a mempool front-running window.
- **Decision.** Fund migration is **opt-in with explicit warnings**; **no auto-migration**. Details
  in `docs/PQ_WALLET_MIGRATION_V3.md`.
- **Rationale.** Consent, custody safety, and avoiding a synchronized exposure window; ECDSA seed
  material does **not** yield an ML-DSA key, so PQ keys are separately derived/backed up.
- **Alternatives.** Scheduled auto-migration (rejected — custody hazard, stranding risk).
- **Status.** **ACCEPTED** (as recommendation; not active).

### D8. Witness component lengths use fixed uint16 big-endian (not CompactSize)
- **Context.** The versioned witness (D3) prefixes each component (signature / public key) with an
  explicit length. Earlier secondary docs (performance model §3, checklist §2, audit-package echoes)
  modelled that length as Bitcoin-style `CompactSize`, while the normative wire spec
  (`docs/PQ_TX_FORMAT_V3.md §5`) and the prototype (`prototype/pq/pq_witness.h`) used a fixed 2-byte
  big-endian integer. The external-review package must present exactly one encoding.
- **Decision.** Every component length is `len_be16`: an **unsigned 16-bit integer, big-endian
  (network byte order), occupying exactly 2 bytes**. There is no `CompactSize`, varint, short form,
  long form, or alternative prefix. Each decoded length must equal the exact expected size for the
  component's `alg_id` and position; anything else is deterministically rejected. No allocation
  occurs before the exact expected length is checked.
- **Why CompactSize was rejected for V3.** CompactSize is variable-width (1/3/5/9 bytes) and carries
  a canonicalisation obligation (shortest-form enforcement) that is itself an attack surface; a
  fixed-width field has exactly one representation of each value and needs no canonicalisation rule.
  All currently proposed component sizes are below 65536 bytes (largest: ML-DSA-87 signature 4627),
  so 16 bits suffice.
- **Size impact.** Per-component overhead is a flat 2 bytes. Per-input modelled sizes:
  LEGACY-under-envelope 138, ML-DSA-44 3773, ML-DSA-65 5302, ML-DSA-87 7260, HYBRID 3874
  (`docs/PQ_PERFORMANCE_MODEL_V3.md §3`).
- **Compatibility.** No effect on mainnet: `PQ_ACTIVATION_HEIGHT = INT64_MAX` and version-1
  serialization (which uses no length prefix) is untouched. This is a property of the provisional
  version-2 witness only.
- **Risks.** Accidental little-endian encoding, a one-byte prefix, or a CompactSize-style prefix are
  each rejected as a wrong/oversized length; negative vectors cover all three
  (`tests/pq_vectors/`, `docs/examples/pq/witness_vectors.json`). Parser-differential risk across
  implementations is flagged for external review.
- **Future-proofing.** A component exceeding 65535 bytes could not be expressed under `len_be16` and
  would require a **new witness version**, never an alternative interpretation of the V3 length field.
- **Status.** **PROVISIONAL** — pending external review and a separate consensus proposal.

---

## DECISIONS PENDING (open items — not yet decided)

- **Final `alg_id` assignments** — current V3 ids are PROVISIONAL and may change before any
  activation.
- **Exact size limits / weights** — per-input and per-block accounting for PQ witnesses, including
  whether `MAX_TX_BYTES_*` / `MAX_INPUTS_CONSENSUS` need revision; **no unjustified weight discount
  for PQ** (`docs/PQ_PERFORMANCE_MODEL_V3.md`).
- **Activation height** — none; remains `INT64_MAX` until governance decides.
- **External audit** — not performed; scope, auditor, and sign-off pending
  (`docs/PQ_AUDIT_CHECKLIST_V3.md`).
- **Testnet parameters** — isolated testnet configuration for PQ/HYBRID not finalised.
- **Final address prefix** — `sost2…` is an **aspirational placeholder only**, not final; whether
  PQ and HYBRID share a prefix is undecided (`docs/PQ_WALLET_MIGRATION_V3.md`).
- **PQ key derivation scheme** — the exact KDF/derivation for the PQ branch is intentionally
  unspecified pending design + review.

---

*Author: NeoB, 2026-07-02. Research/architecture only — activates nothing.*
