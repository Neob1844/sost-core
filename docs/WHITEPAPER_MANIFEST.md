# SOST Whitepaper / Cryptography Documentation Manifest

> **IMPLEMENTATION STATUS**
> - **Mainnet-active:** ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
> - **Research-prototype:** ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
> - **Not active on mainnet:** post-quantum transaction validation (no activation height, no date, not merged)
>
> This document is research/architecture only. It changes no consensus rule and activates nothing.

## Purpose

This manifest inventories **every documentation surface that mentions SOST cryptography** and
records which surface is the source-of-truth versus a downstream copy.

**`docs/whitepaper/` is the canonical content tree.** The files `00-status.md` … `12-changelog.md`
are the single source of truth for every statement SOST makes about its cryptography. All other
surfaces — the `README.md`, the `website/*.html` pages, and marketing material — are **downstream
copies** that must be kept in agreement with the canonical tree.

Synchronisation is intended to be checked by `scripts/check_whitepaper_sync.py` (a sync-linter that
verifies each downstream surface states the canonical crypto claims and contradicts none of them).
**Note:** that script does not exist in the working tree yet; until it lands, sync is a manual
contributor responsibility per the checklist below.

**Aspirational dates are NOT canonical.** The website currently carries aspirational calendar dates
for post-quantum migration (2027/2028/2030 — e.g. `website/sost-security.html:634-637`,
`website/sost-technology.html`, `website/sost-roadmap.html`). Under V3 these are **NOT canonical**:
there is **no fixed activation date and no activation height**. The canonical roadmap uses phase
labels only (`docs/whitepaper/06-post-quantum-roadmap.md`).

## Inventory

Last-updated column reflects this manifest revision, 2026-07-02.

