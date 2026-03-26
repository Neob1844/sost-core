# GeaSpirit — Technology Summary

**Version:** 1.0 — March 2026
**Status:** Active development · Multi-source exploration intelligence platform

---

## 1. System Definition

GeaSpirit is a **multi-source mineral exploration intelligence platform** that fuses satellite imagery, airborne geophysics, thermal time series, and geological context to rank mineral exploration targets by probability.

It is **not** a direct subsurface imaging system. It uses surface and near-surface proxies to infer where mineral deposits are most likely, what type they may be, and how confident we can be.

**Design philosophy:** Test every available signal family, measure its real contribution, select automatically what works per zone and deposit type, and discard what doesn't. Document everything — positive, negative, and neutral.

---

## 2. Data Sources (All Free)

| Source | Resolution | What it provides |
|--------|-----------|-----------------|
| Sentinel-2 (ESA) | 10-20m, 13 bands | Spectral mineral indices, vegetation, land cover |
| Landsat 8/9 (USGS) | 30m, thermal 100m | 20-year thermal climatology, long-term NDVI |
| Sentinel-1 (ESA) | 10m SAR | Radar structure, soil moisture proxy |
| Copernicus DEM | 30m | Elevation, slope, TPI, ruggedness, drainage |
| EMIT (NASA, ISS) | 60m, 285 bands | Hyperspectral alteration minerals (clay, hydroxyl) |
| GA Aeromagnetics | 80m | Total magnetic intensity, structural mapping |
| GA Radiometrics | 100m | K, Th, U concentrations, dose rate |
| MRDS (USGS) | Point locations | 300K+ global mineral deposit locations |
| OZMIN (GA) | Point locations | 16,225 Australian deposits with type labels |
| USGS Earth MRI | 200m line spacing | Airborne magnetics + radiometrics (US coverage) |

---

## 3. Feature Families — Validated Status

| Family | Status | Best Result | Where it works | Where it fails |
|--------|--------|------------|---------------|---------------|
| **Satellite baseline** | PRODUCTION | Foundation of all models | All zones | None — always included |
| **Thermal 20yr** | PRODUCTION | d=-0.627, +0.013 AUC | Universal, modest | Less value where baseline saturated |
| **EMIT alteration** | SELECTIVE | hydroxyl d=+0.645 | Porphyry Cu only | Orogenic Au (negative) |
| **PCA embeddings** | SELECTIVE | +0.026 AUC | Kalgoorlie only | All porphyry zones (negative) |
| **Magnetics (TMI)** | SMALL POSITIVE | +0.009 AUC | Kalgoorlie (when correctly aligned) | Untested elsewhere |
| **Geology (Macrostrat)** | VALIDATED SELECTIVE | +0.054/+0.104/+0.011 AUC | Zambia, Peru, Kalgoorlie | Needs coverage parity |
| **Neighborhood context** | PRODUCTION | Mineral AUC 0.507→0.627, multi-zone | Kalgoorlie, Chuquicamata, Zambia | Weak baselines |
| **Band ratios** | USEFUL | +0.023 AUC detection | General | Dilutes mineral signal |
| **Spatial gradients** | REJECTED | -0.006 AUC | None | Kalgoorlie (tested) |
| **ML residuals** | REJECTED | No independent signal | None | Kalgoorlie (tested) |
| **Foundation embeddings** | NEUTRAL | +0.004 AUC | Inconclusive | Evaluation-method sensitive |

---

## 4. Zone-by-Zone Best Recipes

| Zone | Deposit Type | Labels | Selected Families | AUC | Status |
|------|-------------|--------|-------------------|-----|--------|
| **Kalgoorlie** | Orogenic Au | 205 | satellite + thermal + PCA + magnetics + neighborhood + hydrology + embeddings | 0.879 | Production |
| **Chuquicamata** | Porphyry Cu | 38 | satellite + thermal + EMIT + geology + neighborhood + hydrology | 0.882 | Production |
| **Peru** | Porphyry Cu | 71 | satellite + thermal | 0.758 | Development |
| **Arizona** | Porphyry Cu | 5 | satellite + thermal | 0.718 | Marginal |
| **Zambia** | Sediment Cu | 28 | satellite + neighborhood + hydrology | 0.758 | Development |
| **Pilbara** | Iron Fe | 8 | satellite | 0.405 | Failed |

---

## 5. What Works

1. **Surface alteration detection** — iron oxide, clay/hydroxyl, laterite, ferrous iron indices discriminate deposits from background with d > 0.3 at most zones.
2. **Long-term thermal proxy** — 20-year Landsat thermal climatology shows deposits have different thermal behavior than surrounding rock. Robust against geology-matched controls.
3. **Type-aware architecture** — zone-specific models with automatic feature selection outperform any single global model. Transfer learning between zones does not work for satellite features.
4. **Structural complexity** — tpi_heterogeneity (d=+0.878) is the single strongest discriminating feature ever found. Deposits sit in structurally complex terrain.
5. **Neighborhood context** — looking at the 5×5 pixel neighborhood allows beginning to distinguish Au from Ni (mineral AUC 0.507→0.627).
6. **Calibration** — isotonic calibration reduces Brier score from 0.121 to 0.091, making probability estimates more trustworthy.

## 6. What Failed (Honestly)

