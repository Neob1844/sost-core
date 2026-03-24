# Materials Engine — Phase XI Outcome Report

**Date:** 2026-03-24
**Phase:** XI — Calibration Intelligence + Evidence-Driven Discovery

---

## Executive Summary

Phase XI wires accumulated validation evidence directly into the scoring engine. The engine now uses family trust, strategy trust, and noise suppression to make evidence-driven decisions about which candidates to promote and which to suppress.

---

## New Component

**`calibration_intelligence.py`** in `src/validation_bridge/`:

| Function | Input | Output |
|----------|-------|--------|
| `compute_family_trust()` | elements, evidence, calibration | trust_score, reliability, MAE, overconfidence |
| `compute_strategy_trust()` | method, evidence, calibration | trust_score, yield, reliability |
| `compute_scoring_adjustments()` | family_trust, strategy_trust | bonuses, penalties, noise suppression, label |

## How Evidence Changes Scoring

| Evidence Signal | Effect on Score | Range |
|----------------|-----------------|-------|
| Historically reliable family | +0.08 bonus | Strong trust (>0.3) |
| Historically unreliable family | -0.10 penalty | Weak trust (<-0.3) |
| High-yield strategy | +0.05 bonus | Yield > 60% |
| Low-yield strategy | -0.06 penalty | Yield < 40% |
| Both weak (family + strategy) | -0.15 noise suppression | Double-weak pattern |

## Evidence Quality Labels

| Label | Meaning |
|-------|---------|
| `evidence_supported` | Both family and strategy have positive trust |
| `evidence_neutral` | No historical evidence to adjust |
| `evidence_mixed` | Some signals positive, some negative |
| `evidence_warns` | Historical evidence suggests caution |
| `no_evidence` | No calibration data available |

## New Campaign Profile

**`evidence_guided_discovery`** — prioritizes candidates in historically reliable families:
- 50% exploit, 30% explore, 20% diversify
- Stability 0.30, value 0.25, diversity 0.20
- `use_evidence_calibration: true`

## Scorer Integration

`score_candidate()` now accepts optional `evidence_adjustments` parameter. When provided, applies family trust bonus, strategy trust bonus, and noise suppression to the composite score. All adjustments are recorded in the output dict for full traceability.

## Tests

- **Phase XI:** 17/17 pass
- **All previous:** 91/91 pass
- **Total:** 108/108 (zero regressions)

## Honest Limitations

1. Evidence is only as good as what's been imported/accumulated
2. Family trust is element-level — doesn't distinguish polymorphs
3. Strategy trust is statistical — small sample sizes can mislead
4. Noise suppression is heuristic, not physical
5. Evidence-guided discovery is still computational, not experimental

*Evidence improves prioritization. It does not replace validation.*
