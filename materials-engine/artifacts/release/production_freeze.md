# Production Freeze

## formation_energy
- Model: cgcnn
- MAE: 0.1528
- Status: PRODUCTION — stable, no changes needed

## band_gap
- Model: alignn_lite
- MAE: 0.3422
- Status: PRODUCTION — stable after 9 phases of optimization attempts

## Do NOT Change
- Do NOT modify model_registry.json without CTO approval
- Do NOT retrain production models without full benchmark validation
- Do NOT promote hierarchical pipeline without solving narrow-gap regression
- Do NOT delete any checkpoint files — they are the reproducibility chain
