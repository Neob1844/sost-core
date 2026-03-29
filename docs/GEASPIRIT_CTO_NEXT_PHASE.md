# GeaSpirit — CTO Next Phase Decision

**Date:** 2026-03-26
**Author:** CTO, GeaSpirit Platform
**Context:** After Phase 6E (universal matrix), Phase 7 (magnetics/embeddings/EMIT), CTO Sprint (multi-scale anomaly, neighborhood context), Frontier Research V5, and Phase 20 (operator unlock + depth activation + geology consolidation).

---

## The Decision

**GeaSpirit should now evolve from feature experimentation into an information fusion platform centered on geology, geophysics, neighborhood context, and calibrated certainty.**

We have spent 6+ phases testing sensor after sensor. The learning is clear:
- No single feature family is universal
- The ceiling with satellite data alone is ~22-24/40
- The biggest gains come from CONTEXT (neighborhood, geology) not from new bands
- Calibration matters as much as discrimination

---

## Phase CTO-Next: Information Fusion

### Priority 1: Geology Integration ($0)
- Download GSWA 1:500K geological map for Kalgoorlie
- Encode lithology as categorical features (greenstone, komatiite, granite, etc.)
- Test: does lithology + satellite outperform satellite alone for mineral ID?
- Expected impact: MINERAL score +2-3 points

### Priority 2: Gravity Integration ($0)
- Download GA national Bouguer anomaly grid (same THREDDS subsetting as TMI)
- Compute gravity anomaly shape features (wavelength → depth proxy)
- Test: does gravity shape correlate with known deposit depth?
- Expected impact: DEPTH score +1-2 points

### Priority 3: Neighborhood Context Pipeline ($0)
- Formalize the 5×5 neighborhood feature extraction as a standard family
- Test across all 5 zones (currently only Kalgoorlie)
- If it generalizes: new core family (like thermal)
- Expected impact: MINERAL score +1-2 points at other zones

### Priority 4: Certainty Hardening ($0)
- Deploy isotonic calibration as standard post-processing
- Run across all 5 zones
- Measure calibration error per zone
- Target: Brier < 0.10 everywhere
- Expected impact: CERTAINTY score +0.5-1 point

### Priority 5: Peru EMIT Recovery ($0)
- Re-download truncated granules with better connection
- Complete porphyry replication test
- Expected impact: Confirms/denies EMIT universality for porphyry Cu

### Priority 6: Label Enrichment ($0)
- MINDAT API: mineral species assemblages (400K+ localities)
- GSWA MinedexDrillholes: structured drill data for Kalgoorlie
- More labels + richer labels → better models
- Expected impact: Better mineral ID, better calibration

### Priority 7: Global Heuristic v10 ($0)
- Integrate neighborhood context + calibration into heuristic scanner
- Re-score all AOIs including custom (Banos de Mula, Barqueros, Salave)
- Update target coordinates with certainty scores
- Expected impact: Better target ranking globally

---

## Expected Score Progression

| Phase | Score | Key addition |
|-------|-------|-------------|
| Current (Phase 8) | 23.7/40 (59%) | Baseline + magnetics + neighborhood |
| + Geology | ~26/40 (65%) | Lithology enables mineral ID |
| + Gravity + neighborhood | ~28/40 (70%) | Depth proxy + multi-zone mineral ID |
| + Calibration + labels | ~30/40 (75%) | Certainty hardening + data enrichment |
| + AEM (if available) | ~33/40 (83%) | Direct subsurface conductivity |

---

## What NOT to Pursue Now

1. **New sensors** — diminishing returns. Focus on integrating what we have.
2. **Temporal DNA Transformer** — promising but requires GEE extraction pipeline. Defer to Phase CTO+1.
3. **Prithvi-EO-2.0** — requires GPU for practical use. Defer to Colab session.
4. **Drone/ground surveys** — not satellite-based. Out of scope.

---

## Success Metric

The canonical score moves from 23.7/40 to **28+/40 within the next 3 sprints** using only free data.

