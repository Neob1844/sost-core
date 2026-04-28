# Post-fork GPU / pool resistance — research notes

**Date:** 2026-04-28
**Author:** NeoB
**Status:** documentation only. No implementation in consensus.

This document captures **what was decided NOT to implement** in the
block 6400 MTP fork, and what could be considered for a separate,
properly engineered future fork. It exists so the discussion is on the
public record and so future work has a starting point.

## Why not in fork 6400

The block 6400 fork is **surgical**: it wires `ValidateBlockHeaderContextWithMTP`
into the node accept path, full stop. Mixing it with PoW redesign,
miner-identity binding, or anti-pool mechanisms would have:

- expanded review surface and risk of subtle bugs
- delayed activation past the small-network window where coordinated
  upgrade is feasible
- conflated a clear timestamp policy fix with deeper protocol changes
  that need separate research and audit

The MTP fix is fork-gated, narrow, and reversible in a future fork if
it interacts badly with anything else.

## Current status (verified 2026-04-28)

- **No PoW bypass.** Audit of `verify_stability_basin` and
  `convergencex_attempt` (commit `1755769`) shows the consensus path
  is intact. Blocks produced are valid by current rules.
- **Mining distribution is healthy** for a small network: 23 unique
  addresses over the last 288 blocks; top miner ~13-15 %; top 3 ~38 %;
  top 10 ~78 %.
- **The reference miner is CPU-oriented**, but protocol-level GPU
  resistance is **not** fully proven. The algorithm is parallelisable
  enough (k-loop independence, 32×32 matvec, branch-free perturbations)
  that a competent GPU port is plausible.
- **No evidence of pooling** at the address level. Different miners
  win different blocks, including the post-E7 fast blocks that the
  MTP fix is partly motivated by.

## What could be done later — design options (NOT implemented)

### A. ConvergenceX v3 — latency-bound mode

**Idea:** strengthen sequential memory dependencies in the inner loop
so that each round depends on the previous round's output via a chain
of pointer-chasing reads that cannot be pipelined.

Specific levers:

- Replace some independent matvec rounds with rounds whose addresses
  depend on the previous round's hash output (pointer chasing).
- Tighten the round-to-scratchpad coupling so SIMT doesn't help —
  each thread spends time waiting on its own memory.
- Keep verifier cost bounded so a node can still validate a block
  cheaply (asymmetric mining vs. verification).

Risk: making mining slower for everyone, including honest CPU miners.
Needs careful tuning.

### B. Signature-bound PoW / miner-address-bound challenge

**Idea:** include the miner's payout address (or a signature) in the
PoW seed so that the work cannot be pooled without sharing the payout
key.

Specific shapes:

- `seed = sha256(prev || timestamp || coinbase_pkh || ...)` already
  includes coinbase. Strengthen the binding so a pool operator can't
  trivially substitute the payout address after the fact.
- Non-outsourceable mining: research direction (Miller et al.,
  Bonneau et al.). Requires the miner to prove possession of the
  signing key for the payout address as part of the block.

Risk: breaks legitimate setups where a payout address is held in cold
storage and mining happens on a separate machine. Custody patterns
must be considered.

### C. Useful Compute as dilution of raw hashrate

**Idea:** when Useful Compute rewards eventually activate (postponed,
per `feedback_useful_compute`), they make raw hashrate less dominant.
A miner with a GPU rig but no useful compute capability earns less per
unit of energy than a miner combining CPU mining with verified
scientific work.

This is **not consensus**. It is the existing reward design, with the
understanding that activating Useful Compute is itself a separate
project with its own readiness criteria.

## What we should monitor (no consensus, just observation)

These can be added to the explorer or to a script over the coming
weeks to give us data instead of speculation:

- Top miner share over rolling windows (24 h / 7 d / 30 d).
- Top 3 share, top 10 share.
- Consecutive blocks by the same address.
- Sub-60 s blocks per miner.
- Timestamp anomalies (post-fork: deltas at the MTP boundary).
- Estimated per-miner hashrate (Bitcoin-style).
- Effective per-miner attempts/sec (profile-adjusted) where possible.
- Sudden dominance alerts (e.g. top miner crossing 30 % over a
  rolling window).

The dual-metric explorer hashrate (commit `a4f094c`) already gives a
foundation for this.

## Decision rule for any future PoW change

A future change to the PoW algorithm or to miner-identity binding
must satisfy **all** of these before going live:

1. Activation height set in the future, far enough in advance.
2. Tests under existing CI suite.
3. Independent code review (or at least a second pair of eyes).
4. Public testnet deployment with at least one full epoch of data.
5. Bitcointalk announcement with mandatory-update banner.
6. No supply, reward or coinbase change unless explicitly intended.

Anything that fails one of these is **not ready for mainnet**.

## What this document is not

- Not a commitment to implement A, B or C.
- Not a recommendation to introduce miner-identity binding before
  the trial.
- Not a justification to modify ConvergenceX in a hurry.
- Not a public statement. Internal research notes only until we have
  data and a concrete plan.

## Cross-references

- `docs/fast_block_investigation_6200_6310.md` — the investigation
  that led to fork 6400.
- `docs/timestamp_mtp_fork_6400.md` — the MTP fork spec.
- `docs/pending_post_trial.md` — broader post-trial roadmap.
