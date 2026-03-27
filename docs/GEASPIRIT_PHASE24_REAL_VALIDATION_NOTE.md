# GeaSpirit Phase 24 — Real Frontier Validation Research Note

Date: 2026-03-27

## Summary

Phase 24 executed the first real frontier validation using exported Google Earth Engine
rasters. All 4 zones (Chuquicamata, Zambia, Kalgoorlie, Peru) had real Sentinel-2 pixels
and Landsat NDVI time series exported, processed through spectral unmixing, and assessed
against existing labels. Canonical score remains 22.8/40 (57%) UNCHANGED.

## What Was Done

1. **GEE Export (real):** Sampled 500 real S2 pixels per zone (10 bands each) from
   COPERNICUS/S2_SR_HARMONIZED 2023-2025 composites. Sampled 12 years (2013-2024) of
   Landsat 8 annual max NDVI at zone centers.

2. **Spectral Unmixing (real):** NNLS unmixing against 5 endmembers (iron oxide,
   clay/hydroxyl, silica, vegetation, dark mafic). Computed abundance fractions,
   alteration mix (iron + clay), spectral contrast, and entropy features.

3. **NDVI Trend Analysis (real):** Linear regression over 12-year NDVI time series.
   Computed slope, mean, std, R-squared per zone.

4. **Validation Attempt:** Checked for spatial alignment between GEE pixel grids and
   existing label databases. Found label column mismatch at 3 zones; missing labels
   at Chuquicamata. No AUC could be computed.

## Key Findings

### GEE Export Inventory

| Zone | S2 Images | S2 Pixels | NDVI Years |
|------|-----------|-----------|------------|
| Chuquicamata | 267 | 500 | 12 |
| Zambia | 528 | 500 | 12 |
| Kalgoorlie | 180 | 500 | 12 |
| Peru | 55 | 500 | 12 |

### Spectral Unmixing

- Chuquicamata: dominated by silica_bright (0.93), very low alteration (0.046). Consistent with hyperarid bright surface.
- Zambia: iron_oxide dominant (0.46), significant vegetation (0.27). Alteration mix 0.47. Highest entropy (0.87) = most spectrally diverse.
- Kalgoorlie: iron_oxide strongly dominant (0.90), alteration mix 0.90. Low entropy (0.25) = spectrally uniform iron-rich surfaces.
- Peru: iron_oxide dominant (0.64), vegetation (0.31). Alteration mix 0.64. Moderate entropy (0.52).

### NDVI Trends

| Zone | Mean NDVI | Slope/yr | R-squared | Verdict |
|------|-----------|----------|-----------|---------|
| Chuquicamata | 0.042 | -0.0016 | 0.026 | NOT_APPLICABLE_HYPERARID |
| Zambia | 0.310 | +0.0032 | 0.189 | PROMISING_VEGETATED |
| Kalgoorlie | 0.177 | -0.0024 | 0.014 | NEUTRAL |
| Peru | 0.255 | +0.00003 | 0.000 | NEUTRAL |

- Zambia is the only zone with a meaningful vegetation trend (positive slope, sufficient NDVI).
- Kalgoorlie 2020 NDVI spike (0.40 vs mean 0.18) likely reflects a wet year, not a real trend.
- Chuquicamata NDVI is too low (<0.05) for any vegetation-based analysis.

### Validation Blockers

- Label files exist for Zambia, Kalgoorlie, Peru but column names do not match expected
  ('label', 'target', 'deposit', 'y', 'class'). This is fixable.
- Chuquicamata has no label file in the labels directory.
- Even with correct columns, GEE-sampled pixel locations (random grid) do not match
  label point locations. Spatial alignment is needed.

## Canonical Impact

- **Previous:** 22.8/40 (57%) FROZEN v4
- **Updated:** 22.8/40 (57%) UNCHANGED
- **Score change justified:** No
- **Reason:** Features are real but validation is blocked by spatial alignment. No AUC
  improvement can be claimed without proper aligned validation.

## Honest Limitations

- GEE pixel sampling uses a random grid that does not align with label databases
- Spectral unmixing endmembers are approximate library values, not field-measured
- NDVI trend is single-pixel at zone center, not full raster coverage
- Kalgoorlie iron_oxide dominance (0.90) may reflect endmember library bias
- Canonical score cannot change without spatially-aligned AUC validation

## Data Artifacts Created

- `geaspirit/data/raw_s2/{zone}_s2_pixels_v1.npy` — 500x10 S2 reflectance arrays (4 zones)
- `geaspirit/data/raw_s2/{zone}_s2_coords_v1.npy` — pixel coordinates (4 zones)
- `geaspirit/data/raw_time_series/{zone}_ndvi_trend_real_v1.npy` — 5-element trend vectors (4 zones)
- `geaspirit/data/frontier/{zone}_real_unmixing_features_v1.npy` — 500x8 feature arrays (4 zones)
- `geaspirit/outputs/phase24/phase24_real_frontier_validation.json` — full results
- `geaspirit/outputs/phase24/phase24_real_frontier_validation.md` — markdown report

## Next Steps (Phase 25)

1. Fix label column detection (inspect actual column names in label CSVs)
2. Build spatial alignment: sample GEE features at exact label coordinates
3. Re-run unmixing + NDVI at label locations for proper AUC validation
4. Update canonical score only if real AUC improvement is confirmed
