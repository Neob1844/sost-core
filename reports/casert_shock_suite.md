# CASERT Shock Test Suite Results

## Question

Why does the SOST explorer show H9/H10 blocks cycling in a sawtooth
pattern (H10->H9->H6->H3->B0->H10) when the v5_simulator predicts
mostly B0/E profiles?

## Summary Table

| Scenario | H9+% | Sawtooth | B0% | LagMax |
|----------|-------|----------|-----|--------|
| S0: Simulator baseline (uniform, sim PID+diff) | 0.0% | 0.365 | 48.5% | +10 |
| S1: Concentrated (sim PID+diff, no shocks) | 0.0% | 0.363 | 49.1% | +7 |
| S2: Concentrated + realistic diff (sim PID) | 0.0% | 0.368 | 44.5% | +10 |
| S3: Real PID + sim diff (concentrated) | 0.1% | 0.230 | 69.8% | +2 |
| S4: Real PID + realistic diff (concentrated) | 1.3% | 0.248 | 72.2% | +3 |
| S5: Real PID + real diff + top miner drops 2h | 1.2% | 0.249 | 71.7% | +4 |
| S6: Real PID + real diff + top-2 drop 3h | 1.2% | 0.249 | 72.1% | +3 |
| S7: Real PID + real diff + staggered recovery | 1.1% | 0.250 | 71.3% | +3 |
| S8: Real PID + real diff + lag+20 (no shock) | 1.4% | 0.250 | 71.3% | +23 |
| S9: Real PID + real diff + lag+20 + shock | 1.4% | 0.251 | 70.5% | +23 |
| S10: Immediate-drop (real PID+diff, lag+20, shock) | 1.4% | 0.251 | 70.5% | +23 |

## Detailed Results

### S0: Simulator baseline (uniform, sim PID+diff)

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.0m, Median: 6.6m
- H9+ blocks: 0.0%
- Sawtooth: 0.365, Anti-stall: 9.4
- Max consec B0: 11.2, H9+: 0.0

| Profile | % |
|---------|---|
| E3 | 1.6% |
| E2 | 9.2% |
| E1 | 24.4% |
| B0 | 48.5% |
| H1 | 9.3% |
| H2 | 4.8% |
| H3 | 1.7% |
| H4 | 0.3% |

### S1: Concentrated (sim PID+diff, no shocks)

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.0m, Median: 6.5m
- H9+ blocks: 0.0%
- Sawtooth: 0.363, Anti-stall: 7.4
- Max consec B0: 10.0, H9+: 0.0

| Profile | % |
|---------|---|
| E4 | 0.2% |
| E3 | 1.8% |
| E2 | 9.1% |
| E1 | 25.7% |
| B0 | 49.1% |
| H1 | 8.3% |
| H2 | 4.2% |
| H3 | 1.3% |
| H4 | 0.2% |

### S2: Concentrated + realistic diff (sim PID)

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.0m, Median: 6.6m
- H9+ blocks: 0.0%
- Sawtooth: 0.368, Anti-stall: 3.4
- Max consec B0: 10.4, H9+: 0.0

| Profile | % |
|---------|---|
| E4 | 0.2% |
| E3 | 1.9% |
| E2 | 8.5% |
| E1 | 23.1% |
| B0 | 44.5% |
| H1 | 12.0% |
| H2 | 6.9% |
| H3 | 2.4% |
| H4 | 0.4% |

### S3: Real PID + sim diff (concentrated)

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.1m, Median: 5.8m
- H9+ blocks: 0.1%
- Sawtooth: 0.230, Anti-stall: 13.9
- Max consec B0: 27.0, H9+: 1.1

| Profile | % |
|---------|---|
| E4 | 5.4% |
| E3 | 16.6% |
| E2 | 3.9% |
| E1 | 1.5% |
| B0 | 69.8% |
| H3 | 1.8% |
| H6 | 0.7% |
| H9 | 0.1% |

### S4: Real PID + realistic diff (concentrated)

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.0m, Median: 6.3m
- H9+ blocks: 1.3%
- Sawtooth: 0.248, Anti-stall: 10.5
- Max consec B0: 23.9, H9+: 3.0