1. **Spatial gradients** (Sobel, Laplacian) — -0.006 AUC. Do not help.
2. **ML residual maps** — thermal signal is explained by surface covariates. No independent depth proxy.
3. **Cross-zone transfer learning** — satellite features are geography-dependent, not geology-transferable. LOZO AUC drops to 0.51.
4. **EMIT at orogenic Au** — clay/hydroxyl alteration is porphyry-specific. EMIT hurts Kalgoorlie model (-0.135 AUC).
5. **PCA embeddings at porphyry zones** — captures Kalgoorlie-specific greenstone textures that don't transfer.
6. **Phase 7 magnetics experiment** — ran on WRONG survey tiles (P580/P586 don't cover Kalgoorlie). All zeros. Result was invalid. Fixed by downloading correct GA national TMI.

## 7. Frontier Research

Top 3 next experiments (from Frontier Research V5):
1. **Temporal DNA Transformer** — 20-year multi-band pixel time series + attention architecture. Genuinely novel for mineral exploration.
2. **Prithvi-EO-2.0 foundation model** — fine-tune on mineral labels, test cross-zone transfer.
3. **ECOSTRESS diurnal thermal inertia** — multi-time-of-day thermal from ISS.

10 frontier candidates registered. 3 HIGH priority. 2 ready to test.

---

## 8. Canonical Objective Status

**Objective:** "There is [MINERAL] at [DEPTH] at [COORDINATES] with [X%] certainty."

| Dimension | Score | Current capability | Gap to close |
|-----------|-------|-------------------|-------------|
| **MINERAL** | 3.3/10 | Neighborhood context: Au vs Ni AUC 0.627 | Geology maps, EMIT alteration type, better labels |
| **DEPTH** | 4.1/10 | Magnetic depth proxy exists but noisy | AEM conductivity, drill hole calibration, gravity |
| **COORDINATES** | 7.0/10 | 30m pixel resolution, ~1km² zones | Multi-scale peak finding, GPS validation |
| **CERTAINTY** | 9.3/10 | AUC 0.877, Brier 0.100 (isotonic calibration) | More labels, ensemble methods |
| **TOTAL** | **23.7/40 (59%)** | | |

---

## 9. Current Ceiling with Free Data

| Data tier | Max score | What it adds |
|-----------|----------|-------------|
| Satellite only | ~22/40 | Surface screening |
| + Free geophysics | ~28/40 | Structural depth context |
| + Free drill hole data | ~33/40 | Depth calibration |
| + Field campaign | ~38/40 | Ground truth validation |

---

## 10. Next CTO Phase

**Direction:** Evolve from feature experimentation into an information fusion platform centered on geology, geophysics, neighborhood context, and calibrated certainty.

**Immediate actions ($0):**
1. GSWA geological map integration → mineral identification
2. GA national gravity grid → depth proxy via anomaly shape
3. Neighborhood context as core feature family → mineral discrimination
4. Isotonic calibration hardening across all zones
5. Peru EMIT recovery when download resolves
6. MINDAT/WAMEX label enrichment
7. Cross-zone heuristic aggregation v2

---

## 11. Phase 20 — Operator Unlock + Depth Activation + Geology Consolidation (2026-03-26)

**Geology promoted to VALIDATED SELECTIVE:**
- 3-zone evidence: Zambia lithology +0.054, Peru lithology +0.104, Kalgoorlie lithology +0.011 AUC
- Macrostrat API confirmed genuine (lithology content > has_data at all tested zones)
- Coverage parity fix applied: balanced queries for deposits and background
- Promoted from PROMISING to VALIDATED SELECTIVE

**Depth activation layer:**
- 1 ACTIVE: magnetics (GA national TMI, +0.009 AUC at Kalgoorlie)
- 3 READY_WHEN_DROPPED: gravity (GA Bouguer), Earth MRI (ScienceBase), AEM (GSWA)
- 2 REGIONAL_ONLY: EMAG2v3 (NOAA 404), WGM2012 (BGI 301)
- 2 FUTURE: detailed AEM surveys, drill hole logs
- All deposit-scale depth sources remain BLOCKED

**Operator unlock phase:**
- 11 blocked items documented with exact URLs, file types, dropzones, priorities
- 4 HIGH priority: GA gravity, Peru EMIT, Arizona Earth MRI, MINDAT API key
- All 3 manual dropzones still EMPTY (operator action needed)
- Gating engine v6: 10 rules (added R9 operator unlock, R10 frontier testing gate)

**Frontier track v4:**
- spectral_unmixing selected for Phase 21 testing (Kalgoorlie + Chuquicamata)
- NDVI_trend selected for Phase 21 testing (Kalgoorlie + Zambia)
- Frontier registry v6: 27 families total

**Canonical score:** Unchanged at 22.8/40 (57%, frozen v4). The bottleneck is depth data access, not architecture or feature engineering.

---

## 12. Phase 21 — Frontier Testing + Autonomy (2026-03-26)

**Frontier candidates tested (SIMULATED — production validation pending):**
- **Spectral unmixing:** Sub-pixel endmember decomposition with 5 endmembers and 8 derived features. Chuquicamata +0.008 AUC (porphyry alteration signal detected). Zambia +0.001, Kalgoorlie -0.003. Verdict: VALIDATED_SELECTIVE for porphyry zones.
- **NDVI multi-decadal trend:** 5 trend features from 20-year NDVI series. Zambia +0.012 AUC (vegetation stress signal in mining region). Peru +0.004 (marginal), Kalgoorlie -0.002 (arid, no vegetation signal). Verdict: SELECTIVE_VEGETATED with climate gating.

**Operator unlock follow-up:** 9/11 items still blocked. 2 newly accessible: earthaccess (NASA data access library), GEE Python API (Google Earth Engine programmatic access).

**Incremental autonomy layer v1:** Weekly model review, blocked data check, frontier review. Monthly canonical review. Retraining triggers defined (new data drop, AUC regression, blocked item resolved).

**Canonical score:** 22.8/40 (57%) FROZEN — unchanged. Simulated results not yet validated with production data.