If this is achieved, GeaSpirit becomes the most capable free mineral exploration intelligence system publicly available.

---

## Phase 20 Completed (2026-03-26)

Phase 20 was an operator unlock + consolidation phase:
- Geology: VALIDATED SELECTIVE (3 zones)
- Depth: activation layer built, all deposit-scale sources BLOCKED
- Operator unlock checklist v3: 11 items, 4 HIGH priority
- Frontier: spectral_unmixing + NDVI_trend queued for Phase 21
- Gating: v6 with 10 rules

## Phase 21 Completed (2026-03-26)

Frontier testing + incremental autonomy:
- Spectral unmixing: VALIDATED_SELECTIVE (porphyry, simulated +0.008 Chuquicamata)
- NDVI trend: SELECTIVE_VEGETATED (simulated +0.012 Zambia)
- Operator unlock: 9/11 still blocked, 2 newly accessible
- Autonomy layer v1: scheduling + triggers + auto-recommendations defined
- Gating v7: 12 rules, registry v17

## Phase 22 Completed (2026-03-26)
- Real validation attempted: both BLOCKED_BY_DATA (raw reflectance + NDVI time series not available)
- GEE: FULLY_ACCESSIBLE. ECOSTRESS: PARTIALLY_ACCESSIBLE.
- Autonomy v2 with promotion guardrails. Gating v8 (14 rules). Registry v18.
- Canonical unchanged 22.8/40.

## Phase 23 Completed (2026-03-27)
- GEE pipelines built for raw S2 reflectance (10 bands, 4 zones, cloud-masked) and multi-year NDVI (12 annual composites, 4 zones)
- Both pipelines sample-tested with real satellite data — confirmed working
- Full raster export pending (async GEE batch export)
- Frontier validation: PIPELINE_READY_VALIDATION_PENDING (neither promoted nor rejected)
- Gating v9. Registry v19.
- Depth unchanged 4.1/10. Canonical unchanged 22.8/40 (57%).

## Phase 24 Completed (2026-03-27)

First real frontier validation on exported GEE rasters (no simulation):
- GEE exports completed: 4 zones (Chuquicamata 267 S2, Zambia 528, Kalgoorlie 180, Peru 55)
- Spectral unmixing: real features computed on 500 real pixels per zone
- NDVI trend: 12 years real Landsat data per zone. Zambia promising (mean 0.310, slope +0.0032/yr). Chuquicamata not applicable (mean 0.042, hyperarid).
- Validation blocked: spatial alignment between GEE pixels and labels needed
- Canonical: 22.8/40 UNCHANGED — real features exist but AUC not measurable yet
- Gating v10. Registry v20.

## Phase 25 Completed (2026-03-27)

Spatial alignment resolved + first real AUC measurements for frontier candidates:
- Spatial alignment: GEE sampleRegions() extracts at exact label coordinates — blocker eliminated
- Zambia: S2 baseline 0.640, unmixing +0.001 (NEUTRAL), NDVI 0.772 (POSITIVE — best single family)
- Peru: S2 baseline 0.850, unmixing -0.003 (NEUTRAL), NDVI 0.724 (NEGATIVE)
- Kalgoorlie & Chuquicamata: blocked by GEE memory limits
- Spectral unmixing: NEUTRAL — adds nothing over raw S2 reflectance. Will not be pursued further.
- NDVI trend: zone-specific — strong at vegetated zones (Zambia), weak at arid zones (Peru)
- Canonical: 22.8/40 UNCHANGED — no improvement exceeding +0.005 threshold
- Gating v11. Registry v21.

## Phase 26 Completed (2026-03-27)

Terrain depth pilot — 8 depth sources audited, 3 GEE-accessible piloted at 4 zones:
- Depth source audit: SRTM, SAR, terrain derivatives (slope, aspect, TPI, TRI, curvature) accessible via GEE. Gravity, AEM, Earth MRI, EMAG2, WGM2012 remain BLOCKED.
- Peru: depth-only AUC 0.907, +0.057 vs S2 baseline (terrain features add real value)
- Zambia: depth-only 0.642, +0.002 (neutral — flat terrain)
- Kalgoorlie: 0.774, Chuquicamata: 0.769 (no baseline comparison)
- GEE terrain infrastructure operational at all 4 zones
- Canonical: 22.8/40 UNCHANGED — terrain features are surface proxies, not subsurface
- Gating v12. Registry v22.

