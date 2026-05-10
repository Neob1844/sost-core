# Trinity / Materials Discovery — Scorecard `oxide_frontier_v01`

> **DRY-RUN scorecard.** Weighted industrial-promise score computed from remote proxy axes (abundance, criticality, structure, hypothesis count, compute feasibility, novelty uncertainty, toxicity/cost). Not a DFT result. Not a synthesis recommendation. Not a performance claim.

- **Schema**: `trinity-materials-scorecard/v0.1`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `candidate_pool_basename`: `TRINITY_MATERIALS_CANDIDATES_oxide_frontier.json`
  - `candidate_pool_sha256`: `98f564da40a59e136d84366c47ecb1d35d2fac95bbc07b6b9e6ef0b1644d7e66`
  - `filter_basename`: `TRINITY_MATERIALS_FILTER_oxide_frontier.json`
  - `filter_sha256`: `9f92ab14e25fa15c025f77f7b3db9c8f1ce131b79110f5652b3d91f2a63a8544`
  - `mode`: `deterministic_rule_based_v0.1`

## Weights

- `abundance`: `0.2`
- `compute_feasibility`: `0.1`
- `criticality_penalty`: `0.2`
- `hypothesis_count`: `0.1`
- `novelty_uncertainty_penalty`: `0.1`
- `structure_plausibility`: `0.15`
- `toxicity_cost_penalty`: `0.15`

## Top candidates by score

| rank | id | formula | family | score | confidence | hypotheses |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `MX-0016` | `SrTiO3` | `perovskite` | 93.7 | 0.946 | magnetoresistance_oxide, oxygen_evolution_catalyst, thermoelectric |
| 2 | `MX-0001` | `NiAl2O4` | `spinel` | 92.1 | 0.941 | battery_cathode, magnetic_oxide, oxygen_evolution_catalyst |
| 3 | `MX-0021` | `CaZrO3` | `perovskite` | 90.6 | 0.949 | ferroelectric, proton_conductor |
| 4 | `MX-0009` | `ZnCr2O4` | `spinel` | 90.2 | 0.917 | battery_cathode, magnetic_oxide, oxygen_evolution_catalyst |
| 5 | `MX-0005` | `CuCr2O4` | `spinel` | 90.1 | 0.916 | battery_cathode, magnetic_oxide, oxygen_evolution_catalyst |
| 6 | `MX-0008` | `MnAl2O4` | `spinel` | 89.1 | 0.945 | magnetic_oxide, oxygen_evolution_catalyst |
| 7 | `MX-0013` | `FeGa2O4` | `spinel` | 87.3 | 0.923 | battery_cathode, magnetic_oxide |
| 8 | `MX-0010` | `NiFe2O4` | `spinel` | 85.3 | 0.94 | oxygen_evolution_catalyst |