| Doc (path) | Purpose | Audience | Canonical source | Generated vs Manual | Language | Last-updated | Crypto sections | Sync status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `docs/whitepaper/00-status.md` | Honest implementation status | Devs, reviewers | **Canonical** | Manual | EN | 2026-07-02 | Whole doc | Source-of-truth |
| `docs/whitepaper/01-protocol-overview.md` | Where crypto sits | Devs | **Canonical** | Manual | EN | 2026-07-02 | Signature placement | Source-of-truth |
| `docs/whitepaper/02-consensus.md` | Consensus signature surfaces | Devs, reviewers | **Canonical** | Manual | EN | 2026-07-02 | Spend ECDSA / SbPoW Schnorr | Source-of-truth |
| `docs/whitepaper/03-transactions-and-signatures.md` | Canonical tx signature scheme | Devs, integrators | **Canonical (primary)** | Manual | EN | 2026-07-02 | Whole doc | Source-of-truth |
| `docs/whitepaper/04-sbpow.md` | Schnorr scope (block-identity only) | Devs | **Canonical** | Manual | EN | 2026-07-02 | SbPoW Schnorr | Source-of-truth |
| `docs/whitepaper/05-security-model.md` | Classical model + quantum framing | Reviewers, users | **Canonical** | Manual | EN | 2026-07-02 | Threat model | Source-of-truth |
| `docs/whitepaper/06-post-quantum-roadmap.md` | Research phases (no dates) | All | **Canonical** | Manual | EN | 2026-07-02 | PQ roadmap | Source-of-truth |
| `docs/whitepaper/07-wallet-migration.md` | Wallet migration summary | Wallet devs | **Canonical (summary)** | Manual | EN | 2026-07-02 | Key/witness handling | Source-of-truth |
| `docs/whitepaper/08-activation-and-governance.md` | Activation is a separate upgrade | Governance, reviewers | **Canonical (summary)** | Manual | EN | 2026-07-02 | Activation/governance | Source-of-truth |
| `docs/whitepaper/09-performance-and-limits.md` | Size limits + FIPS 204 sizes | Devs, reviewers | **Canonical** | Manual | EN | 2026-07-02 | Sizes/limits | Source-of-truth (timings PENDING) |
| `docs/whitepaper/10-known-limitations.md` | Honest limitations | All | **Canonical** | Manual | EN | 2026-07-02 | All limitations | Source-of-truth |
| `docs/whitepaper/11-glossary.md` | Precise definitions | All | **Canonical** | Manual | EN | 2026-07-02 | All terms | Source-of-truth |
| `docs/whitepaper/12-changelog.md` | V3 changelog | All | **Canonical** | Manual | EN | 2026-07-02 | V3 vs V2 | Source-of-truth |
| `README.md` | Repo overview + params table | Devs | Downstream | Manual | EN | 2026-07-02 | `README.md:196` (Signature = ECDSA secp256k1 LOW-S) | In sync (spend claim) |
| `website/index.html` | Public landing | Public | Downstream | Manual | EN | 2026-07-02 | `:1413` NOT-CLAIMED panel (ECDSA spend; Schnorr = SbPoW only; PQ not active) | In sync (honest) |
| `website/sost-whitepaper.html` | Public whitepaper page | Public | Downstream | Manual | EN | 2026-07-02 | Crypto summary | Needs review vs canonical |
| `website/whitepaper-reader.html` | Whitepaper reader UI | Public | Downstream | Manual/Generated shell | EN | 2026-07-02 | Crypto summary | Needs review vs canonical |
| `website/sost-technology.html` | Technology page | Public | Downstream | Manual | EN | 2026-07-02 | Crypto + PQ dates (aspirational) | Out of sync (2027 date not canonical) |
| `website/sost-security.html` | Security page | Public | Downstream | Manual | EN | 2026-07-02 | PQ migration phases w/ 2027/2028/2030 dates (`:634-637`) | Out of sync (dates not canonical) |
| `marketing/SOST_AGGREGATOR_LISTINGS.md` | Exchange/aggregator listing copy | Listings, BD | Downstream | Manual | EN | 2026-07-02 | Signature/crypto line | Needs review vs canonical |
| `include/sost/proposals.h` (`:44`) | Inert governance placeholder | Devs | Downstream (code) | Manual | C++ | 2026-07-02 | proposal id 8 "post_quantum" label "SPHINCS+/Dilithium" | Legacy naming — reword to ML-DSA (inert, no behaviour change) |
| `docs/PQ_MIGRATION_V2.md` | Prior migration iteration (PR #37) | Devs | Superseded | Manual | EN | (V2) | PQ migration v2 | Superseded by V3 — **not present in working tree** (referenced only) |
| `docs/PQ_MIGRATION_V3.md` | Detailed V3 migration plan | Devs, reviewers | Companion (detailed) | Manual | EN | planned | Full PQ plan | Planned companion (not created in this change) |
| `docs/PQ_WALLET_MIGRATION_V3.md` | Detailed wallet migration | Wallet devs | Companion (detailed) | Manual | EN | planned | Wallet migration | Planned companion (not created in this change) |
| `docs/PQ_ACTIVATION_PLAN_V3.md` | Detailed activation plan | Governance | Companion (detailed) | Manual | EN | planned | Activation | Planned companion (not created in this change) |
| `docs/PQ_PERFORMANCE_MODEL_V3.md` | Detailed performance model | Devs | Companion (detailed) | Manual | EN | planned | Perf/sizes | Planned companion (not created in this change); timings RESULTS_PENDING_COMPUTE_ENV |

Related existing surface (not PQ-V3 but crypto-adjacent): `docs/QUANTUM_RESISTANCE_RESEARCH.md`
(earlier research note) — should be reconciled against the canonical tree in a later pass.

## SYNC MATRIX

Each canonical crypto claim below MUST be stated (and never contradicted) on every listed surface.

### Claim 1 — Spend = ECDSA secp256k1, compact 64-byte, canonical LOW-S

Canonical: `docs/whitepaper/03-transactions-and-signatures.md` (facts: `README.md:196`,
`src/tx_signer.cpp:210/223/247/277/374/551`, `include/sost/transaction.h:72-73`).

Must state it: `README.md` (`:196` ✓) · `website/index.html` (`:1413` ✓) · `website/sost-whitepaper.html` ·
`website/whitepaper-reader.html` · `website/sost-technology.html` · `website/sost-security.html` ·
`marketing/SOST_AGGREGATOR_LISTINGS.md`.

### Claim 2 — Schnorr (BIP-340) = SbPoW block-identity binding ONLY, not spend

Canonical: `docs/whitepaper/04-sbpow.md` (facts: `src/sbpow.cpp:37-80/249-270/304-318`,
`website/index.html:1413`).

Must state it (where crypto is described in any depth): `website/index.html` (`:1413` ✓) ·
`website/sost-technology.html` · `website/sost-security.html` · `website/sost-whitepaper.html` ·
`website/whitepaper-reader.html`. README and marketing must **not** imply Schnorr is a spend scheme.

### Claim 3 — Post-quantum = NOT active (no date, no height, not merged)

Canonical: `docs/whitepaper/00-status.md`, `08-activation-and-governance.md`
(fact: `PQ_ACTIVATION_HEIGHT = INT64_MAX`; inert placeholder `include/sost/proposals.h:44`).

Must state it: every surface that mentions post-quantum at all — `website/index.html` (`:1413` ✓) ·
`website/sost-technology.html` (⚠ carries aspirational dates) · `website/sost-security.html`
(⚠ `:634-637` dates) · `website/sost-roadmap.html` · `website/sost-whitepaper.html` ·
`marketing/SOST_AGGREGATOR_LISTINGS.md`. Surfaces marked ⚠ must be corrected: the 2027/2028/2030
dates are **not canonical** and must not be presented as committed activation dates.

## MANDATORY CHECKLIST

Complete every item when touching crypto / consensus / prototype code or any crypto documentation.

- [ ] Read `docs/whitepaper/03-transactions-and-signatures.md` (the canonical tx signature scheme).
- [ ] Any new on-chain crypto fact cites `file:line` and matches the source (do not paraphrase away
      the LOW-S, 64/33 fixed layout, or SbPoW-Schnorr-only scope).
- [ ] Do **not** claim SOST is "quantum-safe" / "post-quantum secure", or that ML-DSA is active.
- [ ] Use correct terminology: ML-DSA (FIPS 204), ML-KEM (FIPS 203, a KEM not a signature),
      SLH-DSA (FIPS 205, a backup). "CRYSTALS-Dilithium" only in the historical phrasing.
- [ ] Do **not** introduce fixed activation dates or block heights. Use phase labels + conditions.
- [ ] Keep `PQ_ACTIVATION_HEIGHT = INT64_MAX` unless this is the separate, reviewed, audited,
      announced activation upgrade (it is not, for docs/prototype changes).
- [ ] If the `alg_id` registry is touched, mark it PROVISIONAL and note it supersedes/reassigns V2.
- [ ] Hybrid is **AND** (both ECDSA and ML-DSA verify); never document an OR-hybrid as valid.
- [ ] Do not invent performance timings (mark RESULTS_PENDING_COMPUTE_ENV) or audit results
      (none exist).
- [ ] Update every downstream surface in the SYNC MATRIX that states the affected claim, and update
      this manifest's Last-updated / Sync status.
- [ ] Run `scripts/check_whitepaper_sync.py` once it exists; until then, verify sync manually.
- [ ] No AI attribution; no personal email; author is NeoB.

---
*Canonical tree: `docs/whitepaper/`. This manifest and the tree supersede V2 (`docs/PQ_MIGRATION_V2.md`, PR #37).*
