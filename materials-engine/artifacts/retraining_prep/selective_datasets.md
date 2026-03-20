# Selective Retraining Datasets

**Status: PREPARED — NOT YET TRAINED**

## bg_hotspots_10k

- **Target**: band_gap
- **Size**: 5
- **Elements**: 8 unique
- **Spacegroups**: 5 unique
- **Selection**: Materials with band_gap 1.0-6.0 eV where model has MEDIUM/LOW confidence (MAE 0.87-1.12 eV in calibration)
- **Reason**: Calibration shows BG 3-6 eV bucket has MAE=1.12 (LOW confidence) and 1-3 eV has MAE=0.87 (MEDIUM). These are the model's weakest regions.
- **Expected benefit**: Reduce BG MAE for wide-gap materials from ~1.0 to <0.6 eV. Improve calibration from LOW/MEDIUM to HIGH.
- **Risk**: Oversampling wide-gap may degrade metal/narrow-gap accuracy. Use curriculum or stratified sampling.

## bg_sparse_exotic_10k

- **Target**: band_gap
- **Size**: 4
- **Elements**: 17 unique
- **Spacegroups**: 4 unique
- **Selection**: Materials with 4+ elements and band_gap. High combinatorial complexity where model has limited signal.
- **Reason**: 5+ element materials show MAE=0.73 in calibration (MEDIUM). Only 1,630 materials in corpus have n_elements>=4 with BG.
- **Expected benefit**: Better BG prediction for complex compositions. Expand chemical diversity in training.
- **Risk**: Small sample — may not generalize. 4-elem materials dominate over 5+ which are truly sparse.

## bg_balanced_hardmix_20k

- **Target**: band_gap
- **Size**: 9
- **Elements**: 21 unique
- **Spacegroups**: 7 unique
- **Selection**: Union of hard BG value ranges (1-6 eV) + complex compositions (4+ elem) + rare SGs. Balanced for diversity.
- **Reason**: Combined difficulty signals. Addresses all weak calibration buckets simultaneously.
- **Expected benefit**: Broad improvement across all weak BG regions. Reduce overall BG MAE from 0.49 toward 0.35.
- **Risk**: Larger dataset = longer training. Risk of diluting hard cases with too many medium cases.

## fe_hardcases_10k

- **Target**: formation_energy
- **Size**: 1
- **Elements**: 5 unique
- **Spacegroups**: 1 unique
- **Selection**: Materials with formation_energy > 0 eV/atom (unstable/metastable). Calibration shows MAE=0.43 for 1-5 eV range (MEDIUM).
- **Reason**: FE > 0 (unstable) is the only MEDIUM confidence bucket. MAE=0.43 vs overall 0.23. 15K materials in this region.
- **Expected benefit**: Reduce FE MAE for unstable materials from 0.43 to <0.25. Critical for stability screening.
- **Risk**: FE model already strong (overall MAE=0.15). Gains may be marginal vs effort.

## fe_sparse_mix_10k

- **Target**: formation_energy
- **Size**: 4
- **Elements**: 17 unique
- **Spacegroups**: 4 unique
- **Selection**: Complex materials (4+ elements) for formation_energy. Rare chemistry where model has limited exposure.
- **Reason**: FE model trained mostly on 2-3 element materials. 4+ element materials are underrepresented.
- **Expected benefit**: Better FE prediction for complex compositions. Useful for multinary phase screening.
- **Risk**: FE model already excellent on common materials. Overemphasis on complex may not help.

## curriculum_easy_to_hard_20k

- **Target**: band_gap
- **Size**: 9
- **Elements**: 21 unique
- **Spacegroups**: 7 unique
- **Selection**: Full BG corpus sample (20K). Training uses curriculum: start with easy (metals, common), gradually add harder (wide-gap, complex). Ordered by predicted difficulty.
- **Reason**: Curriculum learning can improve convergence on hard cases without sacrificing easy-case accuracy.
- **Expected benefit**: Smoother loss landscape. Better generalization across all BG ranges.
- **Risk**: Curriculum ordering requires difficulty labels at training time. More complex training loop.

