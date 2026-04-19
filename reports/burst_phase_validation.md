# Burst Phase Validation

Seeds: 20 | Burst: 25 blocks @ 13.0 kH/s | Recovery: 200 blocks @ 1.3 kH/s

## Key Metrics

| Metric | Baseline | Burst ctrl | DynSlew |
|---|---|---|---|
| Blocks to reach H9 | 11.5 | 11.5 | 11.5 |
| Blocks to reach H10 | 13.9 | 13.9 | 13.9 |
| Max lag accumulated | 11.1 | 11.1 | 11.1 |
| Lag at end of burst | 8.6 | 8.2 | 8.6 |
| Max profile reached | 11.1 | 11.0 | 11.1 |
| Overshoots to H11+ | 2.0 | 1.9 | 2.0 |
| Burst phase time (s) | 10130.2 | 10363.3 | 10130.2 |
| bitsQ guard activations | 0.0 | 0.0 | 0.0 |
| Blocks > 20m (total) | 27.6 | 27.8 | 27.7 |
| Blocks > 40m (total) | 5.8 | 5.8 | 5.8 |
| Blocks > 60m (total) | 1.6 | 1.6 | 1.6 |
| Mean block time (s) | 600.6 | 600.6 | 600.7 |
| Std block time (s) | 953.4 | 942.3 | 953.4 |

## Profile Path (seed 42)

**A) Baseline (slew ±1):** B0 → H1 → H2 → H3 → H4 → H5 → H6 → H7 → H8 → H9 → H10 → H9 → H10 → H11 → H11 → H10 → H9 → H8 → H9 → H10 → H10 → H11 → H10 → H11 → H11

**B) Burst ctrl (H10 ceil):** B0 → H1 → H2 → H3 → H4 → H5 → H6 → H7 → H8 → H9 → H10 → H9 → H10 → H11 → H11 → H10 → H9 → H8 → H9 → H10 → H10 → H11 → H10 → H11 → H11

**C) DynSlew libre:** B0 → H1 → H2 → H3 → H4 → H5 → H6 → H7 → H8 → H9 → H10 → H9 → H10 → H11 → H11 → H10 → H9 → H8 → H9 → H10 → H10 → H11 → H10 → H11 → H11


## Verdict

**NO_IMPROVEMENT**

Burst controller does not measurably improve the burst phase.
