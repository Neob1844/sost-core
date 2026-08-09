# Trinity / Geo Discovery — Useful Compute Plan `global_phase1`

> **DRY-RUN plan.** Proposes heavy compute / data tasks per AOI for the next campaign iteration. Useful Compute rewards are **not** active; no task in this document is enqueued, paid or published. Remote proxy evidence only; not a mineral reserve claim.

- **Schema**: `trinity-geo-uc-plan/v0.1`
- **Track**: `geaspirit`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `dossier_basename`: `TRINITY_GEO_DOSSIER_global_phase1.json`
  - `dossier_sha256`: `8eea473a272e4b651868d63e5a11307397ad3e9ecf71f74c11593f53e1c1ac97`

## Safety status

- `dry_run`: `True`
- `no_auto_publish`: `True`
- `no_chain_broadcast`: `True`
- `no_consensus_modification`: `True`
- `no_rewards_active`: `True`

## Summary

- **aois_total**: `90`
- **tasks_total**: `245`
- **by_classification**:
  - `candidate_reward_worthy`: `140`
  - `deferred`: `105`
  - `not_reward_worthy`: `0`

## Per-AOI proposals (first 30)

### `GEO-0027` &mdash; region `south_america_andes` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0027 (south_america_andes) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0027 (south_america_andes) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0027 (south_america_andes): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0027 (south_america_andes): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0045` &mdash; region `south_america_andes` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0045 (south_america_andes) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0045 (south_america_andes) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0045 (south_america_andes): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0045 (south_america_andes): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0005` &mdash; region `north_america_carlin` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0005 (north_america_carlin) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0005 (north_america_carlin) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0070` &mdash; region `north_america_carlin` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0070 (north_america_carlin) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0070 (north_america_carlin) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0070 (north_america_carlin): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0070 (north_america_carlin): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0085` &mdash; region `north_america_carlin` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0085 (north_america_carlin) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0085 (north_america_carlin) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0023` &mdash; region `south_america_andes` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0023 (south_america_andes) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0023 (south_america_andes) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0023 (south_america_andes): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0023 (south_america_andes): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0067` &mdash; region `south_america_andes` &mdash; dossier REJECT

- `cross_worker_descriptor_validation` &mdash; **candidate_reward_worthy** (~40 min)
  - GEO-0067 (south_america_andes) rejected by council; keep as a calibration anchor in the descriptor cross-check pool (deferred work, not reward-worthy on its own).

### `GEO-0008` &mdash; region `australia_lachlan` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0008 (australia_lachlan) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0008 (australia_lachlan) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0035` &mdash; region `north_america_sierra_nevada` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0035 (north_america_sierra_nevada) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0035 (north_america_sierra_nevada) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0068` &mdash; region `australia_lachlan` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0068 (australia_lachlan) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0068 (australia_lachlan) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0068 (australia_lachlan): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0068 (australia_lachlan): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0079` &mdash; region `australia_lachlan` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0079 (australia_lachlan) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0079 (australia_lachlan) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0034` &mdash; region `australia_yilgarn` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0034 (australia_yilgarn) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0034 (australia_yilgarn) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0034 (australia_yilgarn): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0034 (australia_yilgarn): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0100` &mdash; region `north_america_sierra_nevada` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0100 (north_america_sierra_nevada) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0100 (north_america_sierra_nevada) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0100 (north_america_sierra_nevada): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0100 (north_america_sierra_nevada): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0039` &mdash; region `north_america_trans_hudson` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0039 (north_america_trans_hudson) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0039 (north_america_trans_hudson) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0039 (north_america_trans_hudson): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0039 (north_america_trans_hudson): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0036` &mdash; region `asia_tethyan` &mdash; dossier REJECT

- `cross_worker_descriptor_validation` &mdash; **candidate_reward_worthy** (~40 min)
  - GEO-0036 (asia_tethyan) rejected by council; keep as a calibration anchor in the descriptor cross-check pool (deferred work, not reward-worthy on its own).

### `GEO-0041` &mdash; region `asia_tethyan` &mdash; dossier REJECT

