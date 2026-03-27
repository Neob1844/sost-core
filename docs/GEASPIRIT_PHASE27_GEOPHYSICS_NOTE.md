# GeaSpirit Phase 27 -- Geophysics Unblocking Sprint

Date: 2026-03-27

## Objective

Attack the DEPTH bottleneck (4.1/10 in canonical score) by auditing geophysical
sources, accessing global GEE datasets for terrain/landform/water features, building
the first subsurface-aware feature family at label locations across all 4 zones, and
honestly reclassifying what is surface structure vs. genuine depth information.

## Source Triage

| Source | Status | Depth Type | Utility |
|--------|--------|-----------|---------|
| GA National TMI Magnetics | READY_NOW | indirect_magnetic | HIGH -- already integrated at Kalgoorlie |
| GEE SRTM Terrain Derivatives | READY_NOW | surface_structure | MEDIUM -- geological structure proxy, NOT true depth |
| GEE Sentinel-1 SAR | READY_NOW | surface_roughness | MEDIUM -- dropped from this sprint (band/memory issues) |
| GA Bouguer Gravity | MANUAL_BUT_HIGH_VALUE | direct_gravity | VERY HIGH -- encodes depth of buried density contrasts |
| USGS Earth MRI | MANUAL_BUT_HIGH_VALUE | airborne_geophysics | HIGH -- magnetics+radiometrics over mineral districts |
| GSWA AEM Conductivity | ACCESS_BLOCKED | direct_subsurface | HIGHEST -- direct conductivity at depth slices |
| EMAG2v3 Global Magnetics | LOW_PRIORITY | regional_magnetic | LOW -- 3.7km too coarse for deposit-scale |
| WGM2012 Global Gravity | LOW_PRIORITY | regional_gravity | LOW -- 3.7km too coarse for deposit-scale |

## GEE Collections Confirmed Available

| Collection | Bands | Use |
|-----------|-------|-----|
| CSP/ERGo/1_0/Global/SRTM_mTPI | elevation | Multi-scale topographic position index |
| CSP/ERGo/1_0/Global/SRTM_landforms | constant | Landform classification (categorical) |
| CSP/ERGo/1_0/Global/SRTM_topoDiversity | constant | Topographic diversity index |
| USGS/SRTMGL1_003 | elevation | SRTM 30m DEM |
| COPERNICUS/S1_GRD | HH, HV, angle | Sentinel-1 SAR (not used -- band issues) |
| JRC/GSW1_4/GlobalSurfaceWater | occurrence + 6 others | Surface water frequency |

No gravity or magnetic datasets found in GEE. The global geophysical datasets
(EMAG2v3, WGM2012) are not hosted on GEE and their original URLs are broken.

## Feature Family Built

9 features: 7 GEE-sourced + 2 derived.

**Base features (GEE):**
- elevation, slope, aspect (SRTM terrain)
- mTPI (CSP/ERGo multi-scale topographic position index)
- landform (CSP/ERGo categorical landform class)
- topo_diversity (CSP/ERGo topographic diversity)
- water_occurrence (JRC Global Surface Water, NaN -> 0)

**Derived features (local):**
- relative_elevation (elevation minus zone mean)
- slope_mTPI_interaction (slope * |mTPI|)

## Extraction Results

| Zone | Points | Valid | Coverage |
|------|--------|-------|----------|
| Kalgoorlie | 606 | 606 | 100% |
| Zambia | 128 | 128 | 100% |
| Chuquicamata | 276 | 276 | 100% |
| Peru | 284 | 284 | 100% |

Full coverage at all zones achieved by using unmask(0) on all GEE layers and
sampling at 90m scale (matching CSP/ERGo native resolution).

## Pilot Validation

| Zone | Subsurface AUC | P26 AUC | Combined | Delta | Verdict |
|------|---------------|---------|----------|-------|---------|
| Kalgoorlie | 0.8593 | 0.7740 | 0.8603 | +0.0010 | NEUTRAL |
| Zambia | 0.6823 | 0.6418 | 0.6149 | -0.0675 | NEGATIVE |
| Chuquicamata | 0.8455 | 0.7687 | 0.8248 | -0.0207 | NEGATIVE |
| Peru | 0.9021 | 0.9069 | 0.9031 | -0.0038 | NEUTRAL |

