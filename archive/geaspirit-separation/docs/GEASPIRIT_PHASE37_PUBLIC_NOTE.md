# GeaSpirit Phase 37 — Tennant Creek Measured Validation

**Date:** 2026-03-29
**Classification:** Production validation — first measured results

## Summary

Phase 37 executed the first real ML validation at Tennant Creek using GA TMI magnetics:
- 33 quality-filtered deposit labels (IOCG + orogenic Au)
- Magnetics-only AUC: 0.762 (bootstrap), 95% CI [0.611, 0.897]
- Feature importance: gradient and analytic signal outperform raw TMI (consistent with IOCG geology)
- S2 spectral baseline not measured (requires GEE environment)

## Magnetics Verdict
**STILL_SELECTIVE_BUT_ZONE_DEPENDENT** — above random but needs S2 baseline comparison to confirm added value.

## Canonical Objective
**22.8/40 UNCHANGED (57%)**

## Honest Limitations
- 33 labels produces high per-fold variance — results are indicative, not definitive
- S2 baseline comparison pending — magnetics DELTA not yet measurable
- Grid resolution (~80m national) limits ceiling — survey-scale data would improve results
