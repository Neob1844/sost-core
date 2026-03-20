# Orchestrator Report

**Corpus:** 6 materials | 9 elements | 5 spacegroups

## Chemical Space Coverage

Dense regions (>5K): 

Sparse regions (<50): Si, As, Ga, Cl, Na, Fe, Ti, U, O

### Element count distribution
| Elements | Count |
|---|---|
| 1 | 1 |
| 2 | 5 |

## Exotic Niches

- **rare_earth**: sparse coverage, high potential — Expand rare_earth materials — underrepresented, high exotic potential
- **actinide**: sparse coverage, high potential — Expand actinide materials — underrepresented, high exotic potential
- **heavy_pnictide**: sparse coverage, high potential — Expand heavy_pnictide materials — underrepresented, high exotic potential
- **heavy_chalcogen**: sparse coverage, high potential — Expand heavy_chalcogen materials — underrepresented, high exotic potential
- **quaternary_plus**: sparse coverage, high potential — Materials with 4+ elements are under-represented — high combinatorial novelty space

## Error Hotspots

- **formation_energy** value_range '1.0-5.0': MAE=0.4306 (8 samples) — medium
- **band_gap** value_range '3.0-6.0': MAE=1.1223 (17 samples) — high
- **band_gap** value_range '1.0-3.0': MAE=0.8735 (29 samples) — medium

## Retraining Proposals

### retrain_bg_priority [high]
Target: band_gap | Reason: Band gap has 2 error hotspots vs 1 for formation energy
Expected benefit: Reduce MAE in underperforming buckets
Recommended rung: 20K selective (focus on underperforming regions)

### retrain_fe_targeted [medium]
Target: formation_energy | Reason: 1 error hotspots detected in formation energy prediction
Expected benefit: Improve accuracy for complex/multi-element materials
Recommended rung: 20K with augmented sampling from sparse regions

### expand_then_retrain [medium]
Target: both | Reason: Corpus expansion before retraining typically yields better gains than retraining alone
Expected benefit: Broader coverage → better generalization → lower error across all buckets
Recommended rung: After expansion: 40K or selective 20K from expanded corpus

## Corpus Expansion Plan

| Source | Materials | Cost | Priority | Exotic Value | Status |
|---|---|---|---|---|---|
| materials_project | ~150K | $0 (API key) | high | high | normalizer_ready |
| cod | ~530K | $0 | medium | medium | normalizer_ready |
| aflow | ~3.5M | $0 | medium | high | normalizer_ready |
| oqmd | ~1M | $0 | low | medium | not_integrated |
| nomad | ~12M entries | $0 | low | medium | not_integrated |

## Action Summary

### Improve Now
- Address 3 error hotspot(s) — targets: formation_energy, band_gap
- Ingest materials_project (~~150K materials, $0 (API key))

### Don't Touch
- Production models (CGCNN FE, ALIGNN-Lite BG) — stable and promoted
- Existing corpus (75,993 JARVIS materials) — do not delete or recreate

### Data to Seek
- materials_project: ~150K materials ($0 (API key), easy)
- cod: ~530K materials ($0, moderate)
- aflow: ~3.5M materials ($0, moderate)

### Target Attention
- band_gap needs more attention — more error hotspots
