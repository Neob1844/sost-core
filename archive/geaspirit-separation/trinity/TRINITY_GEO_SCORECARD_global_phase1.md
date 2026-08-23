# Trinity / Geo Discovery — Scorecard `global_phase1`

> **DRY-RUN scorecard.** Weighted prospectivity score computed from remote proxy axes (tectonic belt prior, commodity compatibility, aridity, terrain ruggedness, data availability, novelty penalty, uncertainty penalty). Not a deposit confirmation. Not a mineral reserve claim. Remote proxy evidence only — requires field validation before any public claim.

- **Schema**: `trinity-geo-scorecard/v0.1`
- **Commodity**: `copper_gold_critical_minerals`
- **Track**: `geaspirit`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `candidate_pool_basename`: `TRINITY_GEO_CANDIDATE_AOIS_global_phase1.json`
  - `candidate_pool_sha256`: `311b4c1db8fb8bc99f4c5478836f3aa82a30d3f5970111abf255855ff17148cb`
  - `filter_basename`: `TRINITY_GEO_FILTER_global_phase1.json`
  - `filter_sha256`: `627317fa91a409e2ac9dacf5011369b4a5eeff7ec2441dd237c6650e2d440e2d`
  - `mode`: `deterministic_rule_based_v0.1`

## Weights

- `aridity_proxy`: `0.1`
- `commodity_belt_compatibility`: `0.15`
- `data_availability`: `0.2`
- `novelty_penalty`: `0.1`
- `tectonic_belt_prior`: `0.2`
- `terrain_ruggedness_proxy`: `0.1`
- `uncertainty_penalty`: `0.15`

## Top AOIs by score

| rank | id | name | region | score | confidence | hypotheses |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `GEO-0027` | Andean belt tile S15.7 W70.0 | `south_america_andes` | 87.0 | 0.838 | copper, lithium, molybdenum |
| 2 | `GEO-0045` | Andean belt tile N1.8 W73.8 | `south_america_andes` | 87.0 | 0.838 | gold, lithium, molybdenum |
| 3 | `GEO-0005` | Carlin Trend (Nevada, USA) tile N40.9 W116.8 | `north_america_carlin` | 86.2 | 0.858 | gold |
| 4 | `GEO-0070` | Carlin Trend (Nevada, USA) tile N42.3 W117.1 | `north_america_carlin` | 86.2 | 0.858 | gold |
| 5 | `GEO-0085` | Carlin Trend (Nevada, USA) tile N40.5 W117.4 | `north_america_carlin` | 86.2 | 0.858 | gold |
| 6 | `GEO-0023` | Andean belt tile S0.6 W76.2 | `south_america_andes` | 84.0 | 0.787 | molybdenum |
| 7 | `GEO-0067` | Andean belt tile S17.7 W66.0 | `south_america_andes` | 84.0 | 0.787 | molybdenum |
| 8 | `GEO-0008` | Lachlan Fold Belt (East Australia) tile S33.1 E145.5 | `australia_lachlan` | 82.2 | 0.858 | copper |
| 9 | `GEO-0035` | Sierra Nevada (USA) tile N39.8 W118.7 | `north_america_sierra_nevada` | 82.2 | 0.82 | gold, rare_earth_elements |
| 10 | `GEO-0068` | Lachlan Fold Belt (East Australia) tile S30.4 E144.2 | `australia_lachlan` | 82.2 | 0.858 | copper |
| 11 | `GEO-0079` | Lachlan Fold Belt (East Australia) tile S35.1 E145.8 | `australia_lachlan` | 82.2 | 0.858 | copper |
| 12 | `GEO-0034` | Yilgarn Craton (West Australia) tile S25.6 E115.4 | `australia_yilgarn` | 79.4 | 0.907 | gold, nickel |
| 13 | `GEO-0100` | Sierra Nevada (USA) tile N38.0 W120.8 | `north_america_sierra_nevada` | 79.2 | 0.77 | gold |
| 14 | `GEO-0039` | Trans-Hudson Orogen (Canada) tile N61.8 W104.7 | `north_america_trans_hudson` | 79.1 | 0.873 | copper, nickel |
| 15 | `GEO-0036` | Tethyan Belt (Iran / Turkey / Balkans) tile N41.5 E51.1 | `asia_tethyan` | 78.8 | 0.767 | gold, molybdenum |
| 16 | `GEO-0041` | Tethyan Belt (Iran / Turkey / Balkans) tile N39.3 E25.2 | `asia_tethyan` | 78.8 | 0.767 | copper, gold |
| 17 | `GEO-0053` | Tethyan Belt (Iran / Turkey / Balkans) tile N41.0 E35.0 | `asia_tethyan` | 78.8 | 0.767 | copper, gold, molybdenum |
| 18 | `GEO-0058` | Tethyan Belt (Iran / Turkey / Balkans) tile N39.9 E41.9 | `asia_tethyan` | 78.8 | 0.767 | copper, gold, molybdenum |
| 19 | `GEO-0065` | Tethyan Belt (Iran / Turkey / Balkans) tile N37.6 E54.4 | `asia_tethyan` | 78.8 | 0.767 | copper, gold |
| 20 | `GEO-0092` | Tethyan Belt (Iran / Turkey / Balkans) tile N39.4 E48.1 | `asia_tethyan` | 78.8 | 0.767 | copper, gold, molybdenum |
| 21 | `GEO-0095` | Tethyan Belt (Iran / Turkey / Balkans) tile N35.1 E42.6 | `asia_tethyan` | 78.8 | 0.767 | copper, molybdenum |
| 22 | `GEO-0019` | Superior Craton (Canada) tile N51.2 W90.8 | `north_america_superior` | 78.6 | 0.873 | copper, nickel |
| 23 | `GEO-0040` | Yilgarn Craton (West Australia) tile S25.5 E124.6 | `australia_yilgarn` | 77.5 | 0.858 | nickel |
| 24 | `GEO-0071` | Iberian Pyrite Belt (Portugal / Spain) tile N37.8 W8.3 | `europe_iberian_pyrite` | 76.9 | 0.802 | copper, gold |
| 25 | `GEO-0001` | Yilgarn Craton (West Australia) tile S26.1 E123.9 | `australia_yilgarn` | 76.6 | 0.858 | gold |
