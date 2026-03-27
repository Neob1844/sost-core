# GeaSpirit Phase 25 — Spatial Alignment Layer + Real AUC Validation

Date: 2026-03-27

## Summary

Phase 25 resolved the spatial alignment bottleneck identified in Phase 24. The core
problem was that GEE pixels were sampled at random locations while labels existed at
specific deposit coordinates -- no spatial join was performed. Phase 25 extracts GEE
features at exact label coordinates using sampleRegions(), generates background points
within zone bounding boxes, and measures real cross-validated AUC.

Canonical score remains **22.8/40 (57%) UNCHANGED**.

## What Was Done

1. **Spatial audit:** Diagnosed why Phase 24 could not compute AUC. Root cause: GEE
   .sample() returns pixels at arbitrary locations, unrelated to label databases.
   Label files contain deposit-only records (no binary 0/1 column).

2. **Background generation:** Created negative examples by random sampling within each
   zone's bounding box, enforcing minimum 0.02 degree separation from all known deposits.
   Ratio: 3 background per deposit (capped at 300).

3. **GEE feature extraction at exact coordinates:** Used ee.FeatureCollection +
   sampleRegions() to extract Sentinel-2 reflectance (10 bands) and Landsat NDVI
   (10-year annual max) at precisely the deposit and background locations.

4. **Spectral unmixing:** NNLS against 5 endmembers (iron oxide, clay/hydroxyl, silica,
   vegetation, dark mafic). Derived 8 features: 5 abundance fractions + contrast +
   entropy + alteration index.

5. **Real AUC validation:** 5-fold stratified cross-validation with GradientBoosting.
   Compared: S2 baseline, unmixing-only, S2+unmixing, NDVI-only, all combined.

## Results

### Zones Completed (2 of 4)

| Zone | Points | Baseline S2 | Unmix Only | S2+Unmix | Delta | Verdict |
|------|--------|-------------|------------|----------|-------|---------|
| Zambia | 128 (32+96) | 0.6403 | 0.6163 | 0.6414 | +0.001 | NEUTRAL |
| Peru | 280 (71+209) | 0.8496 | 0.7350 | 0.8466 | -0.003 | NEUTRAL |

### NDVI Trend Results

| Zone | NDVI Only | All Combined | Verdict |
|------|-----------|--------------|---------|
| Zambia | 0.7721 | 0.7096 | POSITIVE |
| Peru | 0.7243 | 0.8304 | NEGATIVE |

### Zones Blocked (2 of 4)

- **Kalgoorlie:** GEE memory limit exceeded (606 points, 540 S2 images)
- **Chuquicamata:** GEE memory limit exceeded (276 points, 676 S2 images)

## Key Findings

1. **Unmixing adds nothing over raw S2 bands.** At both validated zones, the combined
   S2+unmixing AUC is within noise of the S2-only baseline. Unmixing-only is strictly
   worse than S2-only. The 5-endmember linear unmixing does not capture discriminative
   mineralogical signal beyond what raw reflectance already provides.

2. **NDVI trend is zone-specific.** At Zambia (vegetated Copperbelt), NDVI alone reaches
   0.772 AUC -- substantially above S2 baseline (0.640). At Peru (arid Andes), NDVI
   alone is worse (0.724 vs 0.850 baseline). Vegetation proxies help in vegetated mining
   districts but not universally.

3. **Peru S2 baseline is surprisingly strong at 0.850.** This may reflect spectral
   separation between porphyry-hosting Andean geology and random background, or could
   indicate the background points are too geologically distinct from deposits (a form
   of easy-negative bias).

4. **Spatial alignment layer works.** The sampleRegions() approach successfully extracts
   features at exact label coordinates. This is reusable infrastructure for all future
   phases.

5. **GEE memory limits block 2 zones.** Kalgoorlie and Chuquicamata need smaller batch
   sizes or pre-filtered image collections to stay within GEE free-tier quotas.

## Canonical Impact

- **Previous:** 22.8/40 (57%) FROZEN v4
- **Updated:** 22.8/40 (57%) -- UNCHANGED
- **Mineral (4.0/10):** UNCHANGED. Unmixing does not improve AUC.
- **Depth (4.1/10):** UNCHANGED. No new subsurface data.
- **Coordinates (7.0/10):** Architecture improved (spatial alignment layer), but no
  score change until it produces AUC gains.
- **Certainty (7.7/10):** UNCHANGED.
- **Reason:** No validated improvement exceeding +0.005 AUC at any zone.

## Honest Limitations

- Cross-validation is StratifiedKFold, not spatial-block CV (may be optimistic)
- Background points are random within bbox, not geology-informed
- Endmembers are approximate library values, not field-calibrated
- Spectral unmixing is surface-informed, not subsurface detection
- Small sample sizes at some zones (Zambia: 32 deposits) produce high-variance estimates
- Two of four zones could not be validated due to GEE memory limits

## Next Steps

- Reduce batch sizes or use tighter date filters to unblock Kalgoorlie and Chuquicamata
- Test geology-informed background generation (stratified by lithology)
- Evaluate spatial-block CV to check for spatial autocorrelation bias
- The gap to 10/10 remains a DATA problem, not architecture
