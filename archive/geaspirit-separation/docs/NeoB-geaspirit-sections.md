<!-- Archived from NeoB.md on 2026-08-09 (GeaSpirit separation, phase 1/2). -->

## GeaSpirit Platform (Mineral Intelligence)

Located in `geaspirit/`. Python-based satellite mineral prospectivity mapping.

**Current state (Phase 28 — QGIS operational layer spec):**
- Multi-source exploration intelligence platform (not satellite-only)
- 6 supervised zones: Kalgoorlie (0.879 AUC), Chuquicamata (0.882), Peru (0.698 baseline), Arizona (0.718), Zambia (0.760), Pilbara (FAILED)
- Phase 28: QGIS operational layer spec — practical tool map (12 immediate tools, 5 optional, 3 not-worth), reproducible workflows (5 workflows), canonical tool mapping per objective. QGIS strengthens COORDINATES and CERTAINTY but does NOT solve DEPTH or replace ML. Canonical 22.8/40 UNCHANGED.
- Phase 27: 9-feature subsurface-aware family built at all 4 zones via GEE. topo_diversity top feature at 3/4 zones (CSP/ERGo landform). Standalone AUCs strong: Peru 0.902, Kalgoorlie 0.859, Chuquicamata 0.846, Zambia 0.682. Combined with S2: REDUNDANT (Kalgoorlie +0.001 NEUTRAL, Zambia -0.068 NEGATIVE, Chuquicamata -0.021 NEGATIVE, Peru -0.004 NEUTRAL). Terrain reclassified SURFACE_STRUCTURE, not true depth. Canonical 22.8/40 UNCHANGED. Real depth needs GA gravity, GSWA AEM, USGS Earth MRI (manual portals).
- Phase 24: First real GEE validation on exported rasters (no simulation). 4 zones exported. Validation blocked by spatial alignment.
- Phase 23: GEE pipelines built for raw S2 reflectance and multi-year NDVI. Sample-tested with real data.
- Phase 22: real validation of spectral unmixing + NDVI trend both BLOCKED_BY_DATA, GEE FULLY_ACCESSIBLE, ECOSTRESS PARTIALLY_ACCESSIBLE, autonomy v2, gating v8 (14 rules), registry v18
- Phase 21: spectral unmixing SELECTIVE (porphyry, simulated +0.008), NDVI trend SELECTIVE (vegetated, simulated +0.012), autonomy layer v1, gating v7 (12 rules), registry v17
- Phase 20: operator unlock checklist v3 (11 items), depth activation layer, geology VALIDATED SELECTIVE, frontier track v4
- Phase 19: geology officially promoted to VALIDATED SELECTIVE. Depth proxy plan: 1 active, 5 blocked. All deposit-scale depth sources BLOCKED. 11 blocked items documented.
- Phase 12 Zambia full fusion (sat+NB+hydro): 0.737 → 0.760 (+0.024 AUC), Cal Brier 0.139. Multi-source fusion confirmed at 3 zones.
- Phase 11 Kalgoorlie full fusion (sat+mag+thermal+nb+hydro+embeddings): 0.8654 → 0.8785 (+0.013 AUC). Best calibrated Brier ever: 0.096. Gravity BLOCKED (manual download needed).
- Phase 10 Chuquicamata full fusion (sat+geo+EMIT+neighborhood+hydrology): 0.789 → 0.882 (+0.093 AUC) — biggest improvement ever
- Phase 9 information fusion: neighborhood context + hydrology + magnetics + isotonic calibration
- Kalgoorlie 0.8654 → 0.8785 (+0.013 AUC), Zambia 0.7366 → 0.7584 (+0.022 AUC)
- Neighborhood context multi-zone validated (generalized to Zambia)
- Isotonic calibration: all Brier scores below 0.17, Kalgoorlie 0.0999
- Canonical objective FROZEN (v4): 22.8/40 (57%). Mineral 4.0/10, Depth 4.1/10, Coords 7.0/10, Certainty 7.7/10. Methodology fixed, changes require CTO approval.
- Type-aware auto-selection: tests all families, selects best per zone
- Validated: satellite baseline (universal), thermal 20yr (modest), EMIT (porphyry-specific), PCA embeddings (Kalgoorlie-specific), magnetics (+0.009 real), neighborhood context (multi-zone validated)
- Rejected: spatial gradients, ML residuals, EMIT at orogenic Au, cross-zone transfer
- tpi_heterogeneity d=+0.878 = strongest single feature ever found
- Critical fix: Phase 7 magnetics were EMPTY (wrong tiles). Fixed with GA national TMI via NCI THREDDS
- Peru EMIT: blocked (truncated download), 50 granules available
- Blockers: Peru EMIT, GSWA geology maps, GA gravity, detailed AEM
- Scripts in `geaspirit/scripts/`, data in `~/SOST/geaspirit/data/`
- See: docs/GEASPIRIT_TECHNOLOGY_SUMMARY.md, docs/GEASPIRIT_CTO_NEXT_PHASE.md, docs/GEASPIRIT_FRONTIER_RESEARCH_V5.md (extended with CTO sprint findings + 13 sections)


