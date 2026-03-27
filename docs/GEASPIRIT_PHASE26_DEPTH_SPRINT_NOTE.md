# GeaSpirit Phase 26 — Depth Data Unblocking Sprint: Research Note

**Date:** 2026-03-27
**Status:** Internal research memo

## Abstract

Phase 26 attacked the DEPTH bottleneck (4.1/10) by auditing 8 depth-aware sources and building a pilot terrain+SAR feature family via Google Earth Engine. All 4 zones received depth-aware features extracted at exact label locations. Results show terrain features are competitive with spectral baselines at some zones (Peru +0.057 delta) but do not constitute true subsurface depth measurement.

## Source Audit (8 sources)

| Source | Access | Status | Depth Relevance |
|--------|--------|--------|----------------|
| GA National TMI Magnetics | FREE (NCI) | ACTIVE | Indirect — magnetic anomaly shape |
| GA Bouguer Gravity | BLOCKED (portal) | BLOCKED | Direct — gravity shape encodes depth |
| USGS Earth MRI | FREE (ScienceBase) | DROPZONE_EMPTY | High — airborne geophysics |
| SRTM Elevation | FREE (GEE) | USED | Indirect — terrain morphology |
| Sentinel-1 SAR | FREE (GEE) | USED | Indirect — surface roughness |
| EMAG2v3 | BLOCKED (URL 404) | BLOCKED | Regional only (3.7km) |
| AEM Conductivity (GSWA) | BLOCKED (portal) | BLOCKED | Highest — direct subsurface |
| ALOS World 3D DEM | FREE (GEE) | AVAILABLE | Same as SRTM |

## Pilot Results

| Zone | Depth-Only AUC | S2 Baseline | Delta | Verdict |
|------|---------------|-------------|-------|---------|
| Peru | 0.907 | 0.850 | +0.057 | Terrain features add value |
| Zambia | 0.642 | 0.640 | +0.002 | Neutral — depth features competitive but not additive |
| Kalgoorlie | 0.774 | N/A | — | No baseline comparison available |
| Chuquicamata | 0.769 | N/A | — | No baseline comparison available |

## Canonical Impact

**Score: 22.8/40 (57%) — UNCHANGED.** Terrain+SAR features provide structural geological context but are surface-derived proxies. They do not measure subsurface depth. Real depth score improvement requires gravity, AEM, or Earth MRI data — all blocked by manual portal downloads.

## Key Finding

Terrain features (elevation, slope, aspect, relative elevation, roughness) are surprisingly competitive for mineral prospectivity — particularly at Peru where `relative_elevation` alone carries 40% feature importance. This suggests topographic context encodes real geological signal. However, this is structural context, not depth estimation.

## Honest Limitations

- Terrain + SAR are surface measurements, not subsurface
- They provide geological structure context, not depth-to-target
- The DEPTH dimension requires gravity, AEM, or equivalent deposit-scale geophysics
- These sources remain blocked (manual download from portals needed)

## CTO Recommendation

1. Add terrain+SAR features to production as "structural context" family
2. Do NOT claim they solve DEPTH — they are COORDINATES/MINERAL support
3. The real depth unlock remains: GA gravity, GSWA AEM, USGS Earth MRI
4. Operator action needed for those 3 downloads
