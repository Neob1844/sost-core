# SOST Protocol — Platform Master Status

**Date:** 2026-03-26

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

- **Current Phase:** Phase 21 — Frontier Testing + Autonomy
- **Best AUC:** 0.882 (Chuquicamata full fusion)
- **Zones validated:** 3/6 (fusion works), 1 negative, 2 insufficient
- **Canonical Score:** 22.8/40 (57%) — FROZEN v4
- **Architecture:** type + zone + baseline aware, geology VALIDATED SELECTIVE
- **Depth activation layer:** 1 active, 3 ready, 2 regional, 2 future
- **11 blocked data items** (4 HIGH priority), all 3 dropzones EMPTY
- **Gating:** v7 (12 rules), **Registry:** v17
- **Frontier results (SIMULATED):** spectral unmixing SELECTIVE (porphyry, +0.008), NDVI trend SELECTIVE (vegetated, +0.012)
- **Autonomy layer:** v1 (scheduling + triggers + auto-recommendations)
- **Blocked items:** 9/11 (2 newly accessible: earthaccess, GEE)
- **Bottleneck:** depth data access, not architecture

### Phase History (recent)
- Phase 19: geology promoted VALIDATED SELECTIVE, depth proxy plan
- Phase 20: operator unlock checklist v3, depth activation layer, geology selective consolidation, frontier track v4, registry v16, gating v6
- Phase 21: spectral unmixing SELECTIVE (porphyry), NDVI trend SELECTIVE (vegetated), autonomy layer v1, gating v7, registry v17. ALL results SIMULATED.

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

- **GeaSpirit:** 9/11 blocked items (2 newly accessible via earthaccess + GEE) — 4 HIGH priority, all 3 dropzones EMPTY
- **Materials:** 4 databases planned but not connected (MP, OQMD, NOMAD, COD)
- **Autonomy:** Health/backup scripts created but cron not installed on VPS
- **Documentation:** Runbook + troubleshooting created, need VPS deployment
