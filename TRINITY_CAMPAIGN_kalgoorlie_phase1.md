# Trinity Campaign — `kalgoorlie_phase1`

> **DRY-RUN ONLY.** This campaign is a design + provenance artefact. No Useful Compute rewards are active. No tasks have been published. No SOST capsule has been broadcast. The proof bundle below is marked `ready_to_register=true` and `registered=false`; broadcasting is a manual operator step that lives outside this engine.

- **Schema**: `trinity-campaign-manifest/v0`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **AOI**: `kalgoorlie`

## Proof bundle

| Anchor | SHA-256 |
| --- | --- |
| scorecard | `836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246` |
| dossier   | `d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf` |
| useful compute plan | `1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49` |
| **campaign**          | `7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df` |

- **ready_to_register**: `True`
- **registered**: `False`
- **dry_run**: `True`

## Objectives

- **Anchor dossier and Useful Compute Plan in a single proof bundle** (`obj_anchor_artefacts`)
    - Bind the two existing reproducible artefacts to one campaign manifest with a single SHA-256 the operator can later register on chain.
- **Surface and rank evidence gaps for this AOI** (`obj_close_evidence_gaps`)
    - Detect every recognised deficiency in the dossier and the plan; map each to a concrete next action with bucket / impact / safety classification.
- **Refuse any action that activates rewards / publishes tasks / touches consensus** (`obj_no_unsafe_automation`)
    - Hard veto via forbidden-substring routing. Such actions land in the unsafe_or_forbidden bucket with the matched substring recorded as the reason.

## Evidence gaps

| Severity | Gap ID | Source | Description |
| --- | --- | --- | --- |
| info | `dry_run_useful_compute_only` | plan | The Useful Compute Plan is dry-run; tasks are classified but not enqueued and no rewards are active. Tracking this as info, not a defect. |
| critical | `fallback_mode_active` | dossier | The dossier ran in fallback mode (no ranked targets in the scorecard). The campaign records this as a data-completeness gap, not a scientific claim. |
| critical | `features_available_zero` | scorecard | scorecard_features_available is 0; no Geaspirit features were processed for this AOI. Any geological interpretation downstream would be unsupported. |
| high | `missing_geophysical_layer` | scorecard | The scorecard's honesty matrix explicitly cites field geophysics (ERT / gravity / magnetics) as what the model cannot see. Without ground-truth geophysical layers the dossier remains a remote-proxy assessment. |
| high | `missing_spectral_evidence` | scorecard | No spectral features were processed and the honesty matrix notes spectral / vegetation limits. Mineral templates cannot be scored against this AOI. |
| high | `no_ranked_targets` | dossier | No mineral_target hypotheses are present; only AOI-level priority reviews. Rankable targets require feature processing first. |
| medium | `weak_council_confidence` | dossier | Average council confidence is 0.55 and at least one review is on hold or contradicted. More evidence is required before any promotion. |

## Next actions (ranked)

### 1. Re-run aoi_to_dossier.py for kalgoorlie once features land

- **Action id**: `act_rerun_dossier`
- **Bucket**: `blocked`
- **Impact**: `high` · **Safety**: `safe`
- **Estimated cost**: seconds once features exist
- **Addresses gaps**: `fallback_mode_active`
- **Prerequisites**: `act_process_geaspirit_features`

> After feature processing, regenerate the dossier so it leaves fallback mode and emits mineral_target reviews. Pinned-time flag keeps the SHA reproducible.

### 2. Process Geaspirit feature layers for the AOI

- **Action id**: `act_process_geaspirit_features`
- **Bucket**: `needs_external_data`
- **Impact**: `critical` · **Safety**: `needs_review`
- **Estimated cost**: hours of operator time + tile downloads
- **Addresses gaps**: `fallback_mode_active`, `features_available_zero`

> Run the Geaspirit feature pipeline for AOI 'kalgoorlie' so features_available rises above 0. Until this lands, the dossier will keep running in fallback mode.

### 3. Heavy task family 'AOI feature tile scoring' — when Useful Compute rewards activate

- **Action id**: `act_uc_family_aoi_tile_scoring`
- **Bucket**: `useful_compute_candidate`
- **Impact**: `high` · **Safety**: `needs_review`
- **Estimated cost**: 300s per task (1536 MB)
- **Addresses gaps**: `dry_run_useful_compute_only`

> Family `aoi_tile_scoring` is classified candidate_reward_worthy in the Useful Compute Plan attached to this campaign. Currently dry-run; not enqueued by Trinity. Future activation requires a separate consensus + governance step the engine does not perform.

### 4. Heavy task family 'Geology-aware negative resampling for Geaspirit' — when Useful Compute rewards activate

- **Action id**: `act_uc_family_geology_aware_negative_resampling`
- **Bucket**: `useful_compute_candidate`
- **Impact**: `high` · **Safety**: `needs_review`
- **Estimated cost**: 150s per task (1024 MB)
- **Addresses gaps**: `dry_run_useful_compute_only`

> Family `geology_aware_negative_resampling` is classified candidate_reward_worthy in the Useful Compute Plan attached to this campaign. Currently dry-run; not enqueued by Trinity. Future activation requires a separate consensus + governance step the engine does not perform.

### 5. Heavy task family 'Spectral template scoring' — when Useful Compute rewards activate

