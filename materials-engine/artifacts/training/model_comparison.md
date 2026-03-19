# Phase II.75 — Model Comparison (2000 JARVIS samples)

## Results

| Model | Target | MAE | RMSE | R² | Epochs | Time |
|---|---|---|---|---|---|---|
| alignn_lite | band_gap | 0.4022 | 0.7849 | 0.7096 | 40 | 463.9s |
| alignn_lite | formation_energy | 0.2321 | 0.3304 | 0.93 | 40 | 465.2s |
| cgcnn | band_gap | 0.4531 | 0.8641 | 0.648 | 15 | 935.0s |
| cgcnn | formation_energy | 0.2397 | 0.3207 | 0.934 | 40 | 2915.8s |

## Best Models

| Target | Best Model | MAE | R² |
|---|---|---|---|
| band_gap | alignn_lite | 0.4022 | 0.7096 |
| formation_energy | alignn_lite | 0.2321 | 0.93 |

## Improvement vs Phase II (200 samples)

| Target | Phase II MAE | Phase II.75 MAE | MAE improvement | R² improvement |
|---|---|---|---|---|
| band_gap | 0.6476 | 0.4022 | 37.9% | 46.7% |
| formation_energy | 0.3001 | 0.2321 | 22.7% | 4.1% |