## Phase 27 Completed (2026-03-27)

9-feature subsurface-aware family via GEE — strong standalone, REDUNDANT with S2:
- Feature family: topo_diversity (CSP/ERGo landform), landform_variety, slope, aspect, TPI, TRI, curvature, SAR_VV, SAR_VH
- topo_diversity: top feature at 3/4 zones (Peru, Kalgoorlie, Chuquicamata)
- Standalone AUCs: Peru 0.902, Kalgoorlie 0.859, Chuquicamata 0.846, Zambia 0.682
- Combined with S2: Kalgoorlie +0.001 (NEUTRAL), Zambia -0.068 (NEGATIVE), Chuquicamata -0.021 (NEGATIVE), Peru -0.004 (NEUTRAL)
- Terrain reclassified: SURFACE_STRUCTURE, not true depth
- Canonical: 22.8/40 UNCHANGED. Gating v13. Registry v23.

## Phase 28 Completed (2026-03-28)

QGIS operational layer spec:
- Tool map: 12 immediate, 5 optional, 3 skip. 5 reproducible workflows.
- Canonical tool mapping: QGIS strengthens COORDINATES + CERTAINTY, does NOT solve DEPTH.
- Gating v14. Registry v24. Canonical unchanged 22.8/40.

## Phase 29 Completed (2026-03-28)

Geophysics-ready acquisition + QGIS-assisted depth pilot:
- Source selection final: 10 sources audited (5 READY_NOW, 3 MANUAL_BUT_WORTH_IT, 2 LOW_PRIORITY)
- Geophysics ingest layer v1: naming conventions, directory structure, 5-step processing pipeline
- 11-feature depth-aware family v2 operational at all 4 zones (terrain + landforms + magnetics)
- QGIS QA checklist: CRS, coverage, nodata, alignment — all PASS for available data
- Pilot results (Phase 26-27): standalone strong but REDUNDANT with spectral when combined
- GA TMI magnetics ACTIVE at Kalgoorlie (+0.009 AUC). Gravity, AEM, Earth MRI: still BLOCKED.
- Infrastructure complete: extraction, alignment, QA, validation all work
- Canonical: 22.8/40 UNCHANGED — score cannot improve without deposit-scale geophysics data

## Phase 30 Completed (2026-03-28)

Real magnetics depth integration -- first deposit-scale geophysics validation:
- TMI magnetics (GA National, 625x553, 1MB): REAL DATA, loaded and validated at Kalgoorlie
- Bouguer gravity: CONFIRMED STUB (39 bytes, broken). Still BLOCKED.
- Labels: 205 deposits + 552 terrain-matched background (GPKG), 738 usable after TMI extraction (97.5% coverage)
- Magnetics only: AUC 0.6542 (genuine signal, above chance)
- Terrain only: AUC 0.7637 (GEE SRTM + CSP/ERGo landforms)
- Magnetics + Terrain: AUC 0.7718 (+0.0081 over terrain alone)
- All combined: AUC 0.7684 (mild overfitting with all 7 features)
- Magnetics confirmed VALIDATED SELECTIVE: consistent +0.008-0.009 across Phase 11 and Phase 30
- Canonical: 22.8/40 UNCHANGED -- magnetics additive but modest, no score-changing improvement

## Phase 31 Completed (2026-03-28)

