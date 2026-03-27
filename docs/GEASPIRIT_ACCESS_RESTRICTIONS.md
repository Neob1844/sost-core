# GeaSpirit Data Access Restrictions

Last updated: 2026-03-27 (Phase 22)

## Blocked Items (8 of 11 — 3 accessible)

| # | Resource | Status | Priority | Impact |
|---|----------|--------|----------|--------|
| 1 | GA Bouguer gravity | BLOCKED_BY_PORTAL | HIGH | Depth +1-2 pts |
| 2 | Peru EMIT granules | BLOCKED_BY_DOWNLOAD | HIGH | Porphyry confirmation |
| 3 | Arizona Earth MRI | BLOCKED_BY_DOWNLOAD | MEDIUM | New zone geophysics |
| 4 | MINDAT API key | BLOCKED_BY_AUTH | MEDIUM | Label enrichment |
| 5 | AEM conductivity | BLOCKED_BY_PORTAL | HIGH | Direct subsurface |
| 6 | EMAG2v3 | BLOCKED_BY_URL | LOW | Regional magnetics |
| 7 | WGM2012 | BLOCKED_BY_URL | LOW | Regional gravity |
| 8 | ECOSTRESS | **PARTIALLY_ACCESSIBLE** (earthaccess auth OK, 0 granules) | MEDIUM | Thermal inertia |
| 9 | Prithvi-EO-2.0 | NOT_DOWNLOADED | MEDIUM | Foundation embeddings |
| 10 | GEE Python API | **FULLY_ACCESSIBLE** (ee.Initialize works, SRTM OK) | LOW | Unified data access |
| 11 | Macrostrat parity | PARTIALLY_WORKING | HIGH | Geology CORE promotion |

### Phase 21 Access Changes

- **ECOSTRESS (#8):** Now accessible via NASA `earthaccess` Python library. Programmatic download of ECOSTRESS thermal data confirmed possible. Production download and integration pending.
- **GEE Python API (#10):** Now accessible and configured. Google Earth Engine Python API available for unified satellite data access. Production pipeline integration pending.

### Phase 22 Access Changes (2026-03-26)

- **GEE Python API (#10):** Upgraded to FULLY_ACCESSIBLE. ee.Initialize() confirmed working, SRTM query successful. Ready for data pipeline construction (raw S2 reflectance, NDVI composites).
- **ECOSTRESS (#8):** Downgraded to PARTIALLY_ACCESSIBLE. earthaccess library installed and authenticated, but search returns 0 granules for test AOI. Needs AOI/search parameter debugging.
- **8/11 items remain fully blocked.** All depth items (gravity, AEM, Earth MRI) still blocked. No manual dropzone data received.
- **Frontier validation blocked:** Raw S2 reflectance and multi-year NDVI time series not available in existing stacks. Real validation of spectral unmixing and NDVI trend requires new data pipelines.

## Manual Dropzones (all EMPTY as of 2026-03-27)

- `data/manual_drop/gravity/` — GA Bouguer GeoTIFF
- `data/manual_drop/peru_emit/` — EMIT_L2A_RFL_*.nc files
- `data/manual_drop/arizona_earthmri/` — TMI, K_conc, Th_conc, U_conc GeoTIFFs

## Depth Bottleneck

Current depth score: 4.1/10. All deposit-scale depth sources (gravity, AEM, Earth MRI) are BLOCKED.
Only GA TMI magnetics (80m) is active. Depth cannot improve without operator data drops.

## Phase 22 Follow-up

8 items remain fully blocked. GEE is FULLY_ACCESSIBLE and ready for pipeline construction. ECOSTRESS is PARTIALLY_ACCESSIBLE (needs AOI/search fix). The 4 HIGH-priority blockers (gravity, Peru EMIT, AEM, Macrostrat parity) remain unchanged. All depth items blocked. Next priority: build raw S2 reflectance and multi-year NDVI composite pipelines via GEE to enable real frontier validation.

GEE access enables Phase 23 raw data pipeline construction.