- `cross_worker_descriptor_validation` &mdash; **candidate_reward_worthy** (~40 min)
  - GEO-0041 (asia_tethyan) rejected by council; keep as a calibration anchor in the descriptor cross-check pool (deferred work, not reward-worthy on its own).

### `GEO-0053` &mdash; region `asia_tethyan` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0053 (asia_tethyan) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0053 (asia_tethyan) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0058` &mdash; region `asia_tethyan` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0058 (asia_tethyan) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0058 (asia_tethyan) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0058 (asia_tethyan): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0058 (asia_tethyan): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0065` &mdash; region `asia_tethyan` &mdash; dossier REJECT

- `cross_worker_descriptor_validation` &mdash; **candidate_reward_worthy** (~40 min)
  - GEO-0065 (asia_tethyan) rejected by council; keep as a calibration anchor in the descriptor cross-check pool (deferred work, not reward-worthy on its own).

### `GEO-0092` &mdash; region `asia_tethyan` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0092 (asia_tethyan) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0092 (asia_tethyan) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0095` &mdash; region `asia_tethyan` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0095 (asia_tethyan) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0095 (asia_tethyan) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0019` &mdash; region `north_america_superior` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0019 (north_america_superior) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0019 (north_america_superior) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0040` &mdash; region `australia_yilgarn` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0040 (australia_yilgarn) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0040 (australia_yilgarn) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0040 (australia_yilgarn): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0040 (australia_yilgarn): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0071` &mdash; region `europe_iberian_pyrite` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0071 (europe_iberian_pyrite) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0071 (europe_iberian_pyrite) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0071 (europe_iberian_pyrite): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0071 (europe_iberian_pyrite): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0001` &mdash; region `australia_yilgarn` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0001 (australia_yilgarn) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0001 (australia_yilgarn) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0001 (australia_yilgarn): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0001 (australia_yilgarn): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0049` &mdash; region `north_america_trans_hudson` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0049 (north_america_trans_hudson) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0049 (north_america_trans_hudson) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0081` &mdash; region `north_america_trans_hudson` &mdash; dossier ACCEPT

- `satellite_tile_preprocessing` &mdash; **candidate_reward_worthy** (~45 min)
  - GEO-0081 (north_america_trans_hudson) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- `spectral_anomaly_scoring` &mdash; **candidate_reward_worthy** (~60 min)
  - GEO-0081 (north_america_trans_hudson) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0081 (north_america_trans_hudson): DEM-derived layers contextualise the spectral anomalies against structural / topographic features. (deferred: family marked heavy_enough=False)
- `geophysics_layer_fusion` &mdash; **candidate_reward_worthy** (~90 min)
  - GEO-0081 (north_america_trans_hudson): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.

### `GEO-0091` &mdash; region `north_america_trans_hudson` &mdash; dossier REJECT

- `cross_worker_descriptor_validation` &mdash; **candidate_reward_worthy** (~40 min)
  - GEO-0091 (north_america_trans_hudson) rejected by council; keep as a calibration anchor in the descriptor cross-check pool (deferred work, not reward-worthy on its own).

### `GEO-0009` &mdash; region `africa_bushveld` &mdash; dossier HOLD

- `dem_terrain_derivatives` &mdash; **deferred** (~10 min)
  - GEO-0009 (africa_bushveld) on hold; DEM derivatives are the cheapest layer that adds independent structural context for the next council pass. (deferred: family marked heavy_enough=False)
- `uncertainty_estimation` &mdash; **deferred** (~15 min)
  - GEO-0009 (africa_bushveld) on hold; surfacing per-layer uncertainty helps the operator decide whether to invest in heavier preprocessing. (deferred: family marked heavy_enough=False)

### `GEO-0006` &mdash; region `asia_tethyan` &mdash; dossier REJECT

- `cross_worker_descriptor_validation` &mdash; **candidate_reward_worthy** (~40 min)
  - GEO-0006 (asia_tethyan) rejected by council; keep as a calibration anchor in the descriptor cross-check pool (deferred work, not reward-worthy on its own).

