# SOST Post-Quantum Research — Master Index (V3)

STATUS: RESEARCH ONLY

SOST mainnet does not currently use post-quantum transaction signatures.

Transaction spending remains ECDSA over secp256k1 with canonical LOW-S.
BIP-340 Schnorr is used only for SbPoW block-identity binding.

The material indexed here is architecture, documentation, testing and an
isolated prototype. It is not merged, not deployed, not audited and not active.

---

> This file is the single entry point for the SOST post-quantum (PQ) research
> archive on branch `draft/pq-migration-v3-docsync` (PR #38, **DRAFT**). It is an
> **index and status page**, not a specification and not an audit. Every artefact
> it points to is research, documentation, testing or an isolated non-compiled
> prototype. Nothing here changes consensus, and nothing here claims SOST is
> post-quantum or quantum-resistant.

## 1. Plain-language current status

SOST has **not** migrated to post-quantum cryptography. Today, spending a SOST
output is authorised by an ordinary ECDSA signature over the secp256k1 curve, the
same family Bitcoin uses, with canonical LOW-S enforcement. A separate Schnorr
(BIP-340) signature is used only to bind a miner's identity to a block under
SbPoW — it never authorises a spend. Everything in this archive is a paper-and-
prototype study of *how* SOST could add a post-quantum signature option later. It
is not switched on, not scheduled, and not independently reviewed.

## 2. What IS active today (mainnet)

- **Spend authorisation:** ECDSA over secp256k1, compact 64-byte `r||s`, canonical
  **LOW-S** (`README.md:196`; `src/tx_signer.cpp`; verify at
  `secp256k1_ecdsa_verify`).
- **Input layout:** fixed `signature[64]` + `pubkey[33]`, 133 bytes/input
  (`include/sost/transaction.h:72-73`, `src/tx_validation.cpp:77`).
- **Block-identity binding:** BIP-340 Schnorr, SbPoW **only**, in a separate
  secp256k1 context (`src/sbpow.cpp`). Not a spend scheme.
- **Hashing:** SHA-256, unaffected by Shor and only quadratically weakened by
  Grover; 256-bit output remains adequate.

## 3. What is NOT active

- No post-quantum transaction validation on mainnet.
- No ML-DSA / SLH-DSA verification in the node or miner build.
- No `liboqs`/`oqs` dependency in the node or miner build.
- No hybrid (ECDSA-AND-ML-DSA) witness accepted by consensus.
- No `sost2` PQ address type in production.
- No activation height and no activation date: `PQ_ACTIVATION_HEIGHT = INT64_MAX`.
- No external audit of any PQ material.

## 4. Researched architecture (summary)

A crypto-agile, versioned, variable-length **witness** carried under a future tx
version, selected by a 1-byte `alg_id` registry: LEGACY ECDSA (`0x00`), PQ
ML-DSA-44 (`0x01`), HYBRID ECDSA+ML-DSA (`0x02`); ids `0x03/0x04/0x10` reserved
and **rejected**, `0xFF` invalid sentinel. Component lengths use a fixed 2-byte
**big-endian (BE16)** prefix — no `CompactSize`, no varint. HYBRID means **AND**:
both the ECDSA and the ML-DSA components must verify. Candidate primary scheme is
**ML-DSA (FIPS 204)**, standardised by NIST from CRYSTALS-Dilithium; SLH-DSA is a
conceptual backup track. Full narrative: `docs/PQ_MIGRATION_V3.md` and
`docs/PQ_TX_FORMAT_V3.md`.

## 5. Index of all documents

Architecture / design:
- `docs/PQ_MIGRATION_V3.md` — top-level architecture and migration surface.
- `docs/PQ_TX_FORMAT_V3.md` — witness / transaction wire format (BE16).
- `docs/PQ_THREAT_MODEL_V3.md` — quantum and non-quantum threat model.
- `docs/PQ_SECURITY_ASSUMPTIONS_V3.md` — primitive and system assumptions.
- `docs/PQ_PERFORMANCE_MODEL_V3.md` — size, weight and verify-work model.
- `docs/PQ_DECISION_LOG_V3.md` — decisions D1–D8 with rationale.
- `docs/PQ_V3_CONSOLIDATION_REVIEW.md` — V2→V3 consolidation review.

Wallet / migration:
- `docs/PQ_WALLET_MIGRATION_V3.md` — key derivation, backup/restore/export/import,
  fund migration, legacy/PQ/hybrid address separation, exposed-pubkey risk,
  no-auto-migration.

Activation / testnet:
- `docs/PQ_ACTIVATION_PLAN_V3.md` — conditional phases A–H, no dates/heights,
  rollback, old/new client compatibility.
- `docs/PQ_TESTNET_PLAN_V3.md` — private-testnet plan, experimental flag OFF by
  default, mainnet/testnet separation.

Audit hand-off / peer-review package:
- `docs/PQ_AUDIT_CHECKLIST_V3.md` — pre-activation checklist (nothing ticked as
  done by SOST).
- `docs/PQ_EXTERNAL_AUDIT_BRIEF_V3.md` — brief for a would-be external auditor.
- `docs/PQ_EXTERNAL_AUDITOR_QUESTIONS_V3.md` — open questions for reviewers.
- `docs/PQ_EXTERNAL_AUDIT_MANIFEST_V3.md` — reproducibility + SHA-256 integrity
  manifest of every PQ file.

Benchmarks:
- `docs/PQ_BENCHMARK_RESULTS_V3.md` — size math (exact) + timing provenance rules.

Internal whitepaper tree (whitepaper-as-code):
- `docs/WHITEPAPER_MANIFEST.md` + `docs/whitepaper/00-status.md` …
  `docs/whitepaper/12-changelog.md`.

Historical (pre-V3, retained for history):
- `docs/QUANTUM_RESISTANCE_RESEARCH.md` — an **earlier** (pre-V3) research note.
  It predates the V3 doc set and uses the pre-standardisation name
  "CRYSTALS-Dilithium"; the V3 documents (which use the standardised name
  **ML-DSA / FIPS 204**) supersede it. Kept for history only; not normative.

## 6. Index of all ADRs (`docs/ADR/`)

- ADR-001 — crypto-agility (1-byte `alg_id` registry).
- ADR-002 — hybrid = AND, not OR.
- ADR-003 — variable-length versioned witness (fixed BE16 component lengths).
- ADR-004 — PQ library isolation behind an abstract interface.
- ADR-005 — no mainnet activation yet (`INT64_MAX`).
- ADR-006 — whitepaper-as-code.
- ADR-007 — wallet migration strategy (opt-in).

## 7. Index of the prototype (`prototype/pq/`)

Header-only, **not** in any CMake target, `#include`d by no consensus/wallet/
mempool/block translation unit, links no crypto library, activates no rule.

- `prototype/pq/pq_alg_registry.h` — `alg_id` registry, exact sizes, domain tags,
  sentinel; reserved ids rejected.
- `prototype/pq/pq_witness.h` — deterministic single-pass parser/serializer, fixed
  BE16 lengths, no trailing bytes.
- `prototype/pq/pq_validate.h` — conceptual LEGACY/PQ/HYBRID verify; HYBRID
  requires ECDSA **AND** ML-DSA (verify calls are injected hooks).
- `prototype/pq/README.md`.

## 8. Index of tests / vectors

- `tests/pq_vectors/test_pq_witness.cpp` — standalone unit + negative tests
  (serialize/deserialize/round-trip, unknown/reserved alg_id, truncated, wrong
  BE16, little-endian, CompactSize-attempt, wrong length, trailing bytes,
  duplicate/mis-ordered components, HYBRID one/both invalid, tampered sig, wrong
  pubkey). Not in ctest.
- `tests/pq_vectors/fuzz_pq_witness.cpp` — libFuzzer target for the parser.
- `tests/pq_vectors/README.md` — build/run instructions.
- `docs/examples/pq/witness_vectors.json` — machine-readable valid/invalid
  vectors.

## 9. Index of benchmarks (`scripts/pq_bench/`)

- `scripts/pq_bench/pq_bench_v3.py` — size math (exact, FIPS 204) + optional
  liboqs timings; never fabricates a timing.
- `scripts/pq_bench/README.md` — environment/provenance notes.
- `scripts/pq_bench/results/schema.json` — result schema (enforces a provenance
  block).
- `scripts/pq_bench/results/sample_run.json` — illustrative sample (timings
  pending).
- `scripts/pq_bench/results/measured_2026-07-02_i9-10885H_wsl2.json` — indicative
  ML-DSA run (WSL2, turbo not pinned → order-of-magnitude only).

## 10. Index of the peer-review package

The audit hand-off documents (§5) make one point explicitly: **no external audit
of any kind has been performed on this PQ material.** The package exists so that
the community and independent experts can peer-review it. **A machine/AI review is
not an audit.** Any professional cryptographic/implementation audit remains
**pending funding and scheduling** and is a prerequisite for a future activation
proposal, not part of this PR.

## 11. Executed results (this environment)

- Prototype unit + negative tests: **33/33 PASS** (exit 0).
- libFuzzer smoke (clang + ASan/UBSan, ~20 s): **~8.8M execs, 0 crashes / 0 leaks
  / 0 UB**.
- `scripts/check_crypto_claims.py`: **OK** (no dangerous crypto claims).
- `scripts/check_whitepaper_sync.py`: **OK**.
- Benchmark size math: reproduced the published size table.
- All PQ JSON (`witness_vectors.json`, `schema.json`, `sample_run.json`,
  `measured_*.json`): **valid**.
- Manifest SHA-256 table: **self-verifies** (`sha256sum -c`).

## 12. Pending results

- Authoritative ML-DSA timings on clock-pinned bare-metal hardware, with an ECDSA
  secp256k1 baseline, full HYBRID cost, peak memory and p99:
  **RESULTS_PENDING_COMPUTE_ENV** (no `oqs` binding installed in the build/CI
  environment).
- FIPS 204 ACVP known-answer vectors: **NOT_RUN** (audit-scope, not in-repo).

## 13. Known risks (from the threat model / decision log)

- Exposed public keys become spendable by a future quantum adversary once revealed
  in a spend; unspent (hash-only) outputs are safer until first spend.
- Harvest-now-decrypt-later: signed data is permanent, so migration must be
  planned early even though the threat is years out.
- PQ signatures are large (ML-DSA-44 ≈ 3.7 KB/input vs 133 B legacy) — real
  block-throughput and fee implications; no weight discount assumed.
- Encoding-canonicality risks (little-endian, one-byte prefix, CompactSize-style
  prefix) are covered by negative tests.

## 14. Provisional decisions (subject to review)

- BE16 fixed 2-byte big-endian component lengths as the only V3 encoding (D8).
- ML-DSA-44 as the candidate primary PQ scheme; SLH-DSA as a conceptual backup.
- Hybrid = AND (D2); crypto-agility registry (D1); variable-length witness under a
  future tx version (D3); PQ library isolation (D4); opt-in wallet migration (D7).

## 15. Open decisions

- Final PQ parameter set(s) and whether to ship PQ-only, hybrid-only, or both.
- Any fee/weight treatment for large PQ witnesses.
- Version-signalling threshold and grace-window policy.
- Exact `sost2`-class address encoding.
- Whether the inert placeholder proposal (`include/sost/proposals.h:44`, still
  labelled "SPHINCS+/Dilithium") is reworded to ML-DSA in a later docs-only pass.

## 16. Conditions to resume this research

- Community/expert review feedback to fold in (Phase B exit).
- Availability of a compute environment able to produce authoritative timings.

## 17. Conditions to start a private testnet

Per `docs/PQ_TESTNET_PLAN_V3.md`: an **isolated, experimental, OFF-by-default**
testnet build, fully separated from mainnet, entered only after the specification
and prototype have had public review. A testnet is **not** started by this PR.

## 18. Conditions to propose a future activation

All of, in order (Phases C–F of `docs/PQ_ACTIVATION_PLAN_V3.md`): completed and
resolved **external audit**; defined and adopted minimum node/wallet versions;
sustained version-signalling; and a **separate, reviewed, audited proposal** that
alone chooses a real height. None of this is in scope here.

## 19. PR #37 and PR #38 history

- **PR #37** (`draft/pq-migration-v2`) — V2 architecture + benchmark harness.
  **CLOSED, not merged.** Its branch is preserved for history; some V2-only
  document references resolve on that branch by design.
- **PR #38** (`draft/pq-migration-v3-docsync`) — V3 consolidation: architecture,
  whitepaper-as-code tree, ADRs, isolated prototype, tests/vectors/fuzz,
  benchmark harness, external-audit hand-off package, and this master index.
  **OPEN, DRAFT, not merged, not deployed.** V3 supersedes V2.

## 20. Confirmation: mainnet stays on ECDSA

Mainnet transaction spending remains **ECDSA over secp256k1 with canonical
LOW-S**. BIP-340 Schnorr remains SbPoW block-identity only. No post-quantum scheme
is active, scheduled, or merged. `PQ_ACTIVATION_HEIGHT = INT64_MAX`. Any change to
this would be a separate, reviewed, audited consensus proposal — not this PR.

---

*Author: NeoB. Research / architecture / prototype only. Not merged, not deployed,
not audited, not active. This document does not claim SOST is post-quantum or
quantum-resistant.*
