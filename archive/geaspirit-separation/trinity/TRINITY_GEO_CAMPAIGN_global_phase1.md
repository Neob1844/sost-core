# Trinity / Geo Discovery — Campaign Manifest `global_phase1`

> **DRY-RUN manifest.** Composes the geo dossier and the geo Useful Compute plan into one campaign with explicit evidence-gap inventory and 6-bucket next-actions. ``ready_to_register=true`` but ``registered=false``; on-chain anchoring is a separate operator decision. Remote proxy evidence only; not a mineral reserve claim.

- **Schema**: `trinity-geo-campaign/v0.1`
- **Track**: `geaspirit`
- **Commodity**: `copper_gold_critical_minerals`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `dossier_basename`: `TRINITY_GEO_DOSSIER_global_phase1.json`
  - `dossier_sha256`: `8eea473a272e4b651868d63e5a11307397ad3e9ecf71f74c11593f53e1c1ac97`
  - `plan_basename`: `TRINITY_GEO_USEFUL_COMPUTE_PLAN_global_phase1.json`
  - `plan_sha256`: `44e731fee8066a8ef57edd77b097fd55a172f7ae94797b3437cf306eb4f236d2`

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

- `gap_no_field_validation` &mdash; No field validation on file (observed in 180 AOIs)
- `gap_no_drilling_evidence` &mdash; No drilling evidence on file (observed in 180 AOIs)
- `gap_no_geophysics` &mdash; No geophysics survey lines on file (observed in 180 AOIs)
- `gap_no_geological_mapping` &mdash; No detailed geological mapping (observed in 90 AOIs)
- `gap_no_soil_geochemistry` &mdash; No soil-geochemistry transect (observed in 180 AOIs)
- `gap_protected_area_legal_unknown` &mdash; Protected / legally-uncertain area (observed in 0 AOIs)
- `gap_low_data_availability` &mdash; Low public data availability for region (observed in 0 AOIs)
- `gap_too_close_to_known_demo` &mdash; Too close to a v0 demo AOI (observed in 0 AOIs)

## Top 30 next actions (ranked)

- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0001** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0001_uc_geophysics_layer_fusion`
  - GEO-0001 (australia_yilgarn): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0001** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0001_uc_satellite_tile_preprocessing`
  - GEO-0001 (australia_yilgarn) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0001** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0001_uc_spectral_anomaly_scoring`
  - GEO-0001 (australia_yilgarn) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0002** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0002_uc_geophysics_layer_fusion`
  - GEO-0002 (asia_caob): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0002** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0002_uc_satellite_tile_preprocessing`
  - GEO-0002 (asia_caob) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0002** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0002_uc_spectral_anomaly_scoring`
  - GEO-0002 (asia_caob) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0003** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0003_uc_geophysics_layer_fusion`
  - GEO-0003 (south_america_brazilian_shield): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0003** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0003_uc_satellite_tile_preprocessing`
  - GEO-0003 (south_america_brazilian_shield) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0003** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0003_uc_spectral_anomaly_scoring`
  - GEO-0003 (south_america_brazilian_shield) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0004** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0004_uc_geophysics_layer_fusion`
  - GEO-0004 (pacific_rim_ne_asia): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0004** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0004_uc_satellite_tile_preprocessing`
  - GEO-0004 (pacific_rim_ne_asia) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0004** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0004_uc_spectral_anomaly_scoring`
  - GEO-0004 (pacific_rim_ne_asia) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0010** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0010_uc_geophysics_layer_fusion`
  - GEO-0010 (europe_skellefte): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0010** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0010_uc_satellite_tile_preprocessing`
  - GEO-0010 (europe_skellefte) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0010** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0010_uc_spectral_anomaly_scoring`
  - GEO-0010 (europe_skellefte) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0011** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0011_uc_geophysics_layer_fusion`
  - GEO-0011 (caribbean_nickel): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0011** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0011_uc_satellite_tile_preprocessing`
  - GEO-0011 (caribbean_nickel) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0011** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0011_uc_spectral_anomaly_scoring`
  - GEO-0011 (caribbean_nickel) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0012** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0012_uc_geophysics_layer_fusion`
  - GEO-0012 (central_america_volcanic_arc): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0012** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0012_uc_satellite_tile_preprocessing`
  - GEO-0012 (central_america_volcanic_arc) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0012** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0012_uc_spectral_anomaly_scoring`
  - GEO-0012 (central_america_volcanic_arc) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0016** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0016_uc_geophysics_layer_fusion`
  - GEO-0016 (arctic_greenland_east): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0016** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0016_uc_satellite_tile_preprocessing`
  - GEO-0016 (arctic_greenland_east) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0016** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0016_uc_spectral_anomaly_scoring`
  - GEO-0016 (arctic_greenland_east) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0020** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0020_uc_geophysics_layer_fusion`
  - GEO-0020 (europe_skellefte): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0020** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0020_uc_satellite_tile_preprocessing`
  - GEO-0020 (europe_skellefte) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0020** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0020_uc_spectral_anomaly_scoring`
  - GEO-0020 (europe_skellefte) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
- **Useful-Compute candidate task: Geophysics layer fusion (gravity, magnetics) for GEO-0021** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0021_uc_geophysics_layer_fusion`
  - GEO-0021 (asia_sukhoi_log): geophysics fusion provides depth-sensitive evidence beyond the surface-only satellite signals.
- **Useful-Compute candidate task: Sentinel / Landsat tile preprocessing for GEO-0021** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0021_uc_satellite_tile_preprocessing`
  - GEO-0021 (asia_sukhoi_log) accepted by council; the first useful work is to preprocess the AOI's Sentinel / Landsat tiles so every downstream layer can run.
- **Useful-Compute candidate task: Spectral anomaly scoring on AOI tiles for GEO-0021** &mdash; bucket `useful_compute_candidate` &mdash; safety `safe` &mdash; impact `high` &mdash; id `GEO-0021_uc_spectral_anomaly_scoring`
  - GEO-0021 (asia_sukhoi_log) accepted; spectral anomaly scoring is the cheapest first-pass evidence-strength booster on top of preprocessed tiles.