| Profile | % |
|---------|---|
| E4 | 2.5% |
| E3 | 15.9% |
| E2 | 1.1% |
| E1 | 2.1% |
| B0 | 72.2% |
| H3 | 3.1% |
| H6 | 1.7% |
| H9 | 0.9% |
| H10 | 0.3% |

### S5: Real PID + real diff + top miner drops 2h

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.0m, Median: 6.3m
- H9+ blocks: 1.2%
- Sawtooth: 0.249, Anti-stall: 10.3
- Max consec B0: 25.1, H9+: 3.2

| Profile | % |
|---------|---|
| E4 | 2.5% |
| E3 | 16.0% |
| E2 | 1.7% |
| E1 | 2.1% |
| B0 | 71.7% |
| H3 | 3.0% |
| H6 | 1.7% |
| H9 | 0.8% |
| H10 | 0.3% |

### S6: Real PID + real diff + top-2 drop 3h

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.0m, Median: 6.3m
- H9+ blocks: 1.2%
- Sawtooth: 0.249, Anti-stall: 10.8
- Max consec B0: 25.6, H9+: 3.5

| Profile | % |
|---------|---|
| E4 | 2.6% |
| E3 | 16.2% |
| E2 | 1.5% |
| E1 | 2.1% |
| B0 | 72.1% |
| H3 | 2.7% |
| H6 | 1.6% |
| H9 | 0.8% |
| H10 | 0.3% |

### S7: Real PID + real diff + staggered recovery

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.0m, Median: 6.3m
- H9+ blocks: 1.1%
- Sawtooth: 0.250, Anti-stall: 10.7
- Max consec B0: 26.0, H9+: 3.1

| Profile | % |
|---------|---|
| E4 | 2.6% |
| E3 | 15.9% |
| E2 | 2.2% |
| E1 | 2.1% |
| B0 | 71.3% |
| H3 | 3.0% |
| H6 | 1.7% |
| H9 | 0.8% |
| H10 | 0.2% |

### S8: Real PID + real diff + lag+20 (no shock)

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.1m, Median: 6.4m
- H9+ blocks: 1.4%
- Sawtooth: 0.250, Anti-stall: 11.8
- Max consec B0: 23.0, H9+: 3.7

| Profile | % |
|---------|---|
| E4 | 2.5% |
| E3 | 15.8% |
| E2 | 1.3% |
| E1 | 2.1% |
| B0 | 71.3% |
| H2 | 0.2% |
| H3 | 3.0% |
| H5 | 0.2% |
| H6 | 1.8% |
| H8 | 0.1% |
| H9 | 0.9% |
| H10 | 0.3% |

### S9: Real PID + real diff + lag+20 + shock

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.1m, Median: 6.3m
- H9+ blocks: 1.4%
- Sawtooth: 0.251, Anti-stall: 11.5
- Max consec B0: 24.3, H9+: 4.2

| Profile | % |
|---------|---|
| E4 | 2.5% |
| E3 | 15.9% |
| E2 | 2.2% |
| E1 | 2.0% |
| B0 | 70.5% |
| H2 | 0.2% |
| H3 | 2.9% |
| H5 | 0.2% |
| H6 | 1.8% |
| H8 | 0.1% |
| H9 | 0.9% |
| H10 | 0.4% |
| H11 | 0.1% |

### S10: Immediate-drop (real PID+diff, lag+20, shock)

- Blocks/run: 2000, Seeds: 10
- Mean interval: 10.1m, Median: 6.3m
- H9+ blocks: 1.4%
- Sawtooth: 0.251, Anti-stall: 11.5
- Max consec B0: 24.3, H9+: 4.2

| Profile | % |
|---------|---|
| E4 | 2.5% |
| E3 | 15.9% |
| E2 | 2.2% |
| E1 | 2.0% |
| B0 | 70.5% |
| H2 | 0.2% |
| H3 | 2.9% |
| H5 | 0.2% |
| H6 | 1.8% |
| H8 | 0.1% |
| H9 | 0.9% |
| H10 | 0.4% |
| H11 | 0.1% |

