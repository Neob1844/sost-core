# SOST Protocol — Platform Master Status

**Date:** 2026-03-27

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

- **Current Phase:** Phase 25 — Spatial Alignment Resolved + Real Frontier Validation
- **Best AUC:** 0.882 (Chuquicamata full fusion)
- **Zones validated:** 3/6 (fusion works), 1 negative, 2 insufficient
- **Canonical Score:** 22.8/40 (57%) — FROZEN v4, UNCHANGED
- **Architecture:** type + zone + baseline aware, geology VALIDATED SELECTIVE
- **Depth activation layer:** 1 active, 3 ready, 2 regional, 2 future
- **11 blocked data items** (4 HIGH priority), all 3 dropzones EMPTY
- **Gating:** v11, **Registry:** v21
- **Frontier validation:** Spatial alignment resolved (GEE sampleRegions). Unmixing NEUTRAL. NDVI zone-specific (Zambia 0.772 POSITIVE, Peru NEGATIVE). 2 zones GEE memory blocked.
- **GEE:** OPERATIONALIZED (memory limits at Kalgoorlie & Chuquicamata)
- **Autonomy layer:** v2 (promotion guardrails, execution queue, retry policy)
- **Bottleneck:** GEE memory limits at 2 zones + depth data access

### Phase History (recent)
- Phase 19: geology promoted VALIDATED SELECTIVE, depth proxy plan
- Phase 20: operator unlock checklist v3, depth activation layer, geology selective consolidation, frontier track v4, registry v16, gating v6
- Phase 21: spectral unmixing SELECTIVE (porphyry), NDVI trend SELECTIVE (vegetated), autonomy layer v1, gating v7, registry v17. ALL results SIMULATED.
- Phase 22: real validation attempted, both BLOCKED_BY_DATA. GEE FULLY_ACCESSIBLE. ECOSTRESS PARTIALLY_ACCESSIBLE. Autonomy v2. Gating v8 (14 rules). Registry v18.
- Phase 23: GEE pipelines built (S2 reflectance + NDVI), sample-tested with real data, export pending. Gating v9. Registry v19.
- Phase 24: First real GEE validation — 4 zones exported, unmixing+NDVI real features computed, validation blocked by spatial alignment. Gating v10. Registry v20.
- Phase 25: Spatial alignment resolved (GEE sampleRegions). Zambia: unmixing NEUTRAL, NDVI 0.772 POSITIVE. Peru: unmixing NEUTRAL, NDVI NEGATIVE. Kalgoorlie & Chuquicamata GEE memory blocked. Canonical unchanged. Gating v11. Registry v21.

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

- **GeaSpirit:** 8/11 fully blocked (GEE OPERATIONALIZED but memory-limited at 2 zones, ECOSTRESS PARTIALLY_ACCESSIBLE) — 4 HIGH priority, all 3 dropzones EMPTY, GEE tile strategy needed for Kalgoorlie & Chuquicamata
- **Materials:** 4 databases planned but not connected (MP, OQMD, NOMAD, COD)
- **Autonomy:** Health/backup scripts created but cron not installed on VPS
- **Documentation:** Runbook + troubleshooting created, need VPS deployment