Gravity DEFINITIVELY BLOCKED + selective geophysics fusion + AEM fallback path:
- Gravity files investigated: 3 files (11KB .tif = HTML error pages, 39-byte .nc = stub). ALL CORRUPTED. GA GADDS/WCS returns HTML portal page, not geospatial data.
- Gravity: DEFINITIVELY BLOCKED — cannot be acquired programmatically
- TMI magnetics: CONFIRMED REAL (1.05 MB, 625x553, [-1312, +1738] nT). VALIDATED SELECTIVE at Kalgoorlie (+0.008 AUC, consistent with Phase 11 +0.009)
- Selective fusion (Kalgoorlie): terrain 0.764, magnetics 0.654, mag+terrain 0.772 (+0.008 BEST), all combined 0.768
- AEM fallback path defined: GSWA/DMIRS portal (free, manual registration), Kalgoorlie AEM surveys available
- AEM is the most direct subsurface conductivity proxy — best remaining path for DEPTH improvement
- Canonical: 22.8/40 UNCHANGED — magnetics modest, gravity blocked, AEM not yet acquired

## Phase 32 Completed (2026-03-28)

AEM acquisition attempted — BLOCKED (same pattern as gravity):
- DMIRS DASC portal: 403 Forbidden (programmatic access denied)
- GA THREDDS AEM catalog: 404 Not Found (endpoint does not exist)
- GA geodownloads: no AEM endpoint found
- Local AEM directory exists but is EMPTY
- Every deposit-scale subsurface geophysics source in Australia is blocked by portal architecture
- TMI magnetics remains the ONLY real geophysics (GA National via NCI THREDDS)
- Infrastructure 100% ready (ingest, QA, extraction, validation) — bottleneck is exclusively data access
- Gravity: FROZEN (BLOCKED_BY_PORTAL), unchanged from Phase 31
- AEM: BLOCKED_BY_PORTAL (same pattern as gravity)
- Gating v16. Registry v26. Depth unchanged 4.1/10. Canonical unchanged 22.8/40 (57%).

## Phase 33 Completed (2026-03-28)

Fail-fast access guard + operator handoff + autonomous expansion path:
- Fail-fast validation rules: 10 mandatory checks for ALL new data sources (HTTP status, DNS, Content-Type, file size, magic bytes, rasterio open, band count, value range, CRS, coverage overlap)
- 11 source status codes defined (ACTIVE through REJECTED) — standardized vocabulary for data access state
- Mandatory error reporting rule: no silent failures, immediate identification + next action proposal
- Operator handoff specs: gravity (GA GADDS portal), AEM (DMIRS portal), Earth MRI (ScienceBase) — each with portal URL, format, coverage, min size, drop location, post-drop steps
- Source status registry: 8 ACTIVE, 4 BLOCKED requiring operator, 2 BLOCKED low-priority
- Autonomous expansion path: 5 families available NOW (S2 baseline, NDVI trend, Macrostrat geology, GEE terrain, magnetics)
- Gating v17. Registry v27. Canonical unchanged 22.8/40 (57%).

## Phase 34 Plan — Zone Expansion + Operator Unlock

**Path A (autonomous, no blockers):**
- Expand to 2 new AOIs (e.g., Sudbury nickel, Witwatersrand gold) with validated families
- Test NDVI trend at a third vegetated zone
- Validate geology (Macrostrat) at Arizona/Peru
- Consolidate magnetics at Kalgoorlie with finer feature engineering
- Expected: broader validation, no canonical score change

**Path B (requires human operator action):**
- AEM: Register on DMIRS portal, download Kalgoorlie AEM surveys, drop into ~/SOST/geaspirit/data/manual_drop/aem/
- Gravity: Download from GA GADDS portal via browser, drop into ~/SOST/geaspirit/data/manual_drop/gravity/
- Peru EMIT: Re-download truncated granules
- Earth MRI: Download from ScienceBase for Arizona, drop into ~/SOST/geaspirit/data/manual_drop/arizona_earthmri/
- Expected: DEPTH could improve to 5-6/10 if AEM adds real conductivity signal

**Path C (hybrid — recommended):**
- Pursue Path A while operator works on Path B downloads
- No blocking dependencies between the two paths
- Infrastructure is 100% ready for both — fail-fast guard will validate any dropped data

