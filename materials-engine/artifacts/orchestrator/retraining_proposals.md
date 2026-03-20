# Retraining Proposals

## retrain_bg_priority [high]
- **Target:** band_gap
- **Reason:** Band gap has 2 error hotspots vs 1 for formation energy
- **Benefit:** Reduce MAE in underperforming buckets
- **Rung:** 20K selective (focus on underperforming regions)

## retrain_fe_targeted [medium]
- **Target:** formation_energy
- **Reason:** 1 error hotspots detected in formation energy prediction
- **Benefit:** Improve accuracy for complex/multi-element materials
- **Rung:** 20K with augmented sampling from sparse regions

## expand_then_retrain [medium]
- **Target:** both
- **Reason:** Corpus expansion before retraining typically yields better gains than retraining alone
- **Benefit:** Broader coverage → better generalization → lower error across all buckets
- **Rung:** After expansion: 40K or selective 20K from expanded corpus

