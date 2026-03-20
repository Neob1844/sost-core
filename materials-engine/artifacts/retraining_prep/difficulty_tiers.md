# Difficulty Tier Distribution

## band_gap

Total: 76,124

| Tier | Count | % |
|------|-------|---|
| easy | 53,187 | 69.87% |
| hard | 4,810 | 6.32% |
| high_value_retrain | 494 | 0.65% |
| medium | 17,633 | 23.16% |

## formation_energy

Total: 76,193

| Tier | Count | % |
|------|-------|---|
| easy | 74,351 | 97.58% |
| medium | 1,842 | 2.42% |

## Tier Definitions

- **easy**: Model predicts well (within HIGH confidence band). Common chemistry, frequent SG.
- **medium**: Model predicts with moderate error (MEDIUM band). Some structural/chemical complexity.
- **hard**: Model struggles (LOW band or known hotspot). Rare value ranges, complex structures.
- **sparse_exotic**: Rare elements, infrequent SGs, 4+ components. Model has little training signal.
- **high_value_retrain**: Hard + high scientific value. Priority for inclusion in retraining sets.
- **holdout_candidate**: Good for held-out validation. Representative but not critical for training.
