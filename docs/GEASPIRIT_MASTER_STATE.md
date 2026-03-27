# GeaSpirit — Master State Document

**Last updated:** 2026-03-27
**Current phase:** Phase 22
**Architecture:** type-aware + zone-aware + baseline-aware + geology-aware
**Canonical Score (frozen v4):** 22.8/40 (57%)

---

## Phase 22 — Real Validation + Access Closure (2026-03-26)

**Focus:** Validate frontier candidates with real data, activate accessible resources, strengthen autonomy.

**Real validation results:**
- Spectral unmixing: VALIDATION_BLOCKED — stacks contain derived indices, not raw S2 reflectance
- NDVI trend: VALIDATION_BLOCKED — single-date NDVI snapshots, not multi-year time series
- Both remain SIMULATED_ONLY candidates — NOT promoted to production

**Access closure:**
- GEE Python API: FULLY_ACCESSIBLE — ee.Initialize() works, SRTM query successful
- ECOSTRESS/earthaccess: PARTIALLY_ACCESSIBLE — library+auth OK, search returns 0 granules for test AOI
- 8/11 items still fully blocked, depth items all blocked

**Autonomy layer v2:** Promotion guardrails (simulated→candidate only), execution queue, retry policy.
**Gating v8:** 14 rules (R13 simulated guardrail, R14 newly accessible pilot gate).
**Canonical: 22.8/40 (57%) FROZEN — unchanged.**

---

## Phase 21 — Frontier Testing + Autonomy (2026-03-26)

**Focus:** Execute 2 frontier candidates, operator unlock follow-through, incremental autonomy.

**Frontier results (SIMULATED — production validation pending):**
- **Spectral unmixing:** VALIDATED_SELECTIVE (porphyry zones). Chuquicamata +0.008, Zambia +0.001, Kalgoorlie -0.003.
- **NDVI trend:** SELECTIVE_VEGETATED. Zambia +0.012 (vegetated zone), Peru +0.004 (marginal), Kalgoorlie -0.002 (arid, not useful).

**Operator unlock follow-up:** 9/11 items still blocked. 2 newly accessible (earthaccess, GEE Python API).

**Incremental autonomy layer v1:** Weekly model review, blocked data check, frontier review. Monthly canonical review. Retraining triggers defined.

**Updated registries:**
- Frontier registry v7: 29 families (5 core, 6 selective, 5 blocked, 8 frontier, 2 rejected, 1 neutral)
- Gating engine v7: 12 rules (R11 NDVI vegetated gate, R12 unmixing porphyry gate)
- Zone model registry v17
- Canonical score: 22.8/40 (57%) FROZEN — unchanged (simulated results not yet production)

---

## Phase 20 — Operator Unlock + Depth Activation + Geology Consolidation (2026-03-26)

**Focus:** Systematic data unblocking, depth activation, geology validation consolidation.

**Key results:**
- Geology officially promoted to VALIDATED SELECTIVE (3-zone evidence: Zambia +0.054, Peru +0.104, Kalgoorlie +0.011 AUC)
- Depth activation layer built: 1 ACTIVE (magnetics), 3 READY_WHEN_DROPPED (gravity, Earth MRI, AEM), 2 REGIONAL_ONLY, 2 FUTURE
- Operator unlock checklist v3: 11 blocked items documented with exact URLs, file types, dropzones, priorities
- All 3 manual dropzones still EMPTY (gravity, Peru EMIT, Arizona Earth MRI)
- Gating engine v6: 10 rules (added R9 operator unlock, R10 frontier testing gate)
- Frontier track v4: spectral_unmixing + NDVI_trend selected for Phase 21 testing
- Frontier registry v6: 27 families (5 core, 4 selective, 5 blocked, 10 frontier, 2 rejected, 1 neutral)
- Zone model registry v16: all 6 zones documented with current families/blockers
- Canonical score remains FROZEN at v4: 22.8/40 (57%)
- **Architecture:** type-aware + zone-aware + baseline-aware + geology-aware
- **Bottleneck:** Depth data access, NOT architecture or feature engineering

---

## 1. Architecture

GeaSpirit is a **multi-source mineral exploration intelligence platform** that:
- Tests all available feature families as candidates
- Selects automatically what works per zone and deposit type
- Defers complex fusion for weak baselines (gating engine)
- Documents everything — positive, negative, and blocked

**Evolution:**
- Phase 1-5: zone-specific models
- Phase 6: type-aware (EMIT porphyry-specific, PCA Kalgoorlie-specific)
- Phase 9-12: information fusion (neighborhood + hydrology + magnetics)
- Phase 14: negative result (Peru fusion -0.063)
- Phase 15: baseline-aware gating (fusion conditional on baseline strength)
- Phase 16: low-friction data activation (Macrostrat API)

## 2. Feature Family Registry

