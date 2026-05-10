# Trinity / Materials Track — Scorecard `novel_frontier_phase1`

> **DRY-RUN scorecard.** This document is a pinned, deterministic input artefact for the Materials Track pipeline. It records the candidate set, honesty matrix and source attribution. It does not claim novelty for any specific material.

- **Schema**: `trinity-materials-scorecard/v0`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **features_available**: `0`
- **Source**:
  - `input_set_version`: `novel_frontier_v0_pinned`
  - `mode`: `mock`
  - `module`: `materials_engine.frontier+novelty (mocked in v0)`

## Honesty matrix

- `candidates_have_dft_relaxation`: `False`
- `candidates_have_phonon_screening`: `False`
- `candidates_have_synthesis_data`: `False`
- `frontier_scores_are_seeds_not_validations`: `True`
- `novelty_baseline_locked`: `True`

## Candidates

| id | formula | family | seed_novelty | seed_frontier_proximity |
| --- | --- | --- | --- | --- |
| `C-01` | `Fe2MgO4` | spinel oxide | 0.62 | 0.71 |
| `C-02` | `LiNi0.5Mn1.5O4` | layered oxide / cathode candidate | 0.48 | 0.59 |
| `C-03` | `BaZrO3:Y` | perovskite / proton conductor | 0.55 | 0.66 |
| `C-04` | `CaCu3Ti4O12` | giant-permittivity oxide | 0.41 | 0.52 |
| `C-05` | `Co3O4` | transition-metal oxide reference | 0.30 | 0.40 |

### Open questions per candidate

- **`C-01` (Fe2MgO4)**
  - no measured formation energy on file
  - no MLIP relaxation baseline
  - no synthesised polymorph reference for ferrimagnetic ordering
- **`C-02` (LiNi0.5Mn1.5O4)**
  - Mn/Ni ordering not resolved
  - no DFT+U baseline at the chosen U_eff
  - no calorimetric reference for phase stability
- **`C-03` (BaZrO3:Y)**
  - Y dopant site occupancy unconfirmed
  - no phonon screening at the operating temperature
  - no Kroger-Vink defect inventory
- **`C-04` (CaCu3Ti4O12)**
  - internal barrier layer capacitor mechanism still debated
  - no GW band-edge alignment
  - no spin-orbit coupling check on Ti 3d
- **`C-05` (Co3O4)**
  - reference material, included as calibration anchor
  - no fresh DFT relaxation in the current MLIP basis

