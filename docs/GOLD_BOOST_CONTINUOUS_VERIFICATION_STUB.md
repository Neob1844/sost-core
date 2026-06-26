# Gold Boost Continuous Verification Pipeline — Design Stub

Status: **DESIGN STUB — not implemented.** This is a one-page sketch, not a spec. No code here.
Companion to PR #9 / `docs/POPC_SINGLE_MODEL_DRAFT.md`. The Gold Boost stays `INT64_MAX` on mainnet
until this pipeline exists and is soaked.

## Objective

Define how a future auditor/indexer feeds `commitment.gold_verified_days` **without SOST consensus
depending on Ethereum directly**. Gold verification is an *upside-only* signal: it can grant or deny
a boost, never slash, seize, or affect consensus safety.

## What already exists (in code)

- `PoPCCommitment.gold_verified_days` — proven day count, **default 0**, serialized. The boost reads
  ONLY this; a registration snapshot never counts.
- `popc_continuous_verified_days(first_verified_height, last_verified_height, min_gold_observed_mg,
  required_mg, blocks_per_day)` — the pure INTERFACE the pipeline calls. Strict continuity: any dip
  below `required_mg` over the span → `0`.

The pipeline's whole job is to produce honest inputs for that function and write the result back.

## The loop (Phase 2 — attestation, OFF-consensus)

```
1. Schedule         deterministic audit checkpoints from ConvergenceX block entropy
                    (reuse the §6.3 audit schedule; no party picks the times).
2. Observe          at each checkpoint an auditor/indexer reads Ethereum:
                      - ecrecover proves control of the declared EOA (extcodesize==0)
                      - balanceOf(XAUT/PAXG) via multiple independent RPC endpoints
3. Track            per commitment: first_verified_height, last_verified_height,
                    min_gold_observed_mg  (the minimum across the span — the continuity test)
4. Attest           the auditor signs (commitment_id, checkpoint_height, balance_mg) — an
                    attestation, carried to nodes off the consensus root.
5. Recompute        gold_verified_days = popc_continuous_verified_days(...). Write to the commitment.
6. Settle           popc_complete already consumes gold_verified_days, surplus-aware, base-first.
```

## Non-negotiables

- **Consensus never queries Ethereum.** Nodes consume *attestations*, not live RPC. The boost is
  off the consensus root, so an attestation disagreement can only cost a boost — never a slash, never
  a fork.
- **Gold is never collateral and never slashable.** Verification failure / RPC outage → no boost,
  no penalty. The base reward is untouched.
- **Continuity is strict.** A dip below the eligibility threshold at any sampled checkpoint zeroes
  the credit (the function already enforces this).
- **Eligibility unchanged.** `required_mg` = `max(25% of bond value, 0.25 PAXG/XAUT)`; dust never
  qualifies.

## Open decisions (defer until build time)

- **Who attests:** single operator attester vs. a quorum/threshold of independent attesters.
  (More decentralized = more attesters; the boost being non-critical lowers the bar.)
- **Checkpoint cadence** and how many samples define "continuous".
- **Attestation carrier** (how it reaches nodes) + anti-replay / expiry.
- **`blocks_per_day`** constant to pass (≈144 at 10 min/block).

## End-state (Phase 3 — trustless)

Replace the trusted attester with **ZK state proofs** (whitepaper §6.14): the user proves
`balanceOf(XAUT/PAXG) >= required` at a given Ethereum block; SOST verifies the proof, no attester.
This is the preferred final form — an in-consensus Ethereum light client is explicitly NOT the goal.

## Activation gate

Only after this pipeline is built, attestations flow, and a testnet soak passes do we set
`POPC_GOLD_BOOST_HEIGHT` to a finite height. Until then it stays `INT64_MAX` and the boost is 0.
