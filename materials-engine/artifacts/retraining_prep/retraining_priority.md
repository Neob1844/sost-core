# Retraining Priority Ranking

**Recommendation: retrain_band_gap_hotspots_next**

Use dataset 'bg_sparse_exotic_10k' (0.60 priority) for next band_gap retraining on rung_20k. Current BG MAE=0.49 → target MAE<0.35.

## Ranking

| Rank | Dataset | Target | Score | Recommendation |
|------|---------|--------|-------|----------------|
| 1 | bg_sparse_exotic_10k | band_gap | 0.603 | retrain_band_gap_with_bg_sparse_exotic_10k_next |
| 2 | bg_balanced_hardmix_20k | band_gap | 0.498 | consider_bg_balanced_hardmix_20k_after_top_priority |
| 3 | curriculum_easy_to_hard_20k | band_gap | 0.498 | consider_curriculum_easy_to_hard_20k_after_top_priority |
| 4 | fe_sparse_mix_10k | formation_energy | 0.481 | consider_fe_sparse_mix_10k_after_top_priority |
| 5 | fe_hardcases_10k | formation_energy | 0.393 | defer_fe_hardcases_10k |
| 6 | bg_hotspots_10k | band_gap | 0.390 | defer_bg_hotspots_10k |

## Score Breakdown (top 3)

### #1 bg_sparse_exotic_10k
- Benefit: 0.708
- Difficulty concentration: 1.000
- Diversity: 0.105
- Sparse coverage: 0.800
- Exotic value: 0.900
- Overfit risk: 0.700
- Training cost: 0.000

### #2 bg_balanced_hardmix_20k
- Benefit: 0.644
- Difficulty concentration: 1.000
- Diversity: 0.134
- Sparse coverage: 0.600
- Exotic value: 0.300
- Overfit risk: 0.700
- Training cost: 0.000

### #3 curriculum_easy_to_hard_20k
- Benefit: 0.644
- Difficulty concentration: 1.000
- Diversity: 0.134
- Sparse coverage: 0.600
- Exotic value: 0.300
- Overfit risk: 0.700
- Training cost: 0.000

## Do NOT

- Do NOT retrain in this phase — datasets are prepared, not executed
- Do NOT use structure_only or external_unlabeled tier for training
- Do NOT retrain on full 76K corpus — 20K was already optimal in ladder
- Do NOT change production models until new training is validated
- Do NOT ignore holdout set — reserve for final validation
