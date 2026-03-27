# GeaSpirit Phase 23 — Raw Data Engineering Specification

**Date:** 2026-03-26
**Status:** Planning document
**Prerequisite:** GEE Python API confirmed FULLY_ACCESSIBLE (Phase 22)

## Overview

Phase 23 constructs the raw data pipelines needed to validate frontier candidates that were blocked in Phase 22. The key enabler is Google Earth Engine (GEE), now confirmed accessible.

## A) Raw Sentinel-2 Reflectance Pipeline

**Source:** Sentinel-2 L2A (Surface Reflectance) via GEE collection `COPERNICUS/S2_SR_HARMONIZED`

**Preprocessing:**
1. Filter by AOI bounding box (per zone)
2. Filter by date range (most recent 2 years for composite)
3. Cloud masking using SCL band (values 4=vegetation, 5=bare soil, 6=water → keep 4,5; mask rest)
4. Median composite across time window
5. Select bands: B2 (490nm), B3 (560nm), B4 (665nm), B5 (705nm), B6 (740nm), B7 (783nm), B8 (842nm), B8A (865nm), B11 (1610nm), B12 (2190nm)

**Storage:** GeoTIFF, 10 bands, aligned to existing stack grid (reproject + resample to match)

**Output path:** `data/raw_reflectance/<zone>_s2_reflectance.tif`

**Use:** Input to spectral unmixing endmember decomposition (NNLS)

## B) Multi-Year NDVI Composite Pipeline

**Source:** Landsat Collection 2, Level 2 via GEE:
- Landsat 5 TM: `LANDSAT/LT05/C02/T1_L2` (1984-2012)
- Landsat 7 ETM+: `LANDSAT/LE07/C02/T1_L2` (1999-present)
- Landsat 8 OLI: `LANDSAT/LC08/C02/T1_L2` (2013-present)
- Landsat 9 OLI-2: `LANDSAT/LC09/C02/T1_L2` (2022-present)

**Temporal window:** 2000-2025 (25 years)

**Compositing logic:**
1. For each year: compute NDVI = (NIR - Red) / (NIR + Red)
2. Apply cloud mask (QA_PIXEL band)
3. Take annual maximum NDVI per pixel
4. Stack 25 annual layers

**Smoothing/QC:**
- Remove years with <5 valid observations per pixel
- Optional: Savitzky-Golay smoothing of annual time series

**Trend feature extraction:**
- ndvi_mean_longterm: mean of 25 annual values
- ndvi_trend_slope: linear regression slope
- ndvi_trend_strength: R² of linear fit
- ndvi_variability: standard deviation of annual values
- anomaly_persistence: fraction of years below long-term mean

**Output path:** `data/ndvi_timeseries/<zone>_ndvi_annual_stack.tif` (25-band GeoTIFF)

## C) GEE Integration Architecture

**How GEE is called:**
```python
import ee
ee.Initialize()
aoi = ee.Geometry.Rectangle([lon_min, lat_min, lon_max, lat_max])
collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED') \
    .filterBounds(aoi) \
    .filterDate('2023-01-01', '2025-01-01')
composite = collection.median().select(['B2','B3','B4','B5','B6','B7','B8','B8A','B11','B12'])
task = ee.batch.Export.image.toDrive(composite, description='s2_reflectance', region=aoi, scale=10)
task.start()
```

**What stays cloud-side:** Filtering, masking, compositing, NDVI computation
**What is exported locally:** Final composite GeoTIFFs (10-band reflectance, 25-band NDVI stack)

**Failure modes:**
- GEE quota exceeded (10,000 requests/day free tier)
- Export timeout for large AOIs (split into tiles)
- Band name mismatch between Landsat generations (harmonize)

**Auth assumptions:** ee.Initialize() with default credentials (service account or browser auth)

## D) Validation Plan

**Zones (priority order):**
1. Chuquicamata — spectral unmixing (porphyry alteration)
2. Zambia — NDVI trend (vegetated sediment Cu)
3. Kalgoorlie — both (comparison/control)
4. Peru — if baseline improves

**Metrics:** AUC (primary), PR-AUC, Brier score, feature importance

**Promotion criteria:**
- Real AUC delta > +0.005 at primary zone → SELECTIVE_VALIDATED
- Real AUC delta > +0.005 at 2+ zones → SELECTIVE_MULTI_ZONE
- Real AUC delta > +0.010 universal → CORE_CANDIDATE (CTO approval required)
- Real AUC delta < -0.005 → REJECTED
- Real AUC delta in [-0.005, +0.005] → INCONCLUSIVE

**What counts as real validation:**
- Features built from actual satellite data (not simulated)
- Labels from existing verified deposit databases
- Spatial block CV (no spatial leakage)
- Comparison against established baseline

## Timeline Estimate

- Pipeline construction: 1 phase
- Data export + QC: 1 phase
- Real validation: 1 phase
- Total: 2-3 phases before real frontier validation results
