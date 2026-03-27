# GeaSpirit Phase 23 — Raw Data Engineering + Real Frontier Validation: Research Note

**Date:** 2026-03-27
**Status:** Internal research memo

## Abstract

Phase 23 constructed real raw data pipelines via Google Earth Engine (GEE) for both frontier candidates: raw Sentinel-2 L2A reflectance (10 spectral bands) and multi-year Landsat NDVI time series (2013-2024, 12 annual composites). Both pipelines were successfully built and sample-tested with real satellite data. However, full raster export to local storage remains pending (requires async GEE batch export). Frontier validation therefore advances to PIPELINE_READY_VALIDATION_PENDING status.

## Key Results

### Raw S2 Reflectance Pipeline
- **Status:** PIPELINE_READY, sample-tested at all 4 zones
- **Data:** 10 bands (B2-B12), median composite, cloud-masked via SCL
- **Image counts:** Chuquicamata 292, Zambia 872, Kalgoorlie 295, Peru 292 scenes
- **Sample values:** Real reflectance confirmed at zone center points
- **Export:** Pending async ee.batch.Export.image.toDrive()

### Multi-Year NDVI Pipeline
- **Status:** PIPELINE_READY, 12/12 years sampled at all 4 zones
- **Data:** Landsat 8 annual max-NDVI, 2013-2024
- **Trends (real GEE data):**
  - Zambia: +0.0043/yr (greening, mean NDVI 0.30) — vegetation signal present
  - Peru: -0.0026/yr (slight browning, mean NDVI 0.25)
  - Kalgoorlie: -0.0035/yr (slight browning, mean NDVI 0.15) — arid, minimal signal
  - Chuquicamata: ~0.0/yr (mean NDVI 0.03) — hyperarid, no vegetation signal
- **Export:** Pending async batch export

### Frontier Validation Status
- Spectral unmixing: PIPELINE_READY_VALIDATION_PENDING (needs full raster export)
- NDVI trend: PIPELINE_READY_VALIDATION_PENDING (needs full raster export)
- Neither promoted nor rejected — honest intermediate state

### GEE Operationalization
- ee.Initialize() confirmed working
- 2 datasets operationalized: S2_SR_HARMONIZED, LANDSAT/LC08/C02/T1_L2
- 4 AOIs configured and tested
- Export pathway documented

### Depth Status
- Depth score: 4.1/10 unchanged
- GA TMI magnetics: ACTIVE (4 data files confirmed)
- All other depth sources: BLOCKED (manual drops empty)

## Honest Limitations
- Full raster export not yet completed (async GEE process)
- No real AUC improvement measured yet
- Canonical score unchanged: 22.8/40 (57%)
- Progress is in infrastructure (pipelines built), not in validated science (AUC gains)
- NDVI trend shows real vegetation trends at Zambia — promising but needs full validation
- Chuquicamata NDVI is near-zero (hyperarid) — NDVI trend NOT applicable there

## Next Steps
1. Execute GEE batch exports for all zones
2. Download exported GeoTIFFs
3. Run spectral unmixing on real reflectance rasters
4. Run NDVI trend features on real annual composites
5. Train and validate with spatial block CV
6. Update canonical score only if real AUC improvement confirmed
