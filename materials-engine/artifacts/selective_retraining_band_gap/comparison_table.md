# Selective Retraining — Comparison Table

| Model | Role | Dataset | Size | MAE | RMSE | R² | MAE Δ |
|-------|------|---------|------|-----|------|----|-------|
| production_alignn_lite_20k | production | full_corpus_20k | 20,000 | 0.3422 | 0.7362 | 0.7070 | — |
| bg_hotspots_10k | challenger | bg_hotspots_10k | 9,921 | 0.6374 | 0.8255 | 0.5977 | +0.2952 |
| bg_sparse_exotic_10k | challenger | bg_sparse_exotic_10k | 9,953 | 0.5926 | 0.9121 | 0.7336 | +0.2504 |
| bg_balanced_hardmix_20k | challenger | bg_balanced_hardmix_20k | 19,885 | 0.6991 | 0.9815 | 0.6745 | +0.3569 |
