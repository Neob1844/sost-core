# V13 lottery cooldown audit — Monte Carlo aggregate sweep

This audit documents the quantitative analysis behind any change to
`LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` for the V13 fork. The proposed
bump is `5 → 6`. The C9 audit (`tools/lottery_montecarlo.py`) selected
`5` from a sweep over windows ∈ {0, 5, 10, 30}; this re-runs the same
simulation core restricted to candidate windows ∈ {5, 6, 7}.

**TL;DR — Bump `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` from 5 to 6
at `V13_HEIGHT = 12000`.** The aggregate Monte Carlo sweep is a wash
(small uniform regression on most axes); the bump is justified by the
structural-alignment property documented below. This audit is the
explicit record of that trade-off. The aggregate caveat is NOT hidden:
the operator chose determinism / clean rule alignment over micro-level
aggregate optimisation. That choice must remain visible in this file
for as long as `V13_HEIGHT` does.

## What was tested

`tools/sim/lottery_cooldown_v13.py` re-uses the C9 `simulate()` core from
`tools/lottery_montecarlo.py`. No second copy of the simulation logic
exists, so any invariant the C9 audit verified holds here too. The
script sweeps:

| axis | values |
|---|---|
| dominant hashrate | 0.50, 0.70, 0.85, 0.92 |
| honest miners | 5, 10, 35, 100 |
| sybil addresses | 0, 5, 10, 100 |
| **exclusion window** | **5, 6, 7** |
| blocks per scenario | 50 000 |
| seed | `0xC0FFEE` |
| frequency mode | `lifecycle` (5 000 hf phase + permanent thereafter) |

192 scenarios per run; full per-scenario data in
`tools/sim/artefacts/v13_cooldown_50k.json` (178 KB, reproducible from
the script + seed).

## Findings

### Per-window aggregates (means across the 64 scenarios per window)

| window | rollover (max) | dom_total_share (mean) | honest_worst (mean) | sybil_delta (mean) | double_win (mean) |
|-------:|---------------:|-----------------------:|--------------------:|-------------------:|------------------:|
| 5      | 0.006 %        | 43.76 %                | 1.818 %             | 8.903 %            | 1.138 %           |
| 6      | 0.136 %        | 43.80 %                | 1.814 %             | 8.994 %            | 1.104 %           |
| 7      | 0.460 %        | 43.85 %                | 1.808 %             | 9.066 %            | 1.083 %           |

### Pairwise deltas (50 k blocks, seed 0xC0FFEE)

| pair | dom_share | sybil_delta | honest_worst | rollover | double_win |
|------|----------:|------------:|-------------:|---------:|-----------:|
| 5→6  | +0.036 % (worse) | +0.091 %  (worse) | −0.004 % (worse) | +0.130 pp (worse) | −0.034 % (better) |
| 6→7  | +0.052 % (worse) | +0.072 %  (worse) | −0.006 % (worse) | +0.324 pp (worse) | −0.021 % (better) |
| 5→7  | +0.088 % (worse) | +0.163 %  (worse) | −0.010 % (worse) | +0.454 pp (worse) | −0.055 % (better) |

### Direction is consistent across seeds

Spot-checked at 20 000 blocks for seeds {1, 2, 3}:

| seed | dom (5) | dom (6) | dom (7) | sign |
|------|--------:|--------:|--------:|------|
| 1    | 44.89 % | 44.94 % | 45.00 % | 5 < 6 < 7 |
| 2    | 44.85 % | 44.92 % | 44.97 % | 5 < 6 < 7 |
| 3    | 44.90 % | 44.97 % | 45.03 % | 5 < 6 < 7 |

The direction is monotonic in every seed — not a `0xC0FFEE` artefact.

## Why bigger windows are slightly worse in aggregate

The C7.1 lottery model treats the dominant operator as a single PoW
identity (`dom_main`) plus a set of pre-legitimated sybil addresses
without history. Mechanism:

1. With dominant hashrate ≥ 0.50, `dom_main` wins ~50 %+ of recent blocks.
   Any cooldown window ≥ 5 already excludes `dom_main` ~all the time.
2. The dominant's sybil addresses never themselves win blocks (the
   simulator credits everything to `dom_main`), so they are NEVER in the
   cooldown set regardless of window size.
3. Honest miners only enter the eligibility set after winning their first
   block. Once eligible, a recent honest winner DOES go into cooldown.
4. Bumping the window from 5 → 6 → 7 catches **more honest recent winners**
   while leaving the dominant's sybil pool intact. The dominant's lottery
   share rises a tiny but consistent amount.

In short: under the C9 model, the cooldown's bite falls disproportionately
on honest recent winners as the window grows. The dominant gets a
relative gain, not a loss — in the aggregates.

## Aggregate-metric reading

On the aggregate metrics alone, the data does not indicate a bump from
5 to 6. The deltas are small (~0.05 % shift in dominant share for a 5→6
bump), small enough that they may be operationally negligible, but the
direction is unambiguous.

This is **one input** to the V13 decision. It is not the load-bearing
argument; the structural-alignment analysis below is.

## Structural-alignment finding

