# Materials Engine — Phase IX Outcome Report

**Date:** 2026-03-24
**Phase:** IX — Scientific Operations Layer

---

## Executive Summary

Phase IX transforms the validation bridge into a scientific operations layer with batch workflows, longitudinal evidence accumulation, calibration reporting, and multi-dimensional tracking. The engine can now:

1. **Batch validation** — group candidates into prioritized batches
2. **Evidence accumulation** — track accuracy by family, strategy, campaign, and prediction origin
3. **Scientific reporting** — generate operations summaries, family calibration reports, strategy performance reports
4. **Longitudinal tracking** — family MAE, overconfidence rates, strategy yield, reliability rankings

---

## New Components

| Module | Purpose |
|--------|---------|
| `batch.py` | ValidationBatch + BatchManager for batch lifecycle |
| `evidence.py` | EvidenceStore for longitudinal tracking by family/strategy/campaign/origin |
| `reporting.py` | 5 report types: operations summary, family calibration, strategy performance, priority handoff, markdown export |

## Evidence Dimensions

| Dimension | Tracks |
|-----------|--------|
| Family (element set) | FE errors, BG errors, classifications, overconfidence rate |
| Strategy (method) | Errors, classifications, validation yield |
| Campaign (profile) | Count, classifications, confirmed count |
| Origin (direct_gnn/proxy) | Errors per prediction type |

## Reports Available

1. **Validation Operations Summary** — registry + batches + evidence + calibration
2. **Family Calibration Report** — per-family MAE, overconfidence, trust adjustment
3. **Strategy Performance Report** — per-strategy yield, trust adjustment
4. **Priority Handoff Report** — candidates ready + pending
5. **Markdown export** — any report to readable Markdown

## New Campaign Profile

**`validation_operations`** — optimizes for validation efficiency + calibration learning:
- 40% exploit, 30% explore, 30% diversify
- Weights: stability 0.30, value 0.25, diversity 0.25

## Tests

- **Phase IX:** 16/16 pass
- **Phase VIII:** 20/20 pass
- **Phase VII:** 16/16 pass
- **V.B/V.C:** 20/20 pass
- **Existing:** 19/19 pass
- **Total:** 91/91 (zero regressions)

## Honest Limitations

1. Evidence store starts empty — needs real validation to become useful
2. Batch workflows are infrastructure, not automated DFT
3. Reporting is only as good as the evidence accumulated
4. Family-level tracking assumes element sets are meaningful groupings
5. No real DFT backend yet — placeholder only

*All candidates remain theoretical until real validation evidence is ingested.*
