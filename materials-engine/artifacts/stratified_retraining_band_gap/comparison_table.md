# Stratified Retraining — Comparison

| Model | Role | Strategy | Size | MAE | RMSE | R² | MAE Δ |
|-------|------|----------|------|-----|------|----|-------|
| production_alignn_lite_20k | production | random_20k | 20,000 | 0.3422 | 0.7362 | 0.7070 | — |
| bg_stratified_20k | challenger | stratified | 19,925 | 0.6547 | 0.9893 | 0.6437 | +0.3125 |
| bg_curriculum_20k | challenger | curriculum | 19,968 | 0.6287 | 0.9153 | 0.4697 | +0.2865 |
| bg_stratified_balanced_30k | challenger | stratified | 27,437 | 0.6771 | 0.9767 | 0.6273 | +0.3349 |
