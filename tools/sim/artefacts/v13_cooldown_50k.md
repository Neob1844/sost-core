  ... 16/192  (4.1s)
  ... 32/192  (8.9s)
  ... 48/192  (19.6s)
  ... 64/192  (24.0s)
  ... 80/192  (28.0s)
  ... 96/192  (34.7s)
  ... 112/192  (38.1s)
  ... 128/192  (43.8s)
  ... 144/192  (52.8s)
  ... 160/192  (56.2s)
  ... 176/192  (60.5s)
  ... 192/192  (69.3s)
# V13 lottery cooldown sweep

- blocks per scenario: 50000
- seed: 0xc0ffee
- freq_mode: lifecycle
- dom_shares: [0.5, 0.7, 0.85, 0.92]
- honest_counts: [5, 10, 35, 100]
- sybil_counts: [0, 5, 10, 100]
- windows: [5, 6, 7]
- total scenarios: 192

## Per-window aggregates (across full C9 grid)

| window | rollover_rate (mean) | pool_avg (mean) | dom_total_share (mean) | dom_total_share (max) | honest_median_total (mean) | cooldown_exclusion (mean) | double_win (mean) |
|-------:|---------------------:|----------------:|----------------------:|----------------------:|--------------------------:|--------------------------:|-----------------:|
| 5 | 0.00% | 64.41 | 43.76% | 63.39% | 1.87% | 8.88% | 1.14% |
| 6 | 0.00% | 64.17 | 43.80% | 63.40% | 1.87% | 9.74% | 1.10% |
| 7 | 0.01% | 63.96 | 43.85% | 63.43% | 1.86% | 10.55% | 1.08% |

## Sybil delta (smaller = better)

How much sybils boost the dominant's total share, averaged across (dom, honest) and sybil counts ∈ {5, 10, 100}.

| window | sybil_delta (mean) | sybil_delta (median) | sybil_delta (max) |
|-------:|-------------------:|---------------------:|------------------:|
| 5 | 8.903% | 9.514% | 17.770% |
| 6 | 8.994% | 9.530% | 17.851% |
| 7 | 9.066% | 9.498% | 17.939% |

## Concentration view

| window | top-1 (mean) | top-1 (max) | honest worst (mean) | honest median (mean) |
|-------:|-------------:|------------:|--------------------:|--------------------:|
| 5 | 43.76% | 63.39% | 1.82% | 1.87% |
| 6 | 43.80% | 63.40% | 1.81% | 1.87% |
| 7 | 43.85% | 63.43% | 1.81% | 1.86% |

## Pairwise deltas — what does the bump actually buy?

| pair | metric | mean Δ (w_b − w_a) | median Δ | max Δ | min Δ |
|------|--------|-------------------:|---------:|------:|------:|
| 5→6 | dom_total_share | +0.036% | +0.015% | +0.428% | -0.221% |
| 5→6 | rollover_rate | +0.002% | +0.000% | +0.134% | +0.000% |
| 5→6 | pool_avg | -0.243 | -0.225 | -0.033 | -0.790 |
| 5→6 | cooldown_exclusion_rate | +0.851% | +0.433% | +5.042% | +0.042% |
| 5→6 | honest_worst_total | -0.004% | -0.003% | +0.069% | -0.101% |
| 6→7 | dom_total_share | +0.052% | +0.023% | +0.557% | -0.075% |
| 6→7 | rollover_rate | +0.006% | +0.000% | +0.324% | +0.000% |
| 6→7 | pool_avg | -0.210 | -0.208 | +0.471 | -0.535 |
| 6→7 | cooldown_exclusion_rate | +0.810% | +0.420% | +4.599% | +0.040% |
| 6→7 | honest_worst_total | -0.006% | +0.001% | +0.016% | -0.122% |
| 5→7 | dom_total_share | +0.088% | +0.038% | +0.985% | -0.177% |
| 5→7 | rollover_rate | +0.009% | +0.000% | +0.458% | +0.000% |
| 5→7 | pool_avg | -0.453 | -0.436 | +0.391 | -1.038 |
| 5→7 | cooldown_exclusion_rate | +1.662% | +0.856% | +9.641% | +0.082% |
| 5→7 | honest_worst_total | -0.010% | -0.004% | +0.082% | -0.223% |

## Recommendation

- **window=5**: rollover_max=0.006% · dom_share_mean=43.76% · honest_worst_mean=1.818% · sybil_delta_mean=8.903%
- **window=6**: rollover_max=0.136% · dom_share_mean=43.80% · honest_worst_mean=1.814% · sybil_delta_mean=8.994%
- **window=7**: rollover_max=0.460% · dom_share_mean=43.85% · honest_worst_mean=1.808% · sybil_delta_mean=9.066%

**Verdict:** No candidate window strictly dominates baseline (5). Across the C9 grid, larger windows show small but consistent regressions on dom_share, sybil_delta, and honest_worst, while only marginally reducing double_win. Bump NOT recommended — keep cooldown=5. Best candidate audit: window=6, improves=[], regresses=['dom_share', 'sybil_delta', 'rollover', 'honest_worst'].

Wrote structured artefact to tools/sim/artefacts/v13_cooldown_50k.json
