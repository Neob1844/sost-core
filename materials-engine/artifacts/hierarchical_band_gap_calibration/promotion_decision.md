# Promotion Decision: **WATCHLIST**

Production MAE: 0.3422
Best calibrated MAE: 0.2187
Policy: original
Improvement: 0.1235 (36.1%)
Narrow-gap fixed: False

## Rationale
MAE improved by 0.1235 eV (36.1%); Narrow-gap still regressed: 0.6001 vs prod 0.5090; Severe regression: delta=0.3183

## Lessons
- IV.N hierarchical pipeline: MAE=0.2793 but narrow-gap regressed
- Best calibrated policy: original (borderline_low=0.3)
- Calibrated MAE: 0.2187 vs production 0.3422
- Narrow-gap bucket: 0.6001 (prod=0.5090)
- FN count: 220 (was 96 in IV.N at threshold=0.5)