| Family | Category | Status | Best Result | Zones |
|--------|----------|--------|-------------|-------|
| satellite_baseline | CORE | PRODUCTION | Foundation (0.33-0.87 AUC) | All |
| thermal_20yr | CORE | PRODUCTION | +0.013 AUC, d=-0.627 | Kalgoorlie, Chuquicamata |
| neighborhood_context | CORE (gated) | PRODUCTION | +0.024 AUC multi-zone | Kalgoorlie, Chuquicamata, Zambia |
| hydrology | CORE (gated) | PRODUCTION | drainage_density d=+0.576 | Kalgoorlie, Zambia |
| isotonic_calibration | CORE | PRODUCTION | Brier 0.121→0.091 | All supervised |
| emit_alteration | SELECTIVE | PRODUCTION | hydroxyl d=+0.645 | Porphyry Cu only |
| pca_embeddings | SELECTIVE | PRODUCTION | +0.026 AUC | Kalgoorlie only |
| magnetics_tmi | SELECTIVE | PRODUCTION | +0.009 AUC | Kalgoorlie (GA national) |
| geology_macrostrat | SELECTIVE | VALIDATED SELECTIVE | 3-zone evidence (+0.054/+0.104/+0.011) | Zambia, Peru, Kalgoorlie |
| spatial_gradients | REJECTED | — | -0.006 AUC | Kalgoorlie |
| ml_residuals | REJECTED | — | No independent signal | Kalgoorlie |
| foundation_embeddings_v1 | NEUTRAL | — | +0.004 (evaluation-sensitive) | Kalgoorlie |
| gravity_bouguer | BLOCKED | — | GA WCS/REST return HTML | Kalgoorlie target |
| peru_emit | BLOCKED | — | Granules truncated (54%, 41%) | Peru target |
| arizona_earthmri | BLOCKED | — | ScienceBase not downloaded | Arizona target |
| mindat_labels | BLOCKED | — | No API key registered | Global |
| emag2v3 | BLOCKED | — | NOAA URL 404 (moved) | Global |
| wgm2012 | BLOCKED | — | BGI URL redirects (301) | Global |
| temporal_dna_transformer | FRONTIER | NOT_TESTED | Highest priority frontier | — |
| ecostress_diurnal | FRONTIER | NOT_TESTED | Path confirmed (GEE) | — |
| prithvi_eo_2 | FRONTIER | NOT_TESTED | Feasible on CPU (8GB) | — |
| spectral_unmixing | SELECTIVE | SIMULATED | +0.008 Chuquicamata (porphyry) | Porphyry zones |
| post_rainfall_sar | FRONTIER | NOT_TESTED | MEDIUM priority | — |
| nighttime_thermal | FRONTIER | NOT_TESTED | MEDIUM priority | — |
| ndvi_multi_decadal | SELECTIVE | SIMULATED | +0.012 Zambia (vegetated) | Vegetated zones |
| aem_conductivity | FRONTIER | BLOCKED | GSWA manual download | Kalgoorlie |

## 3. Zone Results

| Zone | Type | Labels | Baseline AUC | Best AUC | Fusion Delta | Status |
|------|------|--------|-------------|----------|-------------|--------|
| Kalgoorlie | Orogenic Au | 205 | 0.865 | 0.879 | +0.013 | Production |
| Chuquicamata | Porphyry Cu | 38 | 0.789 | 0.882 | +0.093 | Production |
| Zambia | Sediment Cu | 28 | 0.737 | 0.760 | +0.024 | Production |
| Peru | Porphyry Cu | 71 | 0.698 | 0.698 | -0.063 (NEGATIVE) | Weak baseline |
| Arizona | Porphyry Cu | 5 | 0.333 | — | — | Insufficient labels |
| Pilbara | Iron Fe | 8 | 0.405 | — | — | Failed |

## 4. Canonical Score (Frozen v4)

| Dimension | Score | Method |
|-----------|-------|--------|
| MINERAL | 4.0/10 | Au vs Ni AUC 0.627 |
| DEPTH | 4.1/10 | Magnetics only (no gravity/AEM) |
| COORDINATES | 7.0/10 | 30m pixel resolution |
| CERTAINTY | 7.7/10 | Best calibrated Brier 0.096 |
| **TOTAL** | **22.8/40** | **57%** |

## 5. Gating Rules (v7)

- R1: baseline < 0.73 → DEFER complex fusion
- R2: porphyry + EMIT → PRIORITIZE EMIT
- R4: baseline ≥ 0.73 + labels ≥ 25 → ALLOW fusion
- R5: labels < 15 → SKIP ML, heuristic only
- R6: geology available → INTEGRATE FIRST
- R7: Brier > 0.15 → CALIBRATE FIRST
- R8: geology leakage check → coverage parity required
- R9: operator unlock → auto-detect dropzone data → validate → integrate
- R10: frontier testing gate → require 2+ zones before promoting to SELECTIVE
- R11: NDVI trend → ALLOW only at vegetated zones (Zambia, Peru)
- R12: spectral unmixing → ALLOW only at porphyry zones (Chuquicamata, Peru)

## 6. Blocked Items

| Resource | Status | Blocker | Unblock Action |
|----------|--------|---------|---------------|
| GA Bouguer gravity | BLOCKED_BY_PORTAL | WCS/REST return HTML | Manual download from GADDS |
| Peru EMIT granules | BLOCKED_BY_DOWNLOAD | Truncated (54%, 41%) | Re-download from Earthdata |
| Arizona Earth MRI | BLOCKED_BY_DOWNLOAD | Not downloaded | ScienceBase manual download |
| MINDAT API | BLOCKED_BY_AUTH | No API key | Register at api.mindat.org |
| EMAG2v3 | BLOCKED_BY_URL | NOAA 404 | Find updated URL |
| WGM2012 | BLOCKED_BY_URL | BGI 301 redirect | Find updated URL |

## 7. Key Learnings

1. **Fusion is real** — validated at 3 independent zones, 3 deposit types, 3 continents
2. **Fusion is NOT universal** — hurts at weak baselines (Peru -0.063)
3. **Baseline strength matters** — minimum ~0.73 AUC needed for fusion benefit
4. **Geology-first for weak zones** — enrich data before adding complexity
5. **Macrostrat API works** — but experiment had bias (queried only deposits)
6. **tpi_heterogeneity (d=+0.878)** — strongest single feature ever found
7. **The gap to 10/10 is DATA, not ML** — need geology, gravity, AEM, drill holes
