# GeaSpirit Phase 42 — Frontier Sprint Results

**Date:** 2026-03-30

## Summary

Phase 42 tested three unconventional approaches and ran a full multi-stack comparison at Tennant Creek.

### 1. Temporal DNA validated

Multi-year pixel fingerprint (12-year NDVI+LST annual composites) achieved **0.858 AUC standalone** at Tennant Creek. This is the strongest non-spectral frontier family discovered in GeaSpirit, at +0.134 over the S2 spectral baseline (0.724). The physical basis: mineralized ground produces a distinct multi-year temporal signature in vegetation and thermal response due to altered soil chemistry, moisture retention, and rock thermal properties. Awaiting second zone confirmation before canonical adjustment.

### 2. Vegetation stress spectral: NEUTRAL at arid zones

Sentinel-2 red edge bands (B5, B6, B7) add nothing over standard S2 spectral at arid zones. At Tennant Creek, sparse vegetation means red edge indices measure rock mineralogy rather than plant chlorophyll stress — information already captured by SWIR bands. May produce a different result at vegetated zones where plant communities directly overlie mineralized soil.

### 3. Peru EMIT geographic fix: SUCCESS

The Peru EMIT geographic mismatch (identified Phase 41) has been corrected. A revised CMR search found 20 EMIT hyperspectral granules covering central Peru — the correct region matching the label sites. Three granules downloaded and validated. Ready for ML comparison in Phase 43.

### 4. Performance plateau discovered

The MEGA stack (39 features combining all validated and frontier families) reaches **0.889 AUC** at Tennant Creek — the best result ever at this zone. However, the comparison reveals diminishing returns: from ~20 to 39 features, the gain is <0.005 AUC. The satellite feature ceiling is approximately **0.89 AUC**. Going higher requires subsurface geophysics data (gravity, AEM) that cannot be acquired from orbit.

---

## Canonical: 23.4/40 UNCHANGED

Temporal DNA awaits second zone validation before canonical adjustment. The MEGA plateau result confirms that canonical improvements now require geophysics data, not additional satellite feature engineering.

---

## Phase 43 Plan

- Test Temporal DNA at Mt Isa (second zone validation)
- Run Peru EMIT ML comparison (granules ready)
- Test vegetation stress at Zambia (vegetated zone)
- Operator downloads: GA gravity + GSWA AEM (the depth unlock — both free, both requiring manual browser download)
