# Trinity / Materials Track — Dossier `novel_frontier_phase1`

> **DRY-RUN dossier.** Mock AI Council reviews of the candidate set declared in the materials scorecard. Not a materials discovery claim. Decisions follow strictest-member-wins with validator-veto tracking.

- **Schema**: `trinity-materials-dossier/v0`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `features_available`: `0`
  - `mode`: `mock`
  - `scorecard_basename`: `TRINITY_MATERIALS_SCORECARD_novel_frontier_phase1.json`
  - `scorecard_sha256`: `7355afc86a4056c7b87b15b4125fbecc7dcfab2fa15ffb7fc0b2d2f1c1e4f9f8`

## Summary

- **candidates_total**: `5`
- **decisions_accept**: `0`
- **decisions_hold**: `4`
- **decisions_reject**: `1`
- **validator_vetoes_applied**: `0`

## Hypotheses

### `C-01` &mdash; Fe2MgO4 (spinel oxide) &mdash; **HOLD**

- seed_novelty=`0.62`, seed_frontier_proximity=`0.71`, veto_applied=`False`
- **Reviews**:
  - `validator`: **accept** &mdash; frontier_proximity 0.71 and novelty 0.62 both clear validator thresholds (0.70 / 0.60)
  - `materials_expert`: **hold** &mdash; 3 open synthesis / characterization questions; more than the 2 a v0 mock reviewer is willing to advance past hold
  - `novelty_judge`: **accept** &mdash; seed_novelty 0.62 >= 0.55; frontier-worthy in the v0 mock scale
- **Evidence gaps**:
  - no measured formation energy on file
  - no MLIP relaxation baseline
  - no synthesised polymorph reference for ferrimagnetic ordering

### `C-02` &mdash; LiNi0.5Mn1.5O4 (layered oxide / cathode candidate) &mdash; **HOLD**

- seed_novelty=`0.48`, seed_frontier_proximity=`0.59`, veto_applied=`False`
- **Reviews**:
  - `validator`: **hold** &mdash; insufficient baseline; frontier_proximity 0.59 or novelty 0.48 below accept thresholds but above the reject floor
  - `materials_expert`: **hold** &mdash; 3 open synthesis / characterization questions; more than the 2 a v0 mock reviewer is willing to advance past hold
  - `novelty_judge`: **hold** &mdash; seed_novelty 0.48 in [0.40, 0.55); not enough novelty to advance in v0 mock
- **Evidence gaps**:
  - Mn/Ni ordering not resolved
  - no DFT+U baseline at the chosen U_eff
  - no calorimetric reference for phase stability

### `C-03` &mdash; BaZrO3:Y (perovskite / proton conductor) &mdash; **HOLD**

- seed_novelty=`0.55`, seed_frontier_proximity=`0.66`, veto_applied=`False`
- **Reviews**:
  - `validator`: **hold** &mdash; insufficient baseline; frontier_proximity 0.66 or novelty 0.55 below accept thresholds but above the reject floor
  - `materials_expert`: **hold** &mdash; 3 open synthesis / characterization questions; more than the 2 a v0 mock reviewer is willing to advance past hold
  - `novelty_judge`: **accept** &mdash; seed_novelty 0.55 >= 0.55; frontier-worthy in the v0 mock scale
- **Evidence gaps**:
  - Y dopant site occupancy unconfirmed
  - no phonon screening at the operating temperature
  - no Kroger-Vink defect inventory

### `C-04` &mdash; CaCu3Ti4O12 (giant-permittivity oxide) &mdash; **HOLD**

- seed_novelty=`0.41`, seed_frontier_proximity=`0.52`, veto_applied=`False`
- **Reviews**:
  - `validator`: **hold** &mdash; insufficient baseline; frontier_proximity 0.52 or novelty 0.41 below accept thresholds but above the reject floor
  - `materials_expert`: **hold** &mdash; 3 open synthesis / characterization questions; more than the 2 a v0 mock reviewer is willing to advance past hold
  - `novelty_judge`: **hold** &mdash; seed_novelty 0.41 in [0.40, 0.55); not enough novelty to advance in v0 mock
- **Evidence gaps**:
  - internal barrier layer capacitor mechanism still debated
  - no GW band-edge alignment
  - no spin-orbit coupling check on Ti 3d

### `C-05` &mdash; Co3O4 (transition-metal oxide reference) &mdash; **REJECT**

- seed_novelty=`0.30`, seed_frontier_proximity=`0.40`, veto_applied=`False`
- **Reviews**:
  - `validator`: **reject** &mdash; frontier_proximity 0.40 and/or novelty 0.30 below calibration floor (0.50 / 0.35)
  - `materials_expert`: **hold** &mdash; family 'transition-metal oxide reference' marked as reference / calibration anchor; not advanced past hold without an explicit campaign goal
  - `novelty_judge`: **reject** &mdash; seed_novelty 0.30 < 0.40; treated as calibration / reference, not a discovery candidate
- **Evidence gaps**:
  - reference material, included as calibration anchor
  - no fresh DFT relaxation in the current MLIP basis