## GeaSpirit Status

Located in `/home/sost/SOST/geaspirit/`. Multi-source exploration intelligence platform.

**Phase history:** Thermal V2 (confirmed d=-0.68) → Phase 5I (multi-zone thermal) → Phase 6A-6E (EMIT, PCA, gradients, type-aware selection, universal matrix) → Phase 7 (magnetics, embeddings) → CTO Sprint (multi-scale anomaly, neighborhood context) → Phase 8B (public sync, canonical assessment) → Phase 9 (information fusion: neighborhood + hydrology + magnetics + calibration) → Phase 10 (Chuquicamata full fusion +0.093 AUC) → Phase 11 (Kalgoorlie full fusion +0.013 AUC, gravity blocked) → Phase 12 (Zambia fusion +0.024 AUC, manual data layer, canonical V3 22.9/40) → Phase 13 (data closure, canonical score methodology frozen at v4: 22.8/40) → Phase 14 (Peru fusion NEGATIVE -0.063, fusion not universal) → Phase 15 (baseline-aware gating, 8 rules, 27 families, architecture: type+zone+baseline aware) → Phase 16 (Macrostrat API activated, Peru geology-first +0.168 AUC, bias caveat) → Phase 17 (geology bias fix, Zambia lithology genuine +0.054, Peru still leaky) → Phase 18 (coverage parity fix, lithology content > has_data at all 3 zones, geology genuine) → Phase 19 (geology promoted VALIDATED SELECTIVE, depth proxy plan: 1 active/5 blocked, 11 blocked items documented) → Phase 20 (operator unlock, depth activation layer, geology selective consolidation, frontier track v4, registry v16, gating v6) → Phase 21 (spectral unmixing SELECTIVE porphyry, NDVI trend SELECTIVE vegetated, autonomy layer v1, gating v7, registry v17) → Phase 22 (real validation attempted, both BLOCKED_BY_DATA, GEE accessible, autonomy v2, gating v8, registry v18) → Phase 23 (raw data engineering via GEE, pipelines built+sample-tested, validation pending export, gating v9, registry v19) → Phase 24 (first real GEE validation, 4 zones exported, unmixing+NDVI real features, validation blocked by spatial alignment, canonical unchanged) → Phase 25 (spatial alignment resolved via GEE sampleRegions, spectral unmixing NEUTRAL, NDVI zone-specific: Zambia 0.772 POSITIVE, Peru NEGATIVE, 2 zones GEE memory blocked, canonical unchanged) → Phase 26 (terrain depth pilot: 8 sources audited, 3 GEE-accessible, Peru depth-only 0.907 +0.057, Zambia neutral, GEE terrain operational at 4 zones, canonical unchanged) → Phase 27 (9-feature subsurface-aware family via GEE, topo_diversity top feature 3/4 zones, standalone strong but REDUNDANT with S2, terrain reclassified SURFACE_STRUCTURE, canonical unchanged) → Phase 28 (QGIS operational layer spec: tool map, reproducible workflows, canonical tool mapping, canonical unchanged).

**Selected families by zone (Phase 9):**
- Kalgoorlie: satellite + thermal + PCA + magnetics + gravity + neighborhood + hydrology → **AUC 0.922** (Phase 48 S2+gravity fusion)
- Chuquicamata: satellite + thermal + EMIT + geology + neighborhood + hydrology → AUC 0.882
- Peru/Arizona: satellite + thermal → AUC 0.698/0.718
- Zambia: satellite + neighborhood + hydrology → AUC 0.760

