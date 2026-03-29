# GeaSpirit Phase 38 — GEE Reactivation and Comparison Attempt

**Date:** 2026-03-29
**Classification:** Production validation — comparison blocked

## Summary

Phase 38 reactivated Google Earth Engine for Tennant Creek. GEE authenticated successfully and found 1041 Sentinel-2 images for the AOI. However, interactive feature extraction hit GEE memory limits (same pattern as Phase 24). The S2 spectral baseline was not measured. Within-magnetics comparison showed positive results but does not answer the core question.

## GEE Status

| Check | Result |
|-------|--------|
| GEE initialized | YES — ee.Initialize() works |
| S2 images found | 1041 in AOI |
| Feature extraction | BLOCKED — User memory limit exceeded |
| Root cause | Interactive sampleRegions() too large for 333 pts × 1041 images |
| Fix | Export.table.toDrive() pattern (worked in Phases 25-27) |

## Within-Magnetics Results

| Stack | Features | CV AUC | Bootstrap AUC |
|-------|----------|--------|---------------|
| A — Smoothed TMI | TMI amplitude | 0.595 | 0.634 |
| B — Sharp TMI | Gradient + analytic signal | 0.668 | 0.755 |
| C — Combined | All 3 | 0.660 | 0.752 |

Phase 37 reproduced exactly (CV 0.668). Sharp features outperform smoothed within-magnetics. This is a within-magnetics comparison only — not S2 vs magnetics.

## Magnetics Verdict

**BLOCKED_BY_GEE_COMPARISON** — cannot determine if magnetics adds value over S2 without measuring S2 baseline. Magnetics remains STILL_SELECTIVE_BUT_ZONE_DEPENDENT (unchanged from Phase 37).

## Canonical Objective

**22.8/40 UNCHANGED (57%)**

No improvement is justified without the S2 comparison. The within-magnetics delta (+0.065 CV) does not qualify for a canonical score update.

## Next Step

Build GEE Export.table.toDrive() pipeline to extract S2 spectral features at Tennant Creek, download CSV locally, then measure the true S2 vs magnetics delta. This pattern has worked in Phases 25, 26, and 27.
