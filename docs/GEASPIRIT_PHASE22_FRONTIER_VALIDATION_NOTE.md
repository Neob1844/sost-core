# GeaSpirit Phase 22 — Frontier Validation Attempt: Research Note

**Date:** 2026-03-26
**Authors:** SOST CTO / GeaSpirit Team
**Status:** Internal research memo

## Abstract

Phase 22 attempted real validation of two frontier mineral prospectivity features: spectral unmixing (sub-pixel mineral endmember decomposition) and multi-decadal NDVI trend analysis. Both validation attempts were blocked by data availability — existing satellite data stacks contain derived spectral indices rather than raw reflectance values, and NDVI data consists of single-date snapshots rather than multi-year time series. This does not invalidate the underlying physical hypotheses but identifies raw data pipeline construction as a prerequisite for frontier validation.

## Context

Phase 21 produced simulated results for two frontier candidates:
- Spectral unmixing: simulated +0.008 AUC at Chuquicamata (porphyry copper)
- NDVI multi-decadal trend: simulated +0.012 AUC at Zambia (sediment-hosted copper)

Both results were physically plausible but explicitly marked as SIMULATED. Phase 22's mandate was to validate these with real data.

## Methods Attempted

### Spectral Unmixing (Real Validation)
- Defined 5 endmembers: iron oxide, clay/hydroxyl, silica-bright, vegetation, dark mafic
- Searched for raw Sentinel-2 L2A reflectance at:
  - data/stack/<zone>_stack.tif
  - data/indices/<zone>_*.tif
  - data/stack/<zone>*.tif
- Found: stacks contain pre-computed indices (iron_oxide_ratio, clay_hydroxyl_index, ndvi, etc.)
- Missing: raw B2-B12 reflectance bands needed for spectral unmixing

### NDVI Trend (Real Validation)
- Searched for multi-temporal Landsat NDVI at:
  - data/landsat/<zone>_ndvi*.tif
  - data/indices/<zone>_ndvi*.tif
- Found: single-date NDVI band in existing stacks
- Missing: 20+ year annual NDVI composites from Landsat archive

## Blocking Factors

| Factor | Spectral Unmixing | NDVI Trend |
|--------|------------------|------------|
| Data needed | Raw S2 L2A reflectance (B2-B12) | Multi-year Landsat NDVI composites |
| Data available | Pre-computed spectral indices | Single-date NDVI snapshot |
| Gap | Raw reflectance pipeline not built | Time series assembly not built |
| Resolution | GEE can export raw L2A | GEE can composite annual NDVI |

## Access Update

- **Google Earth Engine:** FULLY_ACCESSIBLE — ee v1.7.18, Initialize() succeeds, SRTM data query works. This is the most likely path to building raw data pipelines.
- **ECOSTRESS/earthaccess:** PARTIALLY_ACCESSIBLE — library v0.14.0 installed, NASA Earthdata login works, but search returns 0 granules for Kalgoorlie test AOI. May need different product short_name or broader spatial query.

## Scientific Interpretation

The blocking of real validation does NOT constitute rejection of the frontier hypotheses:

1. **Spectral unmixing** has strong physical basis — sub-pixel mineral endmember decomposition is a well-established technique in remote sensing (Adams et al., 1986; Boardman, 1993). The technique requires raw reflectance, which is a data engineering problem, not a scientific one.

2. **NDVI trend analysis** is grounded in the observation that mineralized zones in vegetated terrains often show persistent vegetation stress anomalies (Sabins, 1999). The multi-decadal signal requires time series data, which GEE can provide.

3. Simulated results (+0.008 for porphyry, +0.012 for vegetated zones) are consistent with the physical mechanisms and deposit-type specificity observed across the platform.

## Next Required Data Engineering Steps

1. **Raw S2 reflectance pipeline:** Use GEE to export S2 L2A surface reflectance (B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12) for each AOI. Cloud-masked, median composite.
2. **Multi-year NDVI pipeline:** Use GEE to composite annual max-NDVI from Landsat 5/7/8/9 archive (2000-2025). Export per-year layers or trend statistics.
3. **Integration:** Save as GeoTIFF, aligned to existing stack grid. Re-run unmixing and trend feature builders with real data.
4. **Validation:** Spatial block CV with existing labels. Compare real AUC against simulated predictions.

## Honest Limitations

- All frontier results to date remain SIMULATED_ONLY
- Real validation requires data engineering effort (estimated 1-2 phases)
- Canonical score (22.8/40) cannot change until real evidence emerges
- Depth dimension (4.1/10) remains blocked by missing geophysical data (gravity, AEM, Earth MRI)
- The platform's main bottleneck has shifted from ML architecture to data access and engineering
