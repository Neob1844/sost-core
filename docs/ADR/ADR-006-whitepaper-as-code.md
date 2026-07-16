# ADR-006 — Whitepaper-as-code: canonical docs tree with CI sync checks

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

Cryptographic claims about SOST live in many surfaces: the whitepaper, README,
the website, and various announcement texts. These drift. A concrete example of
drift already in the tree: narrative docs still reference "SPHINCS+/Dilithium"
and a 2027 liboqs phase (docs/btctalk_ann*.txt, docs/convergencex_whitepaper.txt),
and the inert placeholder proposal label still says "SPHINCS+/Dilithium"
(include/sost/proposals.h:44) rather than the correct standardised terminology
(ML-DSA, FIPS 204; SLH-DSA, FIPS 205). Drift in crypto claims is dangerous: it
can imply capabilities SOST does not have (e.g. "quantum-safe") or misname
schemes. Documentation about consensus-adjacent facts should be governed with
the same rigour as code.

## Decision

Treat the whitepaper and docs **as code**:

1. **Canonical content tree: `docs/whitepaper/`.** The single source of truth for
   whitepaper content, versioned in the repo like source.
2. **A manifest** enumerating the canonical documents and the downstream surfaces
   (README, website) that must mirror specific sections/claims.
3. **A sync-check script: `scripts/check_whitepaper_sync.py`.** Verifies that
   downstream surfaces (README, website) are in sync with the canonical tree per
   the manifest; drift fails the check.
4. **A crypto-claims linter: `scripts/check_crypto_claims.py`.** Flags forbidden
   or incorrect crypto assertions — e.g. claiming SOST is "quantum-safe" /
   "post-quantum secure," asserting ML-DSA is active, mislabelling schemes
   ("CRYSTALS-Dilithium" as a current name rather than the historical origin of
   ML-DSA), or confusing ML-KEM (a KEM) with a signature scheme.
5. **Run both in CI**, so a PR that introduces drift or an incorrect crypto claim
   fails before merge.

Downstream surfaces (README, website) are kept **in sync** with the canonical
tree; the canonical tree is authoritative.

## Alternatives considered

1. **Manual review only.** Rejected: drift already exists precisely because
   review is manual and inconsistent across surfaces.
2. **A generated single-source doc with no linter.** Rejected: sync alone does
   not catch a *wrong-but-consistent* claim (e.g. "quantum-safe" copied
   everywhere); the crypto-claims linter targets correctness, not just sameness.
3. **Store canonical docs outside the repo (wiki/CMS).** Rejected: loses
   version-control, PR review, and CI enforcement — the whole point of
   docs-as-code.

## Pros

- Crypto claims are checked mechanically in CI, reducing hype/inaccuracy risk.
- One authoritative source; downstream surfaces cannot silently diverge.
- Catches exactly the class of error the PQ workstream is most exposed to
  (over-claiming safety, mislabelling schemes).
- Cheap to extend the linter's forbidden-claim list as terminology settles.

## Risks

- A linter can produce false positives/negatives; its rule list needs
  maintenance as standards terminology evolves.
- Sync checks add CI surface that must itself be maintained and not become a
  rubber stamp.
- Canonicalising docs does not fix already-incorrect content — the existing
  "SPHINCS+/Dilithium" wordings still need a (behaviour-neutral) correction pass.

## Consensus impact

**NONE — documentation tooling only, activates nothing.** Scripts, manifests,
and CI checks touch no consensus code path and change no validation rule.

## Notes

- The behaviour-neutral rewording of include/sost/proposals.h:44 and the
  narrative docs (to ML-DSA / SLH-DSA terminology) is exactly the kind of change
  the crypto-claims linter would flag and guard going forward.
- Related: ADR-005 (honest "nothing is active" posture the linter enforces),
  ADR-007 (RPC/explorer labelling that must also stay accurate).
- Prior iteration: docs/PQ_MIGRATION_V2.md (PR #37), superseded by V3.
