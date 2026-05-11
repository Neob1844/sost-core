# Trinity / Materials Track — Campaign Manifest `oxide_frontier_v02`

> **DRY-RUN manifest.** Composes the dossier and the Useful Compute plan into one campaign with explicit evidence-gap inventory and 6-bucket next-actions. ``ready_to_register=true`` but ``registered=false``; on-chain anchoring is a separate operator decision.

- **Schema**: `trinity-materials-campaign/v0`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `dossier_basename`: `TRINITY_MATERIALS_DOSSIER_oxide_frontier_v02.json`
  - `dossier_sha256`: `87a5db2d164d32898b5438a4c350497cd2af278dc02f9a0be730fb653461f3fb`
  - `plan_basename`: `TRINITY_MATERIALS_USEFUL_COMPUTE_PLAN_oxide_frontier_v02.json`
  - `plan_sha256`: `31eefb9382dd226d0d94fcf99634f4af8608811a242fbcd84a68c5b127b39e29`

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

- `gap_no_dft_relaxation_baseline` &mdash; No DFT relaxation baseline (observed in 8 candidates)
- `gap_no_mlip_baseline` &mdash; No MLIP baseline / cross-validation (observed in 6 candidates)
- `gap_no_phonon_screening` &mdash; No phonon ground-state screening (observed in 2 candidates)
- `gap_no_synthesis_record` &mdash; No synthesised polymorph / reference sample (observed in 0 candidates)
- `gap_no_calorimetric_reference` &mdash; No calorimetric / phase-stability reference (observed in 0 candidates)
- `gap_unresolved_atomic_ordering` &mdash; Unresolved site occupancy / atomic ordering (observed in 6 candidates)
- `gap_no_band_edge_alignment` &mdash; No GW / band-edge alignment (observed in 0 candidates)
- `gap_no_defect_inventory` &mdash; No Kroger-Vink defect inventory (observed in 0 candidates)
- `gap_mechanism_debated` &mdash; Proposed property mechanism still debated (observed in 0 candidates)
- `gap_no_spin_orbit_check` &mdash; No spin-orbit coupling check (observed in 0 candidates)

## Next actions, ranked

- **Useful-Compute candidate task: MLIP geometry relaxation for NiAl2O4** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `MX-0001_uc_mlip_relaxation`
  - MX-0001 (NiAl2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for CuCr2O4** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `MX-0005_uc_mlip_relaxation`
  - MX-0005 (CuCr2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for ZnCr2O4** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `MX-0009_uc_mlip_relaxation`
  - MX-0009 (ZnCr2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for NiFe2O4** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `MX-0010_uc_mlip_relaxation`
  - MX-0010 (NiFe2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for FeGa2O4** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `MX-0013_uc_mlip_relaxation`
  - MX-0013 (FeGa2O4) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for SrTiO3** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `MX-0016_uc_mlip_relaxation`
  - MX-0016 (SrTiO3) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Useful-Compute candidate task: MLIP geometry relaxation for CaZrO3** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `MX-0021_uc_mlip_relaxation`
  - MX-0021 (CaZrO3) is on hold pending a low-energy reference geometry; an MLIP relaxation is the cheapest and most informative first step
- **Look up atomic ordering data for NiAl2O4** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `MX-0001_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Look up atomic ordering data for CuCr2O4** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `MX-0005_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Look up atomic ordering data for ZnCr2O4** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `MX-0009_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Look up atomic ordering data for NiFe2O4** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `MX-0010_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Look up atomic ordering data for FeGa2O4** &mdash; bucket `needs_external_data` &mdash; safety `safe` &mdash; impact `medium` &mdash; id `MX-0013_external_ordering`
  - Site occupancy / cation ordering should be sourced from a public crystallographic database (ICSD, Materials Project) before further DFT investment.
- **Calibration-only use of MnAl2O4** &mdash; bucket `needs_operator_review` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0008_calibration_use`
  - Rejected as a discovery candidate; keep on file as a calibration / benchmark anchor for the MLIP cross-check.
- **Log open evidence gaps for NiAl2O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0001_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for CuCr2O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0005_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for MnAl2O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0008_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for ZnCr2O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0009_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for NiFe2O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0010_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for FeGa2O4** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0013_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_mlip_baseline'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for SrTiO3** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0016_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_phonon_screening'] in the campaign log so future iterations can target them explicitly.
- **Log open evidence gaps for CaZrO3** &mdash; bucket `immediate_local` &mdash; safety `safe` &mdash; impact `low` &mdash; id `MX-0021_log_open_gaps`
  - Record the open evidence gaps ['gap_no_dft_relaxation_baseline', 'gap_no_phonon_screening'] in the campaign log so future iterations can target them explicitly.
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

