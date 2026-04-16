# CASERT PID Tuning Campaign Report

Generated: 2026-04-16 20:09:19

## Methodology

This campaign uses a FIXED simulator that implements the real 5-term PID
from `src/pow/casert.cpp`, replacing the simplified 2-term model in
`scripts/v5_simulator.py` (which used K_L=0.25, K_B=0.50 -- both wrong).

The real PID control signal is:
```
U = K_R*r + K_L*lag + K_I*I + K_B*burst + K_V*vol
```
where r = log2(target/dt), lag = height - expected_height,
I = leaky integrator of lag, burst = EWMA_short - EWMA_long,
vol = EWMA of |r - EWMA_short|.

## Composite Score Formula

```
score = -1.0 * target_error / 60
        -2.0 * std_dt / 600
        -3.0 * gt_40m / total_blocks * 100
        -1.5 * pct_H9plus / 100
        -1.0 * pct_E / 100
        -2.0 * robustness / 60
        -0.5 * sawtooth / total_blocks * 100
```
Higher = better. All terms are penalties.

## Baseline (current V5)

- **Params**: K_L=0.40, K_I=0.15, K_B=0.05, slew=3, I_leak=0.988
- **Score**: -15.139
- **Mean dt**: 603.9s (10.1m)
- **Std dt**: 1653.1s
- **>40min blocks**: 50.1
- **H9+ pct**: 0.17%
- **Sawtooth**: 61.2
- **Robustness**: 5.39s

## Key Finding 1: Which parameter moves the system most?

### slew_rate
- Score spread across values: **4.789**
- Best value: **1**
- Mean scores by value:
  - slew_rate=1: -10.324
  - slew_rate=2: -11.596
  - slew_rate=3: -15.113

### K_B
- Score spread across values: **1.394**
- Best value: **0.0**
- Mean scores by value:
  - K_B=0.0: -11.421
  - K_B=0.02: -12.815
  - K_B=0.05: -12.273
  - K_B=0.08: -12.626
  - K_B=0.1: -12.585

### K_I
- Score spread across values: **0.283**
- Best value: **0.2**
- Mean scores by value:
  - K_I=0.0: -12.396
  - K_I=0.05: -12.427
  - K_I=0.1: -12.371
  - K_I=0.15: -12.381
  - K_I=0.2: -12.144

### K_L
- Score spread across values: **0.048**
- Best value: **0.25**
- Mean scores by value:
  - K_L=0.25: -12.318
  - K_L=0.3: -12.363
  - K_L=0.35: -12.336
  - K_L=0.4: -12.339
  - K_L=0.45: -12.341
  - K_L=0.5: -12.366

**Answer: `slew_rate` has the largest influence** on composite score,
with a spread of 4.789 across tested values.

## Key Finding 2: Does slew_rate=1 help or hurt vs slew_rate=3?

| Metric | slew=1 | slew=2 | slew=3 |
|--------|--------|--------|--------|
| score | -10.57 | -12.06 | -15.14 |
| mean_dt | 601.94 | 602.63 | 603.91 |
| std_dt | 777.54 | 1156.07 | 1653.08 |
| gt_40m | 50.70 | 51.60 | 50.10 |
| sawtooth | 0 | 1.9 | 61.2 |
| robustness | 1.39 | 2.02 | 5.39 |

**Answer: slew_rate=1 HELPS.** Lower slew reduces oscillation and improves stability.

## Key Finding 3: Is there a safe zone or a sharp peak?

- Best score: -9.766
- Worst score: -17.925
- Score range: 8.159
- Configs within top 10% of range: 2276 / 2630

**Answer: PLATEAU.** Many configurations score similarly near the top.
This means the controller is robust to moderate parameter changes.

## Key Finding 4: Trade-off between smoothness and responsiveness

- Low K_L (<=0.30): avg std_dt=815.3s, avg target_error=2.7s
- High K_L (>=0.45): avg std_dt=796.5s, avg target_error=2.6s

