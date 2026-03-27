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

## Phase 23 Plan — Data Pipeline Construction + GEE Integration
Priority 1: Build raw S2 reflectance download pipeline (GEE or direct)
Priority 2: Build multi-year NDVI composite pipeline (GEE + Landsat archive)
Priority 3: Operator gravity data drop → depth activation
Priority 4: ECOSTRESS AOI/search fix
Priority 5: Real validation with proper data pipelines
Priority 6: Canonical re-evaluation if real evidence emerges

**Expected canonical trajectory:**
- Current: 22.8/40 (57%)
- With gravity: ~24/40 (60%)
- With gravity + AEM: ~27/40 (68%)
- With all depth data: ~30/40 (75%)
