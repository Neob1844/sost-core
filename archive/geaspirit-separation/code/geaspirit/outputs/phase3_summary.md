# GeaSpirit Phase 3 — Honest Validation Summary

## Validation Comparison

| Metric | Naive CV (Phase 2) | Spatial Block CV (Phase 3) | Delta |
|--------|-------------------|---------------------------|-------|
| **AUC-ROC** | 0.9995 | **0.6844** | -0.3151 |
| Precision | 0.9916 | **0.6060** | -0.3856 |
| Recall | 0.9994 | **0.2836** | -0.7158 |
| F1 | — | **0.3454** | — |
| PR-AUC | — | **0.5007** | — |

## What This Means

The naive AUC of 0.9995 was inflated by **spatial autocorrelation leakage**:
adjacent pixels ended up in both train and test sets, and the model memorized
local patterns rather than learning generalizable geological signatures.

The honest AUC of **0.6844** means the model has real predictive power
(random would be 0.50) but is far from the near-perfect illusion of Phase 2.

## Calibration

| Metric | Before | After |
|--------|--------|-------|
| Brier Score | 0.1955 | **0.1711** |
| ECE | 0.1446 | **0.0000** |

Isotonic calibration successfully improved probability estimates.

## Target Discovery

With the honest model, 2 unexplored targets were identified above 0.6 threshold
outside the 5km exclusion buffer from known deposits.

## Key Lessons

1. **Spatial leakage was massive** — reduced AUC by 0.31
2. **Hard negatives helped** — model trained on geology-similar terrain
3. **DEM features still dominate** — terrain structure is real signal
4. **The model works but needs more training data** for robust generalization
5. **Phase 2 AUC should NOT be quoted as the real performance**

## Next Steps

1. Add EMIT hyperspectral (285 bands) for mineral-specific detection
2. Improve SAR features with InSAR deformation
3. Add public geological map vectors as features
4. Add airborne gravity/magnetics where available (USGS, Geoscience Australia)
5. Test transfer learning to Pilbara and Zambia
6. Increase training data by including more deposit types from MRDS
