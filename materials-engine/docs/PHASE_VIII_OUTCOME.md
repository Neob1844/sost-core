# Materials Engine — Phase VIII Outcome Report

**Date:** 2026-03-24
**Phase:** VIII — Validation Bridge + DFT Orchestration Prep + Closed Learning Loop

---

## Executive Summary

Phase VIII creates the validation bridge — the infrastructure that closes the learning loop between candidate generation and validation evidence. The engine can now:

1. **Register candidates** for validation with unique IDs
2. **Track lifecycle** through 12 states (rejected → confirmed_partial)
3. **Generate handoff packs** for DFT review
4. **Ingest validation results** from JSON, CSV, or manual entry
5. **Reconcile** model predictions vs observations
6. **Classify outcomes** (model_supports, overconfident, underconfident, etc.)
7. **Calibrate** family-level and strategy-level trust from evidence
8. **Feed back** into scoring via uncertainty adjustments

---

## Architecture: `src/validation_bridge/`

| Module | Purpose |
|--------|---------|
| `lifecycle.py` | 12 lifecycle states, valid transitions, tier ordering |
| `registry.py` | Persistent candidate registry with IDs, state history, handoff packs |
| `result_ingest.py` | Import results from JSON, CSV, or manual entry |
| `reconciliation.py` | Compare predicted vs observed, classify outcome, generate learning signals |
| `calibration.py` | Family/strategy trust tracking, evidence-based uncertainty adjustment |
| `bridge.py` | Orchestrator: submit → handoff → ingest → reconcile → calibrate |
| `bridge.py::DryRunBackend` | Flow testing without real DFT |

## Candidate Lifecycle

```
rejected ─────────────────── (terminal)
watchlist → manual_review → validation_candidate
validation_candidate → priority_validation → DFT_handoff_ready
DFT_handoff_ready → handed_off → validation_pending
validation_pending → result_received
result_received → confirmed_partial | disagrees_with_model | inconclusive
```

## Reconciliation Classifications

| Classification | Meaning | Learning Signal |
|---------------|---------|-----------------|
| model_supports_candidate | Prediction within model MAE | Decrease uncertainty (-0.05) |
| model_partial_match | Within 2.5× MAE | Slight increase (+0.03) |
| model_overconfident | Large error + high confidence | Strong increase (+0.15), retrain |
| model_underconfident | Large error + low confidence | Expected — model was honest |
| no_comparison_data | No overlapping predictions | No adjustment |

## New Campaign Profile

**`validation_priority`** — maximizes candidates most likely to validate well:
- 60% exploit, 20% explore, 20% diversify
- Weights: stability 0.35, value 0.30, diversity 0.20
- Distinct from exotic_hunt or uncertainty_probe

## Tests

- **Phase VIII tests:** 20/20 pass
- **Phase VII tests:** 16/16 pass
- **V.B/V.C tests:** 20/20 pass
- **Existing tests:** 19/19 pass
- **Total:** 75/75 pass (zero regressions)

## Honest Limitations

1. **No real DFT executed** — only dry-run backend tested
2. **Calibration from zero observations** — needs real evidence to be meaningful
3. **Reconciliation thresholds are heuristic** — FE_GOOD=0.15eV, BG_GOOD=0.35eV
4. **Family trust is element-level** — doesn't distinguish polymorphs
5. **Learning loop tested but not yet exercised with real data**

## CTO Recommendation

Phase VIII completes the platform architecture. The engine now has a closed loop from generation through validation feedback. Next:

1. **Phase IX:** Connect first real DFT backend (Quantum ESPRESSO or VASP)
2. **Phase X:** Run validation on top 5 handoff-ready candidates
3. **Phase XI:** Web dashboard showing validation lifecycle + evidence

*All candidates remain theoretical until real DFT/experimental evidence is ingested.*
