# GeaSpirit Data Access Restrictions

Last updated: 2026-03-26 (Phase 20)

## Blocked Items (11)

| # | Resource | Status | Priority | Impact |
|---|----------|--------|----------|--------|
| 1 | GA Bouguer gravity | BLOCKED_BY_PORTAL | HIGH | Depth +1-2 pts |
| 2 | Peru EMIT granules | BLOCKED_BY_DOWNLOAD | HIGH | Porphyry confirmation |
| 3 | Arizona Earth MRI | BLOCKED_BY_DOWNLOAD | MEDIUM | New zone geophysics |
| 4 | MINDAT API key | BLOCKED_BY_AUTH | MEDIUM | Label enrichment |
| 5 | AEM conductivity | BLOCKED_BY_PORTAL | HIGH | Direct subsurface |
| 6 | EMAG2v3 | BLOCKED_BY_URL | LOW | Regional magnetics |
| 7 | WGM2012 | BLOCKED_BY_URL | LOW | Regional gravity |
| 8 | ECOSTRESS | NOT_DOWNLOADED | MEDIUM | Thermal inertia |
| 9 | Prithvi-EO-2.0 | NOT_DOWNLOADED | MEDIUM | Foundation embeddings |
| 10 | GEE Python API | NOT_CONFIGURED | LOW | Unified data access |
| 11 | Macrostrat parity | PARTIALLY_WORKING | HIGH | Geology CORE promotion |

## Manual Dropzones (all EMPTY as of 2026-03-26)

- `data/manual_drop/gravity/` — GA Bouguer GeoTIFF
- `data/manual_drop/peru_emit/` — EMIT_L2A_RFL_*.nc files
- `data/manual_drop/arizona_earthmri/` — TMI, K_conc, Th_conc, U_conc GeoTIFFs

## Depth Bottleneck

Current depth score: 4.1/10. All deposit-scale depth sources (gravity, AEM, Earth MRI) are BLOCKED.
Only GA TMI magnetics (80m) is active. Depth cannot improve without operator data drops.