The aggregate sweep measures *outcomes*. It does not measure the
*structural property* the cooldown is meant to provide: how many
consecutive lottery firings is a recent block miner guaranteed to be
excluded from?

Lottery firings happen at a fixed cadence depending on phase:

- High-frequency phase (first 5 000 blocks of Phase 2): 2 of every 3 blocks
- Permanent phase (rest of the chain's lifetime): 1 of every 3 blocks

When a miner mines a block at height `H`, the cooldown excludes them
from lottery participation at heights `[H+1, H+window]`. The number of
lottery *firings* inside that exclusion range depends on `H mod 3` AND
on the window:

### Permanent phase (1-of-3 lottery firings)

| `H mod 3` | window=5 — firings excluded | window=6 — firings excluded |
|----------:|----------------------------:|----------------------------:|
| 0         | 1 (H+3 only)                | 2 (H+3, H+6)                |
| 1         | 2 (H+2, H+5)                | 2 (H+2, H+5)                |
| 2         | 2 (H+1, H+4)                | 2 (H+1, H+4)                |
| **mean**  | **1.67**                    | **2.00**                    |

### High-frequency phase (2-of-3 firings)

| `H mod 3` | window=5 — firings excluded | window=6 — firings excluded |
|----------:|----------------------------:|----------------------------:|
| 0         | 4                           | 4                           |
| 1         | 3                           | 4                           |
| 2         | 3                           | 4                           |
| **mean**  | **3.33**                    | **4.00**                    |

`window=6` provides a **deterministic exclusion guarantee** in both
phases: every recently-mining miner is excluded from *exactly* 2
permanent-phase rounds (or 4 high-frequency rounds), with no
dependence on `H mod 3`.

`window=5` is alignment-fuzzy: a recent miner who happens to win a
block at `H ≡ 0 (mod 3)` during the long permanent phase is excluded
from only **1** lottery firing — not 2. That edge case is exactly the
kind of regularity gap the cooldown parameter is supposed to close.

The structural property does NOT show up clearly in the aggregates
because:

1. The dominant credits a single address (`dom_main`) and is
   cooldown-saturated under any window ≥ 5. Bumping the window catches
   no additional dominant share — the dominant is already maximally
   excluded.
2. Honest miners are rarely in cooldown at all (they win blocks
   infrequently relative to the window length); the alignment-fuzz
   only affects them in a 1/3 minority of their already-rare wins.
3. The double-win rate moves slightly in `6`'s favour (~0.034 % less),
   which is the visible-in-aggregate shadow of the structural
   property.

## Verdict

**Bump `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` from 5 to 6 at
`V13_HEIGHT = 12000`.**

Rationale:

- `window=6` is the smallest window that provides a deterministic
  2-firing exclusion in the permanent phase, and a deterministic
  4-firing exclusion in the high-frequency phase. The cooldown
  becomes a *clean rule* instead of a fuzzy one.
- The aggregate Monte Carlo sweep does not improve in `6`'s favour —
  on most axes it slightly regresses (~0.05 % dom_share, ~0.09 %
  sybil_delta, similar magnitudes for honest_worst and rollover_max).
  The magnitudes are small but the direction is unambiguous.
- The fork accepts that aggregate cost as the price of the structural
  guarantee. The cooldown rule's *intent* — reliable rotation against
  recent winners — is better served by the deterministic form.

Caveat (preserved on the record):

> The bump is **not** an outcome optimisation. The aggregate metrics
> point the other way. The decision is a deliberate trade of small
> aggregate regression for clean structural alignment.

If a future review concludes that aggregate fairness should win, this
audit is also the file that documents how to reverse the decision —
revert to `5` and re-run the sweep with the same `seed = 0xC0FFEE` for
direct comparability.

## V13 plan impact

V13 fork scope (all changes gated at `V13_HEIGHT = 12000`):

- `LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW`  5 → 6
- `MAX_FUTURE_DRIFT_STAGED`                 60 s → 30 s
- Beacon Phase II-A activation
- Phase III P2P scaffold remains DISABLED-by-default (`INT64_MAX` gate)

## Caveats

The C9 model has documented assumptions worth recalling:

- **Dominant credits one address.** Real operators may rotate addresses
  to avoid cooldown. The cooldown's value to honest miners is highest
  *exactly* when the dominant doesn't rotate.
- **Sybils are pre-legitimated at genesis.** Real sybils need to mine ≥ 1
  block first. This biases the model pessimistically (sybils more
  effective than reality) — a smaller sybil delta in practice.
- **Hashrate is constant.** Real networks have churn; cooldown effects
  on a churning miner population are not modelled.
- **Lottery winner pick is uniform over the eligible set.** Production
  uses a deterministic SHA-256 RNG over a height-tagged seed; uniformity
  is preserved but the tail behaviour is not identical.

None of these caveats reverse the direction of the aggregate result.

## Reproduce

```bash
python3 tools/sim/lottery_cooldown_v13.py \
    --blocks 50000 \
    --seed 0xC0FFEE \
    --json tools/sim/artefacts/v13_cooldown_50k.json
```

Runtime: ~60 s on a 2024 laptop. Re-run with different `--seed` values
to confirm direction stability.
