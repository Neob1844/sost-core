# Trinity / Materials Track — Campaign Manifest `novel_frontier_phase1`

> **DRY-RUN manifest.** Composes the dossier and the Useful Compute plan into one campaign with explicit evidence-gap inventory and 6-bucket next-actions. ``ready_to_register=true`` but ``registered=false``; on-chain anchoring is a separate operator decision.

- **Schema**: `trinity-materials-campaign/v0`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `dossier_basename`: `TRINITY_MATERIALS_DOSSIER_novel_frontier_phase1.json`
  - `dossier_sha256`: `2d266fb607e3bbd130b70b7185545e4746df2d1da2fd0fca3f5b640d8a48b9f8`
  - `plan_basename`: `TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_novel_frontier_phase1.json`
  - `plan_sha256`: `4b9a0aa16e8f68c3b4510e3a795bf4fdd31cf739ad08e6596f86d8796dbcc5ac`

## Safety status

- `dry_run`: `True`
- `no_chain_broadcast`: `True`
- `no_consensus_modification`: `True`
- `no_public_publication`: `True`
- `no_rewards_active`: `True`
- `no_wallet_action`: `True`
- `ready_to_register`: `True`
- `registered`: `False`

## Evidence-gap inventory (closed taxonomy)

- `gap_no_dft_relaxation_baseline` &mdash; No DFT relaxation baseline (observed in 3 candidates)
- `gap_no_mlip_baseline` &mdash; No MLIP baseline / cross-validation (observed in 2 candidates)
- `gap_no_phonon_screening` &mdash; No phonon ground-state screening (observed in 1 candidate)
- `gap_no_synthesis_record` &mdash; No synthesised polymorph / reference sample (observed in 1 candidate)
- `gap_no_calorimetric_reference` &mdash; No calorimetric / phase-stability reference (observed in 1 candidate)
- `gap_unresolved_atomic_ordering` &mdash; Unresolved site occupancy / atomic ordering (observed in 3 candidates)
- `gap_no_band_edge_alignment` &mdash; No GW / band-edge alignment (observed in 1 candidate)
- `gap_no_defect_inventory` &mdash; No Kroger-Vink defect inventory (observed in 1 candidate)
- `gap_mechanism_debated` &mdash; Proposed property mechanism still debated (observed in 1 candidate)
- `gap_no_spin_orbit_check` &mdash; No spin-orbit coupling check (observed in 1 candidate)

## Next actions, ranked

- **Useful-Compute candidate task: MLIP geometry relaxation for Fe2MgO4** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `C-01_uc_mlip_relaxation`
  - C-01 (Fe2MgO4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for LiNi0.5Mn1.5O4** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `C-02_uc_mlip_relaxation`
  - C-02 (LiNi0.5Mn1.5O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for BaZrO3:Y** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `C-03_uc_mlip_relaxation`
  - C-03 (BaZrO3:Y) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for CaCu3Ti4O12** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `C-04_uc_mlip_relaxation`
  - C-04 (CaCu3Ti4O12) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Look up atomic ordering data for Fe2MgO4** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `C-01_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Look up atomic ordering data for LiNi0.5Mn1.5O4** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `C-02_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Look up atomic ordering data for BaZrO3:Y** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `C-03_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Operator review: mechanism debate for CaCu3Ti4O12** &mdash; bucket `needs_operator_review` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `C-04_review_mechanism`
  - Literature mechanism for the property of interest is debated; operator should pin a working hypothesis before further compute is spent.
- **Calibration-only use of Co3O4** &mdash; bucket `needs_operator_review` &mdash; safety `safe` &mdash; impact `low` &mdash; id `C-05_calibration_use`
  - Rejected as a discovery candidate; keep on file as a calibration / benchmark anchor for the MLIP cross-check.
- **Log open evidence gaps for LiNi0.5Mn1.5O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `C-02_log_open_gaps`
  - Record the open evidence gaps ['gap_no_calorimetric_reference', 'gap_no_dft_relaxation_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for BaZrO3:Y** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `C-03_log_open_gaps`
  - Record the open evidence gaps ['gap_no_defect_inventory', 'gap_no_phonon_screening'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for CaCu3Ti4O12** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `C-04_log_open_gaps`
  - Record the open evidence gaps ['gap_no_band_edge_alignment', 'gap_no_spin_orbit_check'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for Co3O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `C-05_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for Fe2MgO4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `C-01_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline', 'gap_no_synthesis_record'] in the campaign log so future iterations can target them explicitly.
- **Do not activate Useful Compute rewards** &mdash; bucket `unsafe_or_forbidden` &mdash; safety `unsafe` &mdash; impact `none` &mdash; id `act_no_activate_rewards`
  - Useful Compute rewards stay dry-run until a separate consensus / governance procedure ships. The engine never flips that switch.
- **Do not modify consensus** &mdash; bucket `unsafe_or_forbidden` &mdash; safety `unsafe` &mdash; impact `none` &mdash; id `act_no_modify_consensus`
  - Consensus rules, miner code, node code and the RPC schema are strictly out of scope. No Trinity script can touch them.
- **Do not move funds** &mdash; bucket `unsafe_or_forbidden` &mdash; safety `unsafe` &mdash; impact `none` &mdash; id `act_no_move_funds`
  - The engine touches no wallet, no key, no transaction broadcast path. Funds never leave the operator's address.
- **Do not publish reward-bearing tasks** &mdash; bucket `unsafe_or_forbidden` &mdash; safety `unsafe` &mdash; impact `none` &mdash; id `act_no_publish_reward_tasks`
  - The public Useful Compute worker / API is unchanged. The engine never enqueues a paid task there.
- **Do not register on chain without operator decision** &mdash; bucket `unsafe_or_forbidden` &mdash; safety `unsafe` &mdash; impact `none` &mdash; id `act_no_register_on_chain_without_operator`
  - Capsule registration is the operator's manual decision. The engine prepares a ready-to-register bundle and stops; broadcasting requires an explicit operator step.

