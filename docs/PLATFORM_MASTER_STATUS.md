# SOST Protocol — Platform Master Status

**Date:** 2026-03-28

## Modules Overview

| Module | Maturity | Autonomous? | Depends on External Data? |
|--------|----------|-------------|--------------------------|
| sost-node (blockchain) | PRODUCTION | YES | NO |
| sost-miner (PoW) | PRODUCTION | YES | NO |
| sost-cli (wallet) | PRODUCTION | YES | NO |
| Explorer (web) | PRODUCTION | YES | NO (reads from node) |
| Wallet (web) | PRODUCTION | YES | NO |
| GeaSpirit (mineral ML) | RESEARCH | PARTIAL | YES (satellite, geophysics, labels) |
| Materials Engine | RESEARCH | PARTIAL | YES (JARVIS, AFLOW, crystal DBs) |
| Auth Gateway | PRODUCTION | YES | NO |
| Website | PRODUCTION | YES | NO |

## GeaSpirit Status

- **Current Phase:** Phase 31 — Selective Geophysics Fusion + AEM Fallback (gravity DEFINITIVELY BLOCKED, magnetics validated, AEM path defined)
- **Best AUC:** 0.882 (Chuquicamata full fusion)
- **Zones validated:** 3/6 (fusion works), 1 negative, 2 insufficient
- **Canonical Score:** 22.8/40 (57%) — FROZEN v4, UNCHANGED
- **Architecture:** type + zone + baseline aware, geology VALIDATED SELECTIVE
- **Depth activation layer:** 1 active (magnetics), 3 GEE-accessible (SRTM, SAR, terrain), 5 blocked (gravity DEFINITIVELY BLOCKED, AEM next target, Earth MRI, EMAG2, WGM2012)
- **Gravity:** DEFINITIVELY BLOCKED — all 3 files corrupted (HTML error pages or empty stubs). GA GADDS/WCS returns HTML, not data.
- **AEM fallback:** GSWA/DMIRS portal — requires manual registration, Kalgoorlie surveys available
- **11 blocked data items** (4 HIGH priority), all 3 dropzones EMPTY
- **Gating:** v15, **Registry:** v25
- **Phase 28 QGIS operational layer:** Tool map (12 immediate, 5 optional, 3 skip), 5 reproducible workflows, canonical tool mapping per objective. QGIS strengthens COORDINATES + CERTAINTY, does NOT solve DEPTH or replace ML.
- **Phase 27 subsurface-aware family:** Standalone strong (Peru 0.902, Kalgoorlie 0.859, Chuquicamata 0.846, Zambia 0.682) but REDUNDANT with S2 spectral. Terrain reclassified SURFACE_STRUCTURE.
- **GEE:** OPERATIONALIZED — terrain infrastructure operational at all 4 zones
- **Autonomy layer:** v2 (promotion guardrails, execution queue, retry policy)
- **Bottleneck:** Depth data access — gravity DEFINITIVELY BLOCKED (corrupted files), terrain REDUNDANT with spectral, true depth needs AEM (next target via GSWA/DMIRS) or Earth MRI (manual portal). QGIS operational layer adds infrastructure for QA but does not change the bottleneck.

