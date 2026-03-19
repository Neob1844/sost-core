# Training Ladder: Formation Energy

| Rung | Arch | Size | MAE | RMSE | R² | Time |
|------|------|------|-----|------|-----|------|
| rung_5k | cgcnn | 5,000 | 0.2033 | 0.2824 | 0.9454 | 489s |
| rung_10k | cgcnn | 10,000 | 0.2012 | 0.2706 | 0.9425 | 947s |
| rung_20k | alignn_lite | 20,000 | 0.2162 | 0.3156 | 0.9033 | 1919s |
| rung_20k | cgcnn | 20,000 | 0.1528 | 0.2271 | 0.9499 | 1375s |
| rung_40k | cgcnn | 40,000 | 0.1757 | 0.2337 | 0.9510 | 2744s |
| rung_full | cgcnn | 75,993 | 0.3566 | 0.5125 | 0.7730 | 3655s |

## CTO Decision: PROMOTE_MID_SCALE_MODEL

Best model: **rung_20k CGCNN** (MAE=0.1528, R²=0.9499)

The 20K CGCNN model (MAE=0.1528, R²=0.9499) achieves the best MAE. Larger datasets (40K, 75K) did NOT improve — likely needs more epochs or lower learning rate at scale. 20K is the best cost/quality tradeoff. ALIGNN-Lite underperforms CGCNN at 20K (0.2162 vs 0.1528).
