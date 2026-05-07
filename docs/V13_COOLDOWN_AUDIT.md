# V13 lottery cooldown audit — Monte Carlo aggregate sweep

This audit documents the quantitative analysis behind any change to
`LOTTERY_RECENT_WINNER_EXCLUSION_WINDOW` for the V13 fork. The proposed
bump is `5 → 6`. The C9 audit (`tools/lottery_montecarlo.py`) selected
`5` from a sweep over windows ∈ {0, 5, 10, 30}; this re-runs the same
simulation core restricted to candidate windows ∈ {5, 6, 7}.

This file ships the **aggregate-metric sweep** only. A
structural-alignment review of the cooldown's interaction with the
1-of-3 / 2-of-3 lottery cadence is a separate consideration the
aggregates cannot capture; that review is added in a follow-up commit
and the final V13 verdict is deferred until both inputs are on the
table.

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

This is **one input** to the V13 decision. The audit explicitly does
NOT close on it: see the follow-up commit for the structural-alignment
analysis, which addresses a property the aggregates cannot measure
(deterministic vs alignment-fuzzy exclusion against the 1-of-3 lottery
cadence in the permanent phase).

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