## Root Cause Analysis

The v5_simulator has **two compounding model errors** that explain
why it cannot reproduce the explorer's H9/H10 behavior:

### Bug 1: Wrong PID Coefficients (PRIMARY CAUSE)

The simulator uses a simplified PID:
```
H_raw = lag * 0.25 + burst_signal * 0.50
```

The real C++ casert.cpp (params.h) uses:
```
U = K_R * r + K_L * L + K_I * I + K_B * B + K_V * V
  = 0.05*r + 0.40*lag + 0.15*integrator + 0.05*burst + 0.02*vol
```

Key differences:
- **K_L (lag weight) = 0.40 in C++, 0.25 in simulator** -- 60% under-weighted
- **Integrator (K_I=0.15)** -- entirely missing from simulator. The
  integrator accumulates persistent lag over time with a 0.988 leak
  rate, amplifying the effect of sustained positive lag.
- **K_B (burst) = 0.05 in C++, 0.50 in simulator** -- 10x over-weighted,
  which compensates somewhat but creates wrong dynamics.

Effect: At lag=25 the simulator computes H_raw=6, the real PID computes
H_raw=10+. This single error is why the simulator never reaches H9/H10.

### Bug 2: Unrealistic Difficulty Multiplier at High Profiles

The simulator's block-time sampling uses:
```
effective_time = base_time * PROFILE_DIFFICULTY[p] / STAB_PCT[p]
```

This gives a 93x multiplier at H10. Real explorer data shows H10 blocks
average 15-25 minutes (2.5-4x target), not 930 minutes. The 93x penalty
creates artificially strong negative feedback that kills any profile
excursion.

### Evidence from the Suite

The transition from S0 to S4 isolates each factor:

- **S0: Simulator baseline (uniform, sim PID+diff)**: 0.0% H9+
- **S1: Concentrated (sim PID+diff, no shocks)**: 0.0% H9+
- **S2: Concentrated + realistic diff (sim PID)**: 0.0% H9+
- **S3: Real PID + sim diff (concentrated)**: 0.1% H9+
- **S4: Real PID + realistic diff (concentrated)**: 1.3% H9+
- **S5: Real PID + real diff + top miner drops 2h**: 1.2% H9+
- **S6: Real PID + real diff + top-2 drop 3h**: 1.2% H9+
- **S7: Real PID + real diff + staggered recovery**: 1.1% H9+
- **S8: Real PID + real diff + lag+20 (no shock)**: 1.4% H9+
- **S9: Real PID + real diff + lag+20 + shock**: 1.4% H9+
- **S10: Immediate-drop (real PID+diff, lag+20, shock)**: 1.4% H9+

With the real PID (S3+), profiles jump in slew-rate multiples of 3:
B0 -> H3 -> H6 -> H9 -> H10, with almost no H1/H2/H4/H5 -- exactly
the staircase pattern seen on the explorer.

### Why Concentration and Shocks Don't Matter (Much)

Hash concentration (Scenario S1 vs S0) has no effect because the
minimum of independent exponentials has the same distribution as a
single exponential with the combined rate (memoryless property).

Miner shocks (S5-S7 vs S4) have marginal effect because a single 2h
outage is a small perturbation over 2000 blocks. The sawtooth pattern
is primarily driven by the PID oscillation around lag=0, not by
miner availability changes.

## Recommendations

1. **Fix the PID in v5_simulator.py**: Replace the simplified
   `lag * 0.25 + burst * 0.50` with the actual C++ coefficients
   (K_L=0.40, K_I=0.15, K_B=0.05, K_R=0.05, K_V=0.02) and add
   the EWMA/integrator state tracking.

2. **Fix the difficulty model**: Replace PROFILE_DIFFICULTY/STAB_PCT
   with empirical effective multipliers from explorer data.

3. **Initialize with actual chain lag**: Query the explorer for the
   current lag value and use it as the starting condition.

