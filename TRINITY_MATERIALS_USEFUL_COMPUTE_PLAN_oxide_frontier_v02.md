# Trinity / Materials Track — Useful Compute Plan `oxide_frontier_v02`

> **DRY-RUN plan.** Proposes heavy compute tasks per candidate for the next campaign iteration. Useful Compute rewards are **not** active; no task in this document is enqueued, paid or published.

- **Schema**: `trinity-materials-uc-plan/v0`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `dossier_basename`: `TRINITY_MATERIALS_DOSSIER_oxide_frontier_v02.json`
  - `dossier_sha256`: `87a5db2d164d32898b5438a4c350497cd2af278dc02f9a0be730fb653461f3fb`

## Safety status

- `dry_run`: `True`
- `no_auto_publish`: `True`
- `no_chain_broadcast`: `True`
- `no_consensus_modification`: `True`
- `no_rewards_active`: `True`

## Summary

- **candidates_total**: `8`
- **tasks_total**: `15`
- **by_classification**:
  - `candidate_reward_worthy`: `7`
  - `deferred`: `8`
  - `not_reward_worthy`: `0`

## Per-candidate proposals

### `MX-0016` &mdash; SrTiO3 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - MX-0016 (SrTiO3) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - MX-0016 (SrTiO3) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `MX-0001` &mdash; NiAl2O4 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - MX-0001 (NiAl2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - MX-0001 (NiAl2O4) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `MX-0021` &mdash; CaZrO3 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - MX-0021 (CaZrO3) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - MX-0021 (CaZrO3) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `MX-0009` &mdash; ZnCr2O4 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - MX-0009 (ZnCr2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - MX-0009 (ZnCr2O4) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `MX-0005` &mdash; CuCr2O4 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - MX-0005 (CuCr2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - MX-0005 (CuCr2O4) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `MX-0008` &mdash; MnAl2O4 (dossier: REJECT)

- `mlip_force_field_validation` &mdash; **deferred** (~25 min)
  - MX-0008 (MnAl2O4) was rejected as a discovery target but is still useful as a benchmark anchor for the MLIP cross-check; classified deferred, not reward-worthy (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `MX-0013` &mdash; FeGa2O4 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - MX-0013 (FeGa2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - MX-0013 (FeGa2O4) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `MX-0010` &mdash; NiFe2O4 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - MX-0010 (NiFe2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - MX-0010 (NiFe2O4) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

