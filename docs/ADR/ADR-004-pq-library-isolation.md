# ADR-004 — Isolate any PQ library behind a replaceable interface

```
IMPLEMENTATION STATUS
  Mainnet-active:        ECDSA secp256k1 + canonical LOW-S (spend); BIP-340 Schnorr (SbPoW block-identity only)
  Research-prototype:    ML-DSA (FIPS 204) witness format, crypto-agility registry, hybrid AND scheme
  Not active on mainnet: post-quantum transaction validation (no activation height, no date, not merged)
This document is research/architecture only. It changes no consensus rule and activates nothing.
```

- **Status:** Accepted-for-research
- **Date:** 2026-07-02
- **Author:** NeoB

## Context

Prototyping ML-DSA (FIPS 204) requires an implementation of the scheme.
Candidate sources include the NIST/standards reference implementation and
liboqs (Open Quantum Safe) for experimentation. Adding any such library to the
node is a significant decision: consensus-critical signature verification cannot
depend on an unaudited, fast-moving, or unpinned dependency. A verification
discrepancy between library versions or platforms would be a **consensus split**.

Current state: **no PQ cryptography library is a build dependency of this
repository.** liboqs is referenced only in narrative/marketing text
(docs/btctalk_ann*.txt, docs/convergencex_whitepaper.txt) as a *future* Phase-2
prototype intention; it is **not** wired into any CMake/build target — verified.
The mainnet crypto stack is libsecp256k1 (ECDSA spend; BIP-340 Schnorr for
SbPoW block-identity only, gated by `SOST_HAVE_SCHNORRSIG`,
src/sbpow.cpp:37-80).

## Decision

Any PQ implementation is placed **behind an abstract, replaceable interface**
(a signature-scheme abstraction keyed by the ADR-001 alg_id — e.g.
`verify(alg_id, msg, sig, pubkey)` / `sign(...)`), so the concrete backend
(NIST reference, liboqs, or a later audited implementation) can be swapped
without touching consensus-facing call sites.

**No PQ crypto dependency is added to the mainnet build in this PR.** A backend
may only be introduced after a **full review** covering, at minimum:

- **License** compatibility with SOST (MIT).
- **Maintenance** health and release cadence.
- **Audit** status of the implementation.
- **Version pinning** (exact, reproducible).
- **API** stability.
- **Side-channel** resistance (constant-time behaviour where required).
- **Reproducibility** of builds across the release toolchain.
- **Platform** coverage (all supported node/miner platforms).
- **Supply-chain** integrity (source provenance, checksums).

Prefer the NIST reference implementation for correctness/known-answer testing
and liboqs for experimentation; treat both as *experimental backends behind the
interface*, not as mainnet dependencies.

## Alternatives considered

1. **Call a PQ library directly from consensus code.** Rejected: couples
   consensus-critical verification to one library's API and version, making a
   later swap a consensus-touching change and concentrating supply-chain and
   side-channel risk at the most sensitive layer.
2. **Vendor a single PQ implementation now and commit to it.** Rejected as
   premature: the review checklist above is not satisfied, and pinning a backend
   before audit/side-channel/reproducibility review would create risk with no
   activation benefit (nothing activates — ADR-005).
3. **No abstraction, add the library only at activation time.** Rejected:
   prototyping needs a stable seam now; the interface is free to define and lets
   experimentation proceed without a mainnet dependency.

## Pros

- The concrete PQ backend is swappable without editing consensus call sites.
- Mainnet build stays free of any unaudited PQ dependency.
- Forces an explicit, documented review gate before any dependency lands.
- Cleanly matches the alg_id dispatch model (ADR-001).

## Risks

- An abstraction can hide backend-specific pitfalls (e.g. serialization or
  constant-time differences) if the interface is under-specified — the interface
  contract must pin encoding and exact sizes (see ADR-003).
- Known-answer/interop testing across backends is essential before trusting any
  one of them; divergence between backends is a consensus hazard.
- Discipline risk: the "no mainnet dependency" rule must hold until the full
  review is genuinely complete, not merely started.

## Consensus impact

**NONE — research only, activates nothing.** No library is added to the mainnet
build in this PR; no consensus code path invokes a PQ backend. `PQ_ACTIVATION_HEIGHT
= INT64_MAX`. Introducing and activating any backend would be a separate future
consensus proposal (ADR-005).

## Notes

- Verified: liboqs is not a build dependency; it appears only in narrative docs
  (docs/btctalk_ann*.txt, docs/convergencex_whitepaper.txt) as a stated future
  intention.
- ML-KEM (FIPS 203) is a KEM, not a signature scheme; SLH-DSA (FIPS 205) is a
  hash-based backup with parameter-set-dependent sizes — either would be a
  distinct backend behind the same interface, not automatic replacements.
- Related: ADR-001 (alg_id dispatch), ADR-003 (encoding/size contract),
  ADR-005 (no activation). Prior iteration: docs/PQ_MIGRATION_V2.md (PR #37).
