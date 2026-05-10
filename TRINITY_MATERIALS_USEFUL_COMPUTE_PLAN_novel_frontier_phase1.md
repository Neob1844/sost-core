# Trinity / Materials Track — Useful Compute Plan `novel_frontier_phase1`

> **DRY-RUN plan.** Proposes heavy compute tasks per candidate for the next campaign iteration. Useful Compute rewards are **not** active; no task in this document is enqueued, paid or published.

- **Schema**: `trinity-materials-uc-plan/v0`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `dossier_basename`: `TRINITY_MATERIALS_DOSSIER_novel_frontier_phase1.json`
  - `dossier_sha256`: `2d266fb607e3bbd130b70b7185545e4746df2d1da2fd0fca3f5b640d8a48b9f8`

## Safety status

- `dry_run`: `True`
- `no_auto_publish`: `True`
- `no_chain_broadcast`: `True`
- `no_consensus_modification`: `True`
- `no_rewards_active`: `True`

## Summary

- **candidates_total**: `5`
- **tasks_total**: `9`
- **by_classification**:
  - `candidate_reward_worthy`: `4`
  - `deferred`: `5`
  - `not_reward_worthy`: `0`

## Per-candidate proposals

### `C-01` &mdash; Fe2MgO4 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - C-01 (Fe2MgO4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - C-01 (Fe2MgO4) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `C-02` &mdash; LiNi0.5Mn1.5O4 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - C-02 (LiNi0.5Mn1.5O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - C-02 (LiNi0.5Mn1.5O4) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `C-03` &mdash; BaZrO3:Y (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - C-03 (BaZrO3:Y) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - C-03 (BaZrO3:Y) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `C-04` &mdash; CaCu3Ti4O12 (dossier: HOLD)

- `mlip_relaxation` &mdash; **candidate_reward_worthy** (~30 min)
  - C-04 (CaCu3Ti4O12) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- `dft_input_preparation` &mdash; **deferred** (~5 min)
  - C-04 (CaCu3Ti4O12) needs canonical DFT input files for the follow-up real-DFT run that would resolve the hold (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

### `C-05` &mdash; Co3O4 (dossier: REJECT)

- `mlip_force_field_validation` &mdash; **deferred** (~25 min)
  - C-05 (Co3O4) was rejected as a discovery target but is still useful as a benchmark anchor for the MLIP cross-check; classified deferred, not reward-worthy (deferred: family marked heavy_enough=False; not large enough to be reward-worthy in v0)

