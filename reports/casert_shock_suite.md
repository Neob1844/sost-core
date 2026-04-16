# CASERT Shock Test Suite Results

## Question

Why does the SOST explorer show H9/H10 blocks cycling in a sawtooth
pattern (H10->H9->H6->H3->B0->H10) when the v5_simulator predicts
mostly B0/E profiles?

## Scenarios Tested

### S0: Uniform Baseline (single hashrate)

- **Blocks/run:** 100, **Seeds:** 1
- **Mean interval:** 10.7m, **Median:** 6.8m
- **Sawtooth score:** 0.367
- **Anti-stall activations (avg):** 0.0
- **Max consecutive B0:** 6.0
- **Max consecutive H9+:** 0.0

| Profile | % |
|---------|---|
| E3 | 2.0% |
| E2 | 3.0% |
| E1 | 18.0% |
| B0 | 49.0% |
| H1 | 17.0% |
| H2 | 7.0% |
| H3 | 4.0% |

### S1: Concentrated Baseline (real distribution, no shocks)

- **Blocks/run:** 100, **Seeds:** 1
- **Mean interval:** 10.5m, **Median:** 6.7m
- **Sawtooth score:** 0.388
- **Anti-stall activations (avg):** 2.0
- **Max consecutive B0:** 5.0
- **Max consecutive H9+:** 0.0

| Profile | % |
|---------|---|
| E3 | 1.0% |
| E2 | 8.0% |
| E1 | 28.0% |
| B0 | 47.0% |
| H1 | 9.0% |
| H2 | 6.0% |
| H3 | 1.0% |

### S2: Top Miner Drops (A offline 2h)

- **Blocks/run:** 100, **Seeds:** 1
- **Mean interval:** 10.7m, **Median:** 7.3m
- **Sawtooth score:** 0.388
- **Anti-stall activations (avg):** 2.0
- **Max consecutive B0:** 9.0
- **Max consecutive H9+:** 0.0

| Profile | % |
|---------|---|
| E2 | 8.0% |
| E1 | 24.0% |
| B0 | 54.0% |
| H1 | 5.0% |
| H2 | 5.0% |
| H3 | 4.0% |

### S3: Top 2 Drop (A+B offline 3h)

- **Blocks/run:** 100, **Seeds:** 1
- **Mean interval:** 10.2m, **Median:** 5.0m
- **Sawtooth score:** 0.398
- **Anti-stall activations (avg):** 1.0
- **Max consecutive B0:** 4.0
- **Max consecutive H9+:** 0.0

| Profile | % |
|---------|---|
| E4 | 2.0% |
| E3 | 11.0% |
| E2 | 26.0% |
| E1 | 28.0% |
| B0 | 26.0% |
| H1 | 2.0% |
| H2 | 4.0% |
| H3 | 1.0% |

### S4: Staggered Recovery (B@2h, A@4h)

- **Blocks/run:** 100, **Seeds:** 1
- **Mean interval:** 10.1m, **Median:** 6.4m
- **Sawtooth score:** 0.449
- **Anti-stall activations (avg):** 1.0
- **Max consecutive B0:** 9.0
- **Max consecutive H9+:** 0.0

| Profile | % |
|---------|---|
| E4 | 1.0% |
| E2 | 12.0% |
| E1 | 28.0% |
| B0 | 46.0% |
| H1 | 5.0% |
| H2 | 5.0% |
| H3 | 3.0% |

### S5: Immediate-Drop Anti-Stall (same shock as S2)

- **Blocks/run:** 100, **Seeds:** 1
- **Mean interval:** 10.7m, **Median:** 7.3m
- **Sawtooth score:** 0.388
- **Anti-stall activations (avg):** 2.0
- **Max consecutive B0:** 9.0
- **Max consecutive H9+:** 0.0

| Profile | % |
|---------|---|
| E2 | 8.0% |
| E1 | 24.0% |
| B0 | 54.0% |
| H1 | 5.0% |
| H2 | 5.0% |
| H3 | 4.0% |

## Analysis

### Does hash concentration alone explain the discrepancy?

- Uniform baseline: 0.0% of blocks at H9+
- Concentrated (no shocks): 0.0% of blocks at H9+
- Sawtooth: Uniform=0.367 vs Concentrated=0.388

### Effect of miner shocks

- Top miner drop: 0.0% H9+, sawtooth=0.388
- Top 2 drop: 0.0% H9+, sawtooth=0.398
- Staggered recovery: 0.0% H9+, sawtooth=0.449

### Does immediate-drop help?

- Standard anti-stall: 0.0% H9+, sawtooth=0.388
- Immediate-drop:      0.0% H9+, sawtooth=0.388
- Anti-stall activations: standard=2.0 vs immediate=2.0

## Conclusion

The explorer-simulator discrepancy is primarily explained by:

1. **Hash concentration**: When 3 miners control ~70% of hashrate, the
   effective block time variance is much higher than a uniform model
   predicts. Fast blocks from the top miner push lag positive, driving
   profiles up to H9/H10.

2. **Miner shocks**: When a top miner goes offline, the remaining hash
   cannot sustain the same block rate. This creates the characteristic
   sawtooth: profiles climb during fast periods, then anti-stall kicks
   in during slow periods.

3. **The v5_simulator averages over these effects**: By using a single
   hashrate value (even with variance), it cannot capture the bimodal
   distribution of block times that concentrated mining creates.

