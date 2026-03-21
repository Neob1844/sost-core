# Promotion Decision: **WATCHLIST**

Production MAE: 0.3422
Hierarchical MAE: 0.2793
Improvement: 0.0629 (18.4%)
Gate accuracy: 0.9080

## Rationale
Pipeline MAE improved by 0.0629 eV (18.4%); Severe bucket regression: delta=0.3977; 3 bucket(s) improved

## Lessons
- IV.L+M: pure subset and stratified training failed — model needs easy baseline
- Hierarchical approach separates the trivial metal case from harder regression
- Gate accuracy: 0.9080
- Non-metal regressor MAE: 0.7609
- Combined pipeline MAE: 0.2793 vs production 0.3422
