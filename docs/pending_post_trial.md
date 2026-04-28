# Post-Trial Roadmap

Items intentionally deferred until **after** the Useful Compute trial
(ETA block 7000, ~2026-05-03). Listed here so they don't leak into
trial-week scope and so they don't get forgotten.

## GPU resistance — major

**Status:** ConvergenceX is parallelizable enough to be ported to GPU
even though the reference miner is CPU-only and the whitepaper claims
"CPU-only". Audit on 2026-04-28 confirmed:

- `verify_stability_basin` (`src/pow/convergencex.cpp:186-227`): 8
  outer iterations are independent → SIMT-friendly.
- `matvec_A` 32x32 (`:117-129`): pure data-parallel.
- `derive_perturbation`, `one_gradient_step`: deterministic, branch-free.
- No PoW bypass found. Asymmetry across miners is hardware/optimisation,
  not cheating.

**Fix idea (not before trial):** RandomX-style mixing — sequence
dependency between rounds, latency-bound memory ops, plus operations
chosen to defeat GPU pipelining. Estimate: 2-3 months engineering + 1
month independent audit + 1 month testnet + coordinated fork.

**Marketing alignment:** soften "CPU-only" wording to "CPU-friendly,
memory-hard PoW" in the next whitepaper revision.

## Second cache — minor

Mainnet `sost-miner` rebuilds `g_cx_dataset` (4 GB) on every tip change.
Same pattern we cached for the scratchpad in commit `90f4e34`. Same
optimisation applies, but it requires changing the API of
`convergencex_attempt` because the dataset is currently accessed as a
global. Not urgent: per-miner optimisation only, no consensus impact.

## Header commitment / anti-precompute

If a future fork wants to formally prevent miners from hashing on a
guessed `prev_hash` before propagation, add a commit field that pins
the header to a value only resolvable after the parent block is
finalised. Independent of GPU resistance work.

## Mining distribution monitor

Add an explorer panel that surfaces sustained concentration trends
(top 1, top 3, top 10 over 24h / 7d / 30d). Useful for community
visibility and for our own anomaly detection. Cosmetic, no consensus.

## Explorer odds and ends

- `mining_time` field in block detail page is interval between
  publications, not actual search time. Renaming or clarifying the
  tooltip avoids confusion.
- Block-level `Hashrate: X H/s` derived from `nonce/interval` is also
  misleading (nonce is the winning index, not the count of attempts).
  Same renaming/tooltip applies.

## What is NOT on this list

- Useful Compute reward activation. That stays paused per the
  rewards-postponed memory.
- Anything that requires a hard fork during trial week. Hard nope.
