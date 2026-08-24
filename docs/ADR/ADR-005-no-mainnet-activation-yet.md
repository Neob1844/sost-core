# ADR-005 — No post-quantum activation on mainnet

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

The V3 PQ workstream defines a crypto-agility registry (ADR-001), an AND-hybrid
scheme (ADR-002), a versioned variable-length witness (ADR-003), and a library
isolation rule (ADR-004). None of these should give the impression that SOST is
"quantum-safe" or that ML-DSA is live. SOST spend authorisation on mainnet is
**ECDSA secp256k1 with canonical LOW-S** and nothing else (README.md:196;
src/tx_signer.cpp). It is essential that this research cannot silently or
accidentally become a consensus rule.

## Decision

**There is no post-quantum activation on mainnet.** The PQ path is gated inert
by design:

1. **INT64_MAX sentinel.** `PQ_ACTIVATION_HEIGHT = INT64_MAX` — the codebase's
   established "never active" pattern, the same sentinel used by
   `POPC_V15_ACTIVATION_HEIGHT` and `atomic_swap_htlc_active_at`. No block height
   ever reaches INT64_MAX, so no PQ validation path is ever entered on mainnet.
2. **Not compiled into the node.** The prototype is not built into the shipped
   node; PQ witness validation is not on any reachable mainnet code path (and no
   PQ library is a build dependency — ADR-004).
3. **Flag defaults OFF and is insufficient alone.** The
   `SOST_EXPERIMENTAL_PQ_TESTNET_ONLY` flag defaults **OFF** and, even when on,
   is **not sufficient by itself to change consensus** — it scopes experimentation
   to testnet/prototype and does not lower the INT64_MAX gate.

**No fixed activation date and no activation height** are set or implied. Any
future rollout is described only in phase labels (Phase A, B, C…) and conditions,
never calendar dates or block heights.

**Activation is a separate, future consensus proposal — not this PR.** Turning
on any alg_id beyond `0x00` (LEGACY_ECDSA) would require a distinct, reviewed,
community-coordinated consensus change with its own proposal, testing, and
activation mechanism. Nothing in the V3 documents constitutes that proposal.

## Alternatives considered

1. **Set a tentative activation height or date now.** Rejected: violates the
   "no invented heights/dates" rule, would misrepresent readiness, and would turn
   research into a de-facto consensus commitment before audit/interop work exists.
2. **Enable the experimental flag by default on testnet.** Rejected for this PR:
   default-OFF is the safe posture; enabling is a deliberate, separate operator
   decision scoped to non-mainnet experimentation.
3. **Ship the prototype compiled but gated only by a runtime check.** Rejected:
   defence in depth is preferred — not compiled into the node **and** INT64_MAX
   gate **and** default-OFF flag, so no single lapse can activate PQ.

## Pros

- Multiple independent guards (not compiled, INT64_MAX gate, default-OFF flag)
  make accidental activation effectively impossible.
- Uses an established, well-understood sentinel already proven in this codebase.
- Keeps public claims honest: research/prototype only, nothing active.

## Risks

- Communication risk: readers may over-read the ADRs as "SOST is quantum-safe."
  Mitigated by the status box on every document and explicit language here.
- Discipline risk: the guards must not be quietly loosened without a real
  activation proposal and review.

## Consensus impact

**NONE — research only, activates nothing.** By construction: INT64_MAX gate +
not compiled into the node + default-OFF experimental flag. Activation would be
a separate future consensus proposal, explicitly **not** this PR.

## Notes

- SOST is **not** described as "quantum-safe" or "post-quantum secure"; ML-DSA is
  **not** active. These ADRs are architecture/research.
- Related: ADR-001..004 (the design being gated), ADR-006 (docs kept honest and
  in sync), ADR-007 (wallet migration is likewise opt-in and non-forced).
- Prior iteration: docs/PQ_MIGRATION_V2.md (PR #37), superseded by V3.
