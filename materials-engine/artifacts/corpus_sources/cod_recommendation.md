# COD Operational Recommendation

**Decision:** continue_cod_expansion

## Rationale

COD pilot added 10 materials with 9 new elements. Structural diversity improved. Worth expanding for reference/search space, but NOT for training.

## Next Steps

- Expand COD ingestion to 500-1000 exotic structures
- Focus on rare earth and intermetallic families
- Use COD structures to improve novelty detection baseline
- Wait for AFLOW real availability for training-ready expansion
- Do NOT retrain models on COD-only materials

## What NOT To Do

- Do NOT train FE/BG models on COD structure-only materials
- Do NOT mark COD materials as training_ready
- Do NOT retrain until corpus has more labeled data from DFT sources
