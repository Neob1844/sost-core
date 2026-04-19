# Burst Replay 5058-5066 — Validation Report

Seeds: 20 | Blocks per sim: 500 | Hashrate: 1.3 kH/s

## Results

| Metric | Baseline | Burst ctrl | DynSlew |
|--------|----------|------------|--------|
| Mean block time | 10.2m | 10.2m | 10.2m |
| Std deviation | 11.8m | 12.8m | 12.8m |
| Median | 6.7m | 6.6m | 6.6m |
| P95 block time | 32m | 32m | 32m |
| P99 block time | 56m | 56m | 56m |
| Max block time | 109m | 142m | 142m |
| Blocks > 20m | 67.5 | 66.4 | 66.6 |
| Blocks > 40m | 14.1 | 13.8 | 13.7 |
| Blocks > 60m | 3.0 | 3.2 | 3.1 |
| Max consecutive >20m | 2.5 | 2.4 | 2.4 |
| Sawtooth score | 0.065 | 0.068 | 0.076 |
| Smoothness | 0.618 | 0.618 | 0.620 |
| Lag std | 2.9 | 3.2 | 3.2 |
| Lag max | 10 | 10 | 10 |
| Composite score | 500 | 506 | 502 |
| Max profile reached | H10 | H10 | H10 |
| Overshoots to H11+ | 0.0 | 0.0 | 0.0 |
| bitsQ guard activations | 0.0 | 0.0 | 0.0 |
| GREEN verdicts | 0/20 | 0/20 | 0/20 |

## Verdict

Best: **A) Baseline (slew ±1 fixed)** (score 500)

**Baseline is still better.** Burst controller needs further tuning.

Dynamic slew libre: **REJECTED** (overshoots H11+, pursues impossible profiles)
