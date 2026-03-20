# Training Ladder: Band Gap

| Rung | Arch | Size | MAE | RMSE | R² | Time | Best Epoch |
|------|------|------|-----|------|-----|------|------------|
| rung_5k | cgcnn | 5,000 | 0.3914 | 0.8142 | 0.7318 | 670s | 17 |
| rung_10k | cgcnn | 10,000 | 0.3735 | 0.7009 | 0.7638 | 912s | 19 |
| rung_20k | alignn_lite | 20,000 | 0.3422 | 0.7362 | 0.7070 | 2642s | 17 |
| rung_20k | cgcnn | 20,000 | 0.3931 | 0.7467 | 0.6986 | 1937s | 17 |
| rung_40k | cgcnn | 40,000 | 0.4119 | 0.6816 | 0.7781 | 2670s | 9 |
| rung_full | cgcnn | 75,993 | 0.4136 | 0.6696 | 0.7632 | 4088s | 9 |

## Best: rung_20k alignn_lite (MAE=0.3422)