Counterintuitively, higher K_L is BOTH more responsive AND smoother.
This suggests the lag correction prevents the chain from drifting into
difficult territory that causes high-variance block times.

## Key Finding 5: What K_I avoids integrator wind-up?

| K_I | Avg Score | Avg std_dt | Avg gt_40m | Avg sawtooth |
|-----|-----------|------------|------------|--------------|
| 0.00 | -11.135 | 873.0 | 40.9 | 3.6 |
| 0.01 | -10.318 | 730.0 | 50.3 | 0.0 |
| 0.02 | -10.313 | 729.7 | 50.3 | 0.0 |
| 0.03 | -10.291 | 729.8 | 50.2 | 0.0 |
| 0.04 | -10.282 | 729.9 | 50.1 | 0.0 |
| 0.05 | -11.107 | 876.8 | 40.6 | 3.8 |
| 0.06 | -10.282 | 729.9 | 50.1 | 0.0 |
| 0.07 | -10.282 | 729.9 | 50.1 | 0.0 |
| 0.10 | -12.371 | 1118.9 | 25.2 | 9.7 |
| 0.13 | -10.323 | 730.8 | 50.3 | 0.0 |
| 0.14 | -10.346 | 732.0 | 50.4 | 0.0 |
| 0.15 | -11.667 | 982.1 | 34.2 | 6.5 |
| 0.16 | -10.346 | 732.5 | 50.4 | 0.0 |
| 0.17 | -10.342 | 732.2 | 50.4 | 0.0 |
| 0.18 | -10.348 | 731.8 | 50.4 | 0.0 |
| 0.19 | -10.349 | 731.8 | 50.5 | 0.0 |
| 0.20 | -11.032 | 868.4 | 40.6 | 3.3 |
| 0.21 | -10.328 | 732.0 | 50.3 | 0.0 |
| 0.22 | -10.318 | 731.1 | 50.3 | 0.0 |


## Top 3 Candidates

### Candidate #1
- **Params**: K_L=0.430 K_I=0.130 K_B=0.000 slew=1 I_leak=0.980
- **Score**: -10.220
- **Mean dt**: 602.0s  Std: 731.4s
- **>40min**: 49.6  H9+: 0.00%
- **Risk**: MEDIUM (occasional >40min blocks)

### Candidate #2
- **Params**: K_L=0.440 K_I=0.130 K_B=0.000 slew=1 I_leak=0.980
- **Score**: -10.220
- **Mean dt**: 602.0s  Std: 731.4s
- **>40min**: 49.6  H9+: 0.00%
- **Risk**: MEDIUM (occasional >40min blocks)

### Candidate #3
- **Params**: K_L=0.450 K_I=0.130 K_B=0.000 slew=1 I_leak=0.980
- **Score**: -10.220
- **Mean dt**: 602.0s  Std: 731.4s
- **>40min**: 49.6  H9+: 0.00%
- **Risk**: MEDIUM (occasional >40min blocks)

## Key Question: Is the current baseline near-optimal?

- Baseline score: -15.139
- Best found:     -10.220
- Improvement:    +4.919 (+32.5%)

- Baseline ranks #2201 out of 2201 configs.

**There is CLEAR room for improvement.** The best config found is
significantly better (+32.5%). Retuning is recommended for V6.

## Recommendation: If you ship ONE change for V6

**Change `slew_rate` from 3 to 1.**

This is the single most influential parameter (spread=4.789).
The remaining parameters are already reasonable.

## Confidence Levels

- Phase 1 (coarse): 5 seeds x 1000 blocks = MODERATE confidence in ranking.
  Good for identifying promising regions, not for final decimal-place tuning.
- Phase 2 (fine): 10 seeds x 2000 blocks = GOOD confidence for top candidates.
  Statistical noise is reduced but not eliminated. Real-network behavior may
  differ due to correlated hashrate changes, strategic mining, etc.
- Simulator limitations: Block time model uses exponential distribution with
  profile-dependent difficulty. Real mining involves PoW variance, network
  latency, and hashrate correlation that this model does not capture.
