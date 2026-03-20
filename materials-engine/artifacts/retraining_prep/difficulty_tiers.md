# Difficulty Tier Distribution

## band_gap

Total: 9

| Tier | Count | % |
|------|-------|---|
| high_value_retrain | 2 | 22.22% |
| medium | 3 | 33.33% |
| sparse_exotic | 4 | 44.44% |

## formation_energy

Total: 10

| Tier | Count | % |
|------|-------|---|
| easy | 6 | 60.0% |
| sparse_exotic | 4 | 40.0% |

## Tier Definitions

- **easy**: Model predicts well (within HIGH confidence band). Common chemistry, frequent SG.
- **medium**: Model predicts with moderate error (MEDIUM band). Some structural/chemical complexity.
- **hard**: Model struggles (LOW band or known hotspot). Rare value ranges, complex structures.
- **sparse_exotic**: Rare elements, infrequent SGs, 4+ components. Model has little training signal.
- **high_value_retrain**: Hard + high scientific value. Priority for inclusion in retraining sets.
- **holdout_candidate**: Good for held-out validation. Representative but not critical for training.
