# Promotion Decision: **HOLD**

Production MAE: 0.3422
Best challenger: bg_curriculum_20k (MAE=0.6287)
Improvement: -0.2865 (-83.7%)

## Rationale
Overall MAE improvement (-0.2865) below threshold (0.01); Severe bucket regression: delta=0.9396; R² dropped: 0.7070 → 0.4697

## Lessons
- IV.L showed pure-subset training fails — model loses easy baseline
- Stratified mixing preserves distribution while boosting hard regions
- Curriculum learning offers staged improvement but adds complexity
- Best stratified challenger: bg_curriculum_20k (MAE=0.6287)