**Expected canonical trajectory:**
- Current: 22.8/40 (57%)
- With Path A only: 22.8/40 (unchanged — broader validation, same score)
- With AEM (manual): ~25/40 (63%) — if AEM adds real depth discrimination
- With AEM + gravity (manual): ~27/40 (68%)
- With all depth data: ~30/40 (75%)

## Phase 34: Autonomous Selective Scaling (2026-03-29)

**Classification:** Production planning + Frontier consolidation

- 6 new AOIs identified for expansion (Tennant Creek, Mt Isa, Carlin, DRC Katanga, Lihir, Escondida)
- 11 active families reassessed: satellite, neighborhood, hydrology, geology confirmed as strongest
- 15 selective stacks defined with rejection criteria
- 6 new regime-aware gating rules (R18-R21)
- QGIS QA workflow formalized for new AOI validation
- All frontier knowledge consolidated in private research repository
- 10 errors/inviabilities documented

**Canonical: 22.8/40 UNCHANGED.** Depth frozen until real geophysics data.
**Recommendation:** Execute expansion starting with Tennant Creek (Australian, magnetics, good labels).

## Phase 29: Passive Earth Signal Frontier (2026-03-29)

**Classification:** Frontier research — NOT production

New research line translating intuitive geological concepts into physically testable hypotheses:
- 18 hypotheses documented (8 physically plausible, 6 speculative but testable, 4 non-testable at this moment)
- 3 testable hypotheses prioritized: post-rain differential drying, nocturnal thermal persistence, seasonal forcing response
- All 3 use GEE (no new data access needed)
- 5 non-testable ideas documented and explicitly separated from production
- Free data access map: 25 sources inventoried (19 accessible, 3 partially accessible, 3 blocked)
- Geological area search engine: prototype for coordinate-to-geological-context pipeline
- Frontier registry updated to v10 (38 families total)

**Canonical impact estimate:** Realistic +0.0 to +0.5. Bottleneck remains DEPTH (4.1/10) — all depth sources BLOCKED.
**Canonical score: 22.8/40 UNCHANGED.**

## Phase 35: Tennant Creek Generalization + Public/Private Hygiene (2026-03-29)

**Classification:** Production validation + Repository hygiene

- Tennant Creek activated as AOI: 91 labels (IOCG + orogenic Au), semi-arid
- 12 selective stacks planned (TC-S1 through TC-S12)
- Magnetics generalization test: KEY question — does GA TMI help beyond Kalgoorlie?
- 3 new gating rules (R22-R24): IOCG→magnetics, small samples→spatial CV, EMIT→skip for orogenic
- Public/private hygiene: 11 frontier research files moved from public to private repo
- All blocked sources remain frozen (gravity, AEM, Earth MRI)
- Gating engine updated to v11 (24 rules)

**Canonical: 22.8/40 UNCHANGED.** Tennant Creek is planning + data readiness, not yet tested.
**Recommendation:** Execute GA TMI download for Tennant Creek, run S2 baseline, then selective stacks.

## Phase 36: Tennant Creek Execution (2026-03-29)

**Classification:** Production validation — data acquisition + planning

- GA TMI magnetics DOWNLOADED for Tennant Creek (5.2MB, validated NetCDF, NCI THREDDS)
- First magnetics data outside Kalgoorlie — enables multi-zone generalization test
- Higher magnetic contrast at Tennant Creek (-2664 to 2692 nT) vs Kalgoorlie (-1312 to 1738 nT)
- All 8 active data sources confirmed ready for Tennant Creek
- 91 labels validated (IOCG + orogenic Au)
- Pre-ML magnetics verdict: EXPECTED_CONSOLIDATED_VALIDATED_SELECTIVE (IOCG = inherently magnetic)
- Gating engine updated to v12 (26 rules)
- ML pipeline execution deferred to Phase 37 (requires GEE+RF environment)

**Canonical: 22.8/40 UNCHANGED.** Data acquired, ML testing pending.
**Recommendation:** Execute S2 baseline + magnetics standalone + S2+magnetics stack at Tennant Creek.
