# Live Ingestion Report — Phase I Closure

**Date:** 2026-03-18T14:46:58.138612+00:00

## Sources

| Source | Fetched | Normalized | Inserted | Failed | Valid Structures |
|--------|---------|------------|----------|--------|-----------------|
| JARVIS | 200 | 200 | 200 | 0 | **200** |
| COD | 1901 | 50 | 50 | 0 | **47** |

## Corpus After Ingestion

| Metric | Count |
|--------|-------|
| Total materials | 250 |
| With valid structure | **247** |
| With band gap | 200 |
| With formation energy | 200 |
| ML-ready (band gap) | 200 |
| ML-ready (formation energy) | 200 |

## Structure Population

JARVIS structures converted via direct  adapter.
No CIF intermediate — avoids format compatibility issues.
COD structures downloaded as real CIF files and validated with pymatgen.