### Phase History (recent)
- Phase 19: geology promoted VALIDATED SELECTIVE, depth proxy plan
- Phase 20: operator unlock checklist v3, depth activation layer, geology selective consolidation, frontier track v4, registry v16, gating v6
- Phase 21: spectral unmixing SELECTIVE (porphyry), NDVI trend SELECTIVE (vegetated), autonomy layer v1, gating v7, registry v17. ALL results SIMULATED.
- Phase 22: real validation attempted, both BLOCKED_BY_DATA. GEE FULLY_ACCESSIBLE. ECOSTRESS PARTIALLY_ACCESSIBLE. Autonomy v2. Gating v8 (14 rules). Registry v18.
- Phase 23: GEE pipelines built (S2 reflectance + NDVI), sample-tested with real data, export pending. Gating v9. Registry v19.
- Phase 24: First real GEE validation — 4 zones exported, unmixing+NDVI real features computed, validation blocked by spatial alignment. Gating v10. Registry v20.
- Phase 25: Spatial alignment resolved (GEE sampleRegions). Zambia: unmixing NEUTRAL, NDVI 0.772 POSITIVE. Peru: unmixing NEUTRAL, NDVI NEGATIVE. Kalgoorlie & Chuquicamata GEE memory blocked. Canonical unchanged. Gating v11. Registry v21.
- Phase 26: Terrain depth pilot. 8 depth sources audited, 3 GEE-accessible. Peru depth-only 0.907 (+0.057). Zambia neutral. GEE terrain operational at 4 zones. Canonical unchanged. Gating v12. Registry v22.
- Phase 27: 9-feature subsurface-aware family via GEE. Standalone strong (Peru 0.902, Kalgoorlie 0.859) but REDUNDANT with S2. Terrain reclassified SURFACE_STRUCTURE. Canonical unchanged. Gating v13. Registry v23.
- Phase 28: QGIS operational layer spec. Tool map (12 immediate, 5 optional, 3 skip), 5 reproducible workflows, canonical tool mapping. QGIS strengthens COORDINATES + CERTAINTY, does NOT solve DEPTH or replace ML. Canonical unchanged. Gating v14. Registry v24.
- Phase 29: Geophysics-ready acquisition + QGIS pilot. Source selection final (10 sources audited). Geophysics ingest layer v1 (naming, directory, pipeline). 11-feature depth-aware family v2 operational at 4 zones. Pilot: standalone strong but REDUNDANT with spectral. Infrastructure ready, waiting for gravity/AEM/Earth MRI data. Canonical unchanged 22.8/40.
- Phase 30: Real magnetics depth integration. TMI magnetics validated (625x553, 1.05 MB). Mag+terrain 0.772 (+0.008 over terrain alone). Magnetics VALIDATED SELECTIVE. Gravity confirmed stub (39 bytes). Canonical unchanged.
- Phase 31: Gravity DEFINITIVELY BLOCKED (3 files: HTML error pages + empty stub). TMI magnetics CONFIRMED REAL. AEM fallback path defined (GSWA/DMIRS portal). Selective fusion: mag+terrain best at +0.008. Gating v15. Registry v25. Canonical unchanged 22.8/40.

## Materials Engine Status

- **Materials indexed:** 76,193
- **Properties predicted:** formation energy (MAE 0.1528), band gap (MAE 0.3422)
- **Candidate generation:** Material Mixer operational
- **Auto-retrain:** NOT_YET_IMPLEMENTED
- **External DB connections:** 2 active (JARVIS, AFLOW), 4 planned, 2 not connected

## What's Ready for Autonomy

| Component | Self-runs? | Self-heals? | Self-improves? |
|-----------|-----------|-------------|---------------|
| Blockchain node | YES | YES (systemd) | N/A |
| Miner | YES | YES (autossh) | N/A |
| Web/Explorer | YES | YES (nginx) | N/A |
| GeaSpirit inference | YES | NO | NO (manual retrain) |
| GeaSpirit data pipeline | PARTIAL | NO | NO |
| Materials inference | YES | NO | NO (manual retrain) |
| Backups | SCRIPTS_READY | NOT_INSTALLED | N/A |
| Health monitoring | SCRIPTS_READY | NOT_INSTALLED | N/A |

## What's Blocked

- **GeaSpirit:** 8/11 fully blocked (GEE OPERATIONALIZED with terrain infrastructure at 4 zones, ECOSTRESS PARTIALLY_ACCESSIBLE) — 4 HIGH priority, all 3 dropzones EMPTY, gravity DEFINITIVELY BLOCKED (corrupted files), AEM next target (GSWA/DMIRS registration needed), terrain REDUNDANT with spectral
- **Materials:** 4 databases planned but not connected (MP, OQMD, NOMAD, COD)
- **Autonomy:** Health/backup scripts created but cron not installed on VPS
- **Documentation:** Runbook + troubleshooting created, need VPS deployment
