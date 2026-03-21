# Promotion Decision: **WATCHLIST**

Production MAE: 0.3422
Best pipeline MAE: 0.2568
Best regressor: nonmetal_lower_lr (MAE=0.6654)
Improvement: 0.0854 (25.0%)
Narrow-gap: 0.83 (prod=0.5090)

## Rationale
Pipeline MAE improved by 0.0854 (25.0%); Narrow-gap regression: 0.8300 vs prod 0.5090; Severe regression: 0.3210

## Lessons
- IV.N regressor MAE=0.7609 → best challenger MAE=0.6654
- Pipeline MAE: production=0.3422, best=0.2568
- Narrow-gap: prod=0.5090, best=0.8300
- Best config: nonmetal_lower_lr (epochs=20, lr=0.002)
