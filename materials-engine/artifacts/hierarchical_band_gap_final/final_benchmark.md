# Final Hierarchical Promotion Benchmark

Sample size: 2000, seed: 42

| Pipeline | MAE | RMSE | R² | Time |
|----------|-----|------|----|------|
| production_alignn_20k | 0.3407 | 0.6806 | 0.7661 | 2.8s |
| hierarchical_v2_gate_reg | 0.2628 | 0.6690 | 0.7740 | 2.4s |

## Per-Bucket MAE

| Bucket | production_alig | hierarchical_v2 |
|--------|---------|---------|
| 0.0-0.05 | 0.1907 (n=1486) | 0.0892 (n=1486) |
| 0.05-1.0 | 0.5135 (n=142) | 0.6495 (n=142) |
| 1.0-3.0 | 0.7950 (n=192) | 0.8102 (n=192) |
| 3.0-6.0 | 0.8682 (n=160) | 0.8116 (n=160) |
| 6.0+ | 1.6707 (n=20) | 0.7725 (n=20) |