**Canonical Score: 25.1/40 (63%).** Mineral 4.0/10, Depth **6.0/10**, Coords 7.0/10, Certainty **8.1/10**. Phase 48 validated gravity fusion.
**Key insight:** Gravity data validated as CORE signal for DEPTH. Next bottleneck: MINERAL (needs MINDAT + temporal features).
**Phase 47 result:** Beta recalibration (Brier 72% improvement), GEE export foundation, manual geophysics intake pipelines, temporal DNA scaffold.
**Phase 48 result:** S2+gravity fusion at Kalgoorlie: AUC 0.899→0.922 (+0.023). AU Gravity 2019 classified CORE. EarthMRI Arizona classified CORE (coverage-limited). WGM2012 classified SUPPORT.
**Phase 9 result:** Neighborhood context + hydrology + magnetics fusion + isotonic calibration. Kalgoorlie +0.012, Zambia +0.022 AUC. Multi-zone validated.
**Phase 10 result:** Chuquicamata full fusion (sat+geo+EMIT+neighborhood+hydrology) = 0.882 AUC (+0.093). Biggest single-experiment improvement ever.
**Phase 11 result:** Kalgoorlie full fusion (sat+mag+nb+hydro+embeddings) = 0.879 AUC (+0.013). Best calibrated Brier ever: 0.096. Gravity BLOCKED (GA endpoints return HTML portal).
**Phase 12 result:** Zambia full fusion (sat+NB+hydro) = 0.760 AUC (+0.024), Cal Brier 0.139. Multi-source fusion confirmed at 3 independent zones (Chuquicamata +0.093, Kalgoorlie +0.013, Zambia +0.024). Manual data dropzones for gravity, Peru EMIT, Arizona Earth MRI. MINDAT blocked (needs API key). Canonical V3: 22.9/40 (57%).
**Phase 13 result:** Data closure. All 3 manual dropzones EMPTY (operator action needed). Peru EMIT 2 raw granules both TRUNCATED. MINDAT BLOCKED (no API key). Canonical score methodology FROZEN at v4: 22.8/40 (57%). Fusion still validated at 3 zones.
**Phase 14 result:** Peru fusion NEGATIVE (-0.063). NB+hydrology hurts weak-baseline zones. Fusion confirmed at 3/4 zones (not universal).
**Phase 15 result:** Baseline-aware gating. Peru diagnostic: baseline 0.698 too weak for fusion (threshold ~0.73). 8 adaptive gating rules. Frontier registry v2: 27 families (6 core, 3 selective, 2 rejected, 1 neutral, 10 frontier, 5 blocked). Architecture: type-aware + zone-aware + baseline-aware.
**Phase 16 result:** Macrostrat API activated (20/20 all zones). Peru geology-first +0.168 AUC (CAVEAT: bias in API-only-at-deposits). Architecture: type+zone+baseline aware + geology-first validated.
**Phase 17 result:** Geology bias fix (balanced Macrostrat query). Zambia lithology content genuine +0.054 AUC (LOW leakage, content > has_data). Peru still leaky (coverage asymmetry: 70% deposits vs 23% background). FIRST honest evidence geology helps by CONTENT, not just data presence.
**Phase 18 result:** Coverage parity fix + clean geology validation. Peru +0.104 (lithology), Kalgoorlie +0.011 (lithology), both LOW leakage. Lithology content > has_data at ALL 3 tested zones (Zambia +0.054, Peru +0.104, Kalgoorlie +0.011). Geology via Macrostrat GENUINE across zones, parity still needs improvement.
**Phase 19 result:** Geology officially promoted PROMISING → VALIDATED SELECTIVE (3-zone evidence). Depth proxy plan: 1 active (magnetics), 5 blocked (gravity, AEM, Earth MRI, EMAG2, WGM2012), 2 regional-only. All deposit-scale depth sources BLOCKED. 11 blocked data items documented. Depth remains weakest dimension (4.1/10). The next bottleneck is depth, not architecture.
**Phase 20 result:** Operator unlock checklist v3 (11 blocked items, 4 HIGH priority). Depth activation layer (1 active, 3 ready, 2 regional, 2 future). Geology consolidated as VALIDATED SELECTIVE. All 3 dropzones still EMPTY. Gating v6 (10 rules). Frontier track v4: spectral_unmixing + NDVI_trend selected for Phase 21. Registry v16. Canonical score unchanged 22.8/40 (57%). Bottleneck: depth data access, not architecture.
**Phase 21 result:** Spectral unmixing VALIDATED_SELECTIVE (porphyry, simulated +0.008 Chuquicamata). NDVI trend SELECTIVE_VEGETATED (simulated +0.012 Zambia). 9/11 items still blocked, 2 newly accessible (earthaccess, GEE). Autonomy layer v1 (scheduling + triggers + auto-recommendations). Gating v7 (12 rules). Registry v17. Canonical unchanged 22.8/40 (57%). ALL frontier results SIMULATED — production validation pending.
**Phase 22 result:** Real validation of spectral unmixing and NDVI trend BLOCKED_BY_DATA (stacks have derived indices, not raw reflectance; NDVI is single snapshot, not time series). GEE FULLY_ACCESSIBLE. ECOSTRESS PARTIALLY_ACCESSIBLE. Autonomy v2 with promotion guardrails. Gating v8 (14 rules). Registry v18. Canonical unchanged 22.8/40 (57%). Honest: frontier candidates remain simulated only.
**Phase 23 result:** GEE pipelines built for raw S2 reflectance (4 zones, 10 bands) and multi-year NDVI (12 years, 4 zones). Sample-tested with real data. Full export pending. Frontier validation PIPELINE_READY. Depth unchanged 4.1/10. Canonical unchanged 22.8/40.
**Phase 24 result:** First real frontier validation on exported GEE rasters (no simulation). 4 zones exported. Validation blocked by spatial alignment.
**Phase 25 result:** Spatial alignment resolved — GEE sampleRegions() extracts at exact label coordinates. Zambia: S2 baseline 0.640, unmixing +0.001 (NEUTRAL), NDVI 0.772 (POSITIVE — best single family). Peru: S2 baseline 0.850, unmixing -0.003 (NEUTRAL), NDVI 0.724 (NEGATIVE). Kalgoorlie & Chuquicamata: blocked by GEE memory limits. Spectral unmixing: NEUTRAL — adds nothing over raw S2 reflectance. NDVI trend: zone-specific — strong at vegetated zones, weak at arid zones. Canonical: 22.8/40 UNCHANGED — no improvement exceeding +0.005 threshold.
**Phase 26 result:** Terrain depth pilot. 8 depth sources audited, 3 GEE-accessible used (SRTM, SAR, terrain derivatives). 4 zones piloted: Peru depth-only AUC 0.907 (+0.057 vs S2 baseline — terrain features add real value), Zambia 0.642 (+0.002, neutral), Kalgoorlie 0.774, Chuquicamata 0.769. Canonical 22.8/40 UNCHANGED — terrain features are surface proxies, not subsurface depth. True depth unlock needs GA gravity, AEM, Earth MRI (all blocked). GEE terrain infrastructure operational at all 4 zones.
**Phase 27 result:** 9-feature subsurface-aware family built at all 4 zones via GEE (CSP/ERGo landform dataset). topo_diversity = top feature at 3/4 zones. Standalone AUCs strong: Peru 0.902, Kalgoorlie 0.859, Chuquicamata 0.846, Zambia 0.682. Combined with S2: Kalgoorlie +0.001 (NEUTRAL), Zambia -0.068 (NEGATIVE), Chuquicamata -0.021 (NEGATIVE), Peru -0.004 (NEUTRAL). Features are REDUNDANT with existing spectral — adding them does not improve AUC. Terrain reclassified: SURFACE_STRUCTURE, not true depth. Canonical 22.8/40 UNCHANGED. Real depth needs GA gravity, GSWA AEM, USGS Earth MRI (all manual portals).
**Phase 28 result:** QGIS operational layer spec. Practical tool map: 12 immediate-value tools, 5 optional, 3 not-worth-prioritizing. 5 reproducible workflows (Label-Raster QA, AOI Clipping, Terrain Context, Multi-Layer Target Review, Geophysics Preparation). Canonical tool mapping per objective dimension. QGIS strengthens COORDINATES (alignment QA) and CERTAINTY (visual inspection) but does NOT solve DEPTH and does NOT replace ML. Canonical 22.8/40 UNCHANGED.
**Full docs:** GEASPIRIT_TECHNOLOGY_SUMMARY.md, GEASPIRIT_CTO_NEXT_PHASE.md, GEASPIRIT_CANONICAL_PATH.md

**Language guardrails:**
- ALWAYS say: "thermal long-term proxy family", "moderate but real improvement"
- NEVER say: "direct subsurface detection", "detect minerals at depth", "nobody has published this"
- Thermal helps but does not dominate satellite spectral indices
- Thermal adds less where spectral/SAR baseline already saturates