- **Action id**: `act_uc_family_spectral_template_scoring`
- **Bucket**: `useful_compute_candidate`
- **Impact**: `high` · **Safety**: `needs_review`
- **Estimated cost**: 240s per task (1024 MB)
- **Addresses gaps**: `dry_run_useful_compute_only`

> Family `spectral_template_scoring` is classified candidate_reward_worthy in the Useful Compute Plan attached to this campaign. Currently dry-run; not enqueued by Trinity. Future activation requires a separate consensus + governance step the engine does not perform.

### 6. Ingest field geophysical layers (ERT / gravity / magnetics)

- **Action id**: `act_ingest_geophysics`
- **Bucket**: `needs_external_data`
- **Impact**: `high` · **Safety**: `needs_review`
- **Estimated cost**: external dataset acquisition + ingestion time
- **Addresses gaps**: `missing_geophysical_layer`

> The scorecard cannot replace field geophysics on its own. Operator must source local geophysical datasets and feed them into the Geaspirit feature stack.

### 7. Score Sentinel-2 / EMIT spectral tiles via Useful Compute

- **Action id**: `act_spectral_template_scoring`
- **Bucket**: `useful_compute_candidate`
- **Impact**: `high` · **Safety**: `needs_review`
- **Estimated cost**: dry-run today; future paid family
- **Addresses gaps**: `missing_spectral_evidence`
- **Prerequisites**: `act_process_geaspirit_features`

> Spectral template scoring is a candidate_reward_worthy Useful Compute family in the plan. Once features are available, the task can be enqueued for cross-worker verification.

### 8. Manual operator review of all council hold/contradicted reviews

- **Action id**: `act_review_weak_council`
- **Bucket**: `needs_operator_review`
- **Impact**: `medium` · **Safety**: `needs_review`
- **Estimated cost**: operator attention
- **Addresses gaps**: `weak_council_confidence`

> Open every review marked hold or contradicted and decide whether to retire, rewrite, or escalate. Council confidence won't rise on its own.

### 9. Activate Useful Compute rewards

- **Action id**: `act_no_activate_rewards`
- **Bucket**: `unsafe_or_forbidden`
- **Impact**: `critical` · **Safety**: `forbidden`
- **Forbidden reason**: matched forbidden substring: 'activate useful compute reward'
- **Estimated cost**: n/a — refused

> Activate Useful Compute rewards for any family. The engine never does this; rewards activation requires a separate consensus / governance procedure.

### 10. Modify consensus / miner / node / RPC

- **Action id**: `act_no_modify_consensus`
- **Bucket**: `unsafe_or_forbidden`
- **Impact**: `critical` · **Safety**: `forbidden`
- **Forbidden reason**: matched forbidden substring: 'modify consensus'
- **Estimated cost**: n/a — refused

> Modify consensus, miner, node, or RPC schema. The engine is strictly out of those layers.

### 11. Move funds from the wallet

- **Action id**: `act_no_move_funds`
- **Bucket**: `unsafe_or_forbidden`
- **Impact**: `critical` · **Safety**: `forbidden`
- **Forbidden reason**: matched forbidden substring: 'move funds'
- **Estimated cost**: n/a — refused

> Move funds. The engine touches no wallet, no key, no transaction broadcast path.

### 12. Publish reward-bearing tasks to the public Useful Compute API

- **Action id**: `act_no_publish_reward_tasks`
- **Bucket**: `unsafe_or_forbidden`
- **Impact**: `critical` · **Safety**: `forbidden`
- **Forbidden reason**: matched forbidden substring: 'publish reward-bearing'
- **Estimated cost**: n/a — refused

> Publish reward-bearing tasks to the public Useful Compute API. The engine never publishes; the worker remains untouched.

### 13. Register hash on chain automatically

- **Action id**: `act_no_register_on_chain`
- **Bucket**: `unsafe_or_forbidden`
- **Impact**: `critical` · **Safety**: `forbidden`
- **Forbidden reason**: matched forbidden substring: 'register hash on chain'
- **Estimated cost**: n/a — refused

> Auto-register hash on chain. The engine produces a ready-to-register proof bundle; broadcasting the capsule is an operator-driven step outside this module.


## Useful Compute candidate queue (mirrored, dry-run)

| Family | Project | Runtime (s) | Memory (MB) | N workers |
| --- | --- | --- | --- | --- |
| `aoi_tile_scoring` | `geaspirit` | 300.0 | 1536.0 | 2 |
| `geology_aware_negative_resampling` | `geaspirit` | 150.0 | 1024.0 | 2 |
| `spectral_template_scoring` | `geaspirit` | 240.0 | 1024.0 | 2 |

_All entries above are dry-run; no task is enqueued, no reward is active, the public Useful Compute API is untouched._

## Safety status

- `dry_run`: `True`
- `engine_version`: `trinity-campaign-manifest/v0`
- `no_chain_broadcast`: `True`
- `no_consensus_modification`: `True`
- `no_public_publication`: `True`
- `no_rewards_active`: `True`
- `no_wallet_action`: `True`
- `no_worker_modification`: `True`

## What this document is NOT

- This is **not** an announcement of active Useful Compute rewards.
- This is **not** a published task list on the public Useful Compute API.
- This is **not** a broadcasted SOST capsule. The campaign SHA-256 is ready to register; broadcasting it is a manual operator step.
- This is **not** a geological conclusion. Every evidence gap and every next action sits behind human review.

