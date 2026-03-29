# Passive Earth Signal — Canonical Impact Estimate V1

**Date:** 2026-03-29
**Current canonical:** 22.8/40 (57%)
**Dimensions:** Mineral 4.0/10, Depth 4.1/10, Coordinates 7.0/10, Certainty 7.7/10

## Impact Estimates by Hypothesis

| Hypothesis | Dimension | Estimated Impact | Confidence | Data Access | Notes |
|-----------|-----------|-----------------|------------|-------------|-------|
| Post-rain differential drying | MINERAL | +0.5 to +1.0 points | LOW | GEE accessible | Could reveal alteration, but signal may be subtle |
| Nocturnal thermal persistence | MINERAL | +0.3 to +0.5 points | MEDIUM | GEE accessible | Partially validated (thermal 20yr), incremental |
| Seasonal forcing response | MINERAL | +0.2 to +0.5 points | LOW | GEE accessible | Highly speculative, many confounders |
| Passive magnetotelluric | DEPTH | +1.0 to +3.0 points | HIGH (if accessible) | BLOCKED | Would be transformative — but no free data |
| Conductivity anomalies (AEM) | DEPTH, MINERAL | +1.0 to +2.0 points | HIGH (if accessible) | BLOCKED_BY_PORTAL | Same as existing AEM blockers |
| Gravity gradients | DEPTH | +0.5 to +1.0 points | MEDIUM | PARTIAL (WGM2012 coarse) | Regional only, not deposit-scale |
| SAR coherence | COORDINATES | +0.1 to +0.3 points | LOW | GEE accessible | Indirect, probably won't move needle |
| Non-testable ideas | NONE | 0.0 | N/A | N/A | By definition, no impact on production |

## Best Case Scenario (All Testable Hypotheses Succeed)

- MINERAL: 4.0 → 5.0-5.5 (+1.0 to +1.5)
- DEPTH: 4.1 → 4.1 (no change — all depth sources BLOCKED)
- COORDINATES: 7.0 → 7.1 (+0.1)
- CERTAINTY: 7.7 → 8.0 (+0.3, from better calibration with more features)
- **Potential canonical: 23.2-24.7 / 40 (58-62%)**

## Realistic Scenario (Historical success rate ~30%)

- Most hypotheses will be NEUTRAL or NEGATIVE (as Phase 14, 25, 27 showed)
- Realistic gain: +0.0 to +0.5 points total
- **Realistic canonical: 22.8-23.3 / 40 (57-58%)**

## Historical Success Rate Context

| Phase | Hypothesis | Outcome | AUC Delta |
|-------|-----------|---------|-----------|
| 14 | Peru fusion (NB+hydrology) | NEGATIVE | -0.063 |
| 25 | Spectral unmixing (real) | NEUTRAL | +0.001 |
| 25 | NDVI trend at Peru | NEGATIVE | -0.126 |
| 27 | Terrain combined with S2 | NEUTRAL/NEGATIVE | -0.068 to +0.001 |
| 9 | Neighborhood + hydrology fusion | POSITIVE | +0.012 to +0.022 |
| 10 | Chuquicamata full fusion | POSITIVE | +0.093 |
| 11 | Kalgoorlie magnetics | POSITIVE | +0.009 |
| 12 | Zambia fusion | POSITIVE | +0.024 |

**Empirical win rate:** ~40% of hypotheses yield genuine AUC improvement. ~30% are neutral. ~30% are negative or zone-specific failures.

## The Hard Truth

The bottleneck is DEPTH (4.1/10), and ALL depth-relevant sources are BLOCKED_BY_PORTAL or BLOCKED_BY_ACCESS:
- GA Bouguer gravity: BLOCKED_BY_PORTAL (returns HTML, not data)
- GSWA/DMIRS AEM: BLOCKED_BY_PORTAL (403 Forbidden programmatic access)
- USGS Earth MRI: BLOCKED_BY_DOWNLOAD (ScienceBase manual only)
- EMAG2v3: REGIONAL_BLOCKED (4km resolution, not deposit-scale)
- WGM2012: REGIONAL_BLOCKED (10km resolution, not deposit-scale)

Passive Earth signal hypotheses that use GEE will mostly help MINERAL, where we are already at 4.0/10. The marginal gain from a +1.0 MINERAL improvement is meaningful but not score-changing at the canonical level.

The transformative hypotheses (MT, AEM, detailed gravity) require data that is not freely accessible programmatically. Human operator action (portal registration, manual download) is the only path to DEPTH improvement.

## Promotion Criteria for New Hypotheses

For any passive_earth_signal_testable family to be promoted to selective or core:
1. Real AUC delta > +0.005 (above noise threshold)
2. Validated at 2+ independent zones
3. Physical mechanism documented (not coincidence)
4. No data leakage confirmed (coverage parity check)

**Canonical score: 22.8/40 UNCHANGED by this research line.**
