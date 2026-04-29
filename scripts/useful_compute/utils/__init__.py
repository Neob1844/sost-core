"""Utility helpers for the multi-file Heavy useful-compute worker.

Modules:
  - parse_formula:         tiny formula → element-count parser
  - abundance_cost_tables: ABUNDANCE_PPM, COST_USD_KG, scoring helpers
  - pgm_replacement_tables: family detection + pgm_replacement_score
  - uncertainty_tables:    composition-only uncertainty scoring
  - mission_profiles:      MissionProfile registry + M3 mission score
  - canonical_hash:        deterministic JSON + SHA256
"""
