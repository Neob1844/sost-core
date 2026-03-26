# Materials Discovery Engine — Master State Document

**Last updated:** 2026-03-26
**Version:** v3.2.0
**Status:** Operational research platform

---

## 1. System Definition

The Materials Discovery Engine is an autonomous computational platform for discovering novel materials with target properties. It uses graph neural networks on crystal structures to predict formation energy and band gap, then generates and screens theoretical candidates.

**Differentiator:** Focus on exotic, rare, and under-explored materials — not competing on accuracy for well-known compounds.

## 2. Strategic Direction

1. **Error minimization loop:** test → predict → compare → correct → retrain → iterate
2. **Corpus expansion:** ingest all available free public materials databases
3. **Exotic specialization:** prioritize novelty over precision on known materials
4. **Novelty-first search:** rank candidates by how different they are from known corpus

## 3. Current Modules

| Module | Status | Notes |
|--------|--------|-------|
| Data ingestion (JARVIS) | ACTIVE | 75,993 materials from JARVIS DFT 3D |
| Data ingestion (AFLOW) | ACTIVE | 200 materials |
| CIF structure parsing | ACTIVE | Validated on full corpus |
| Property prediction (formation energy) | ACTIVE | CGCNN, MAE 0.1528 eV/atom |
| Property prediction (band gap) | ACTIVE | ALIGNN-Lite, MAE 0.3422 eV |
| Material Mixer (candidate generation) | ACTIVE | Element substitution from parent pairs |
| Autonomous Discovery Engine | ACTIVE | Iterative campaigns with error learning |
| Multilingual search | ACTIVE | 9 languages, 270+ common names |
| Curated overrides | ACTIVE | 22 elemental + 22 compound |
| REST API | ACTIVE | 70+ endpoints |
| Novelty ranking | NOT_YET_IMPLEMENTED | Planned: out-of-distribution detection |
| Inverse design | NOT_YET_IMPLEMENTED | Planned: target property → generate structure |
| Auto-retrain pipeline | NOT_YET_IMPLEMENTED | Planned: weekly cron |
| Drift detection | NOT_YET_IMPLEMENTED | Planned: KS test on prediction distributions |
| Benchmark automation | NOT_YET_IMPLEMENTED | Planned: Matbench integration |

## 4. Learning Pipeline

```
1. SEED: Known materials from JARVIS + AFLOW (76,193)
2. GENERATE: Material Mixer creates candidates from parent pairs
3. PREDICT: CGCNN/ALIGNN-Lite estimate properties
4. VALIDATE: Compare predictions with known values (if available)
5. LEARN: Identify prediction errors, retrain on corrections
6. ITERATE: Repeat with refined model
```

Currently steps 1-3 are automated. Steps 4-6 require manual intervention.

## 5. Data Sources

| Source | Status | Materials | License |
|--------|--------|-----------|---------|
| JARVIS DFT 3D | ACTIVE | 75,993 | Public domain (NIST) |
| AFLOW | ACTIVE | 200 (sample) | CC-BY 4.0 |
| Materials Project | PLANNED | ~150,000 | CC-BY 4.0 |
| OQMD | PLANNED | ~1,000,000 | Open |
| NOMAD | NOT_CONNECTED | ~12M calculations | CC-BY 4.0 |
| COD | NOT_CONNECTED | ~500K structures | Open |
| MPDS | RESTRICTED_SOURCE | Requires license | Commercial |
| Matbench | NOT_CONNECTED | Benchmark suite | Open |

## 6. Access Restrictions

| Resource | Status | Blocker |
|----------|--------|---------|
| JARVIS data | ACTIVE | — |
| AFLOW data | ACTIVE | — |
| Materials Project API | PLANNED | Need API key (free registration) |
| OQMD bulk data | PLANNED | Need bulk download setup |
| NOMAD API | NOT_CONNECTED | Need to implement client |
| CGCNN model weights | ACTIVE | Local (trained) |
| ALIGNN-Lite weights | ACTIVE | Local (trained) |
| GPU for retraining | BLOCKED_BY_HARDWARE | CPU only, slow retraining |

## 7. Honest Limitations

- Property predictions are MODEL estimates, not experimental measurements
- Novelty is relative to our 76K corpus — candidates may exist in databases we haven't ingested
- No experimental validation pipeline — predictions need lab confirmation
- CPU-only inference is slow for large-scale screening
- Auto-retrain not yet implemented — requires manual trigger