**Top feature by importance:** topo_diversity at 3/4 zones (Kalgoorlie 0.476,
Chuquicamata 0.495, Zambia 0.243). Peru top feature: relative_elevation (0.330).

**Key findings:**
- Standalone subsurface-aware AUC is strong (0.68--0.90) but combining with Phase 26
  features does NOT improve over the best standalone. This is consistent with both
  feature sets capturing overlapping geological structure information.
- topo_diversity is the most informative single feature, suggesting that landscape
  complexity (geological heterogeneity) correlates with mineralization.
- Combining terrain + P26 features is NEUTRAL or NEGATIVE at all zones. The features
  are redundant, not complementary.

## Terrain Honest Reclassification

Most features in this family are SURFACE STRUCTURE proxies. mTPI and water occurrence
provide indirect geological/subsurface context. Landform classification and topo
diversity capture geological heterogeneity but do NOT directly measure depth. Real
depth measurement requires gravity, AEM, or airborne magnetics -- all still blocked
by manual portal access.

| Feature | Honest Classification |
|---------|----------------------|
| elevation | SURFACE_STRUCTURE -- not depth |
| slope | SURFACE_STRUCTURE -- erosion proxy |
| aspect | SURFACE_STRUCTURE -- illumination/weathering |
| mTPI | MULTI_SCALE_LANDFORM -- geomorphological context |
| landform | GEOMORPHOLOGICAL_CLASS -- categorical surface class |
| topo_diversity | LANDSCAPE_COMPLEXITY -- geological heterogeneity proxy |
| water_occurrence | HYDROLOGICAL_CONTEXT -- indirect groundwater proxy |
| relative_elevation | LOCAL_STRUCTURE -- partially depth-indicative |
| slope_mTPI_interaction | STRUCTURAL_COMPLEXITY -- combined terrain signal |

**True depth features:** water_occurrence (indirect), mTPI (partial).
**NOT depth features:** elevation, slope, aspect, landform.

## Canonical Impact

- Previous: 22.8/40 (57%) FROZEN v4
- Updated: **22.8/40 (57%) -- UNCHANGED**
- DEPTH: INFRASTRUCTURE_READY -- 9-feature subsurface family built at 4 zones but
  no clear AUC improvement over existing features
- Reason: Surface-proxy features provide geological structure context but are
  redundant with existing terrain derivatives. True depth progress requires
  deposit-scale geophysics (gravity, AEM) which remain blocked by manual portal access.

## Blockers (Unchanged)

1. GA Bouguer Gravity -- GADDS portal manual download needed
2. GSWA AEM Conductivity -- DMIRS portal complex registration
3. USGS Earth MRI -- ScienceBase download for Arizona
4. All 3 manual dropzones remain EMPTY

## CTO Recommendation

1. Subsurface-aware terrain family is BUILT and OPERATIONAL but does not unlock new
   depth information beyond what satellite/terrain features already capture.
2. Do NOT claim these features solve DEPTH. They provide geological structure context
   that is largely redundant with existing features.
3. The depth bottleneck remains a DATA problem: gravity, AEM, and airborne magnetics
   data must be manually downloaded from government portals.
4. Operator action (manual downloads) is the single biggest blocker for real DEPTH
   progress. No amount of GEE feature engineering can substitute for true subsurface
   geophysical measurements.
5. topo_diversity from CSP/ERGo is a useful new feature (top importance at 3/4 zones)
   and should be included in the production feature stack as STRUCTURAL_CONTEXT.

## Outputs

- `/home/sost/SOST/geaspirit/outputs/phase27/phase27_geophysics_unblocking.json`
- `/home/sost/SOST/geaspirit/outputs/phase27/phase27_geophysics_unblocking.md`
- `/home/sost/SOST/geaspirit/outputs/phase27/features/{zone}_subsurface_aware_v1.npy` (4 zones)
- `/home/sost/SOST/geaspirit/outputs/phase27/features/{zone}_subsurface_labels.npy` (4 zones)
- Script: `/home/sost/SOST/geaspirit/scripts/run_phase27_geophysics_unblocking.py`
