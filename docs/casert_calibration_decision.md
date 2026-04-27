# cASERT Calibration Decision — 2026-04-27

**Decision:** No consensus fork. cASERT remains as currently deployed.

## Summary

A potential hard fork at block 6210 was considered to tighten the
avg288 dynamic-cap dead-band from ±15s to ±5s. After empirical analysis
of real chain data (6,193 blocks, 42.9 days of mainnet), the change was
**rejected**. The current configuration is already well calibrated to
the network's natural noise profile.

## Configuration retained (unchanged)

- avg288 window: **288 blocks** (~48 hours).
- Dynamic-cap dead-band: **±15s** (no adjustment when `|avg288 − 600| ≤ 15s`).
- Adjustment brackets outside the dead-band:
  - `(15s, 60s]`  → 0.5% per block cap
  - `(60s, 120s]` → 1.0% per block cap
  - `(120s, 240s]` → 2.0% per block cap
  - `>240s`       → ~3.0% per block cap
- Source of truth: `src/pow/casert.cpp:103-148`.

## What was considered

| Setting | Effect (real chain data) |
|---|---|
| ±15s (current) | adj_freq 22%, bitsQ_std 10.8%, no hunting |
| ±10s | adj_freq 30%, bitsQ_std 15.8% |
| ±5s | adj_freq 46%, bitsQ_std 18.1%, more nervous |

Source: simulator replicating the avg288 dynamic-cap logic over real
chain data from `https://sostcore.com/bootstrap-chain.json`.

## Why no fork

1. **Current ±15s is already calibrated to network noise.** With ~22
   miners and ~1.8 K hashes/sec, avg288 oscillates naturally inside
   ±15s most of the time. The current rule produces a moderate ~22%
   adjustment frequency — neither dormant nor nervous.

2. **±5s is too aggressive for the current network size.** It would
   convert natural Poisson noise on avg288 into constant bitsQ
   corrections, increasing volatility (~1.7× higher bitsQ standard
   deviation) without measurable benefit.

3. **±10s is theoretically defensible but not necessary.** The
   improvement over ±15s is small in real data (adj_freq 22% → 30%,
   bitsQ_std 10.8% → 15.8%), and a hard fork is not justified by a
   marginal calibration delta.

4. **avg288 → avg600 / avg1000 was not on the table for consensus**;
   it was a UI request only. Larger windows make the system slower to
   react, which goes opposite to the stated goal of "more responsive
   bitsQ". They have been added as visual / informational metrics only.

## What was added (UI only, not consensus)

The explorer dashboard now shows three averages side-by-side:

- **AVG BLOCK TIME (288)** — blue, consensus-relevant.
- **LONG AVG · 600** — yellow, informational only.
- **LONG AVG · 1000** — red, informational only.

All three share the same pulse animation (intensity proportional to
proximity to 600s target, color follows the 540-660s healthy band).
Card text colors are fixed per metric.

The `LONG AVG` cards are explicitly labelled as visual / informational.
Their card tooltips state: *"Not used by consensus. avg288 is the
consensus-relevant average."*

## Anti-goals (will not happen as a result of this decision)

- No change to `BITSQ_AVG288_WINDOW` (stays at 288).
- No change to `casert_next_bitsq()` brackets or thresholds.
- No new fork height in `params.h`.
- No mandatory upgrade announcement.
- No retroactive change to past blocks.

## When this could be revisited

A future calibration may revisit the dead-band (e.g. ±10s) only if real
production data shows that bitsQ adapts too late to genuine hashrate
shifts. Triggers worth watching:

- Sustained avg288 drift outside `[570s, 630s]` for multiple weeks.
- Repeated failures of the system to absorb miners entering/leaving
  without long stalls.
- Network growth past ~100 miners where Poisson noise on avg288 falls
  below ±5s (at which point ±5s would no longer cause hunting).

If any of those happen, the proposal can be re-evaluated with fresh
empirical data and a new decision document. Until then, no change.

## Author

NeoB — 2026-04-27.
