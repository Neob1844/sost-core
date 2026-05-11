# Trinity / Materials Track — Dossier `oxide_frontier_v02`

> **AUTONOMOUS CANDIDATE PROPOSAL.** The hypotheses in this dossier are **autonomous candidate proposal** entries produced by Trinity / Materials Discovery from a pinned seed and a closed chemistry filter. They are **not experimentally validated**, **not DFT validated**, **not a patent claim**, and **not a commercial performance claim**. Each candidate **requires Useful Compute / DFT / synthesis review** before any further claim can be made.

> **REAL SOST AI COUNCIL.** Reviews below come from the canonical multi_ai_review AICouncil (free-tier members only: validator + local_knowledge + mock_ai). No network, no paid model calls, deterministic. Same engine used by Earth Track.

- **Schema**: `trinity-materials-dossier/v0.2`
- **Track**: `materials`
- **Generated (UTC)**: 2026-05-10T00:00:00+00:00
- **Source**:
  - `council_implementation`: `real_sost_ai_free_tier`
  - `features_available`: `0`
  - `mode`: `autonomous_v0.1`
  - `scorecard_basename`: `TRINITY_MATERIALS_SCORECARD_oxide_frontier_v02.json`
  - `scorecard_schema`: `trinity-materials-scorecard/v0.1`
  - `scorecard_sha256`: `389dafeffa71b9bb031d6672ed73904cf2fd981716755d7785d5e03ac228a7f6`
  - `used_real_council`: `True`

## Summary

- **candidates_total**: `8`
- **decisions_accept**: `0`
- **decisions_hold**: `7`
- **decisions_reject**: `1`
- **decisions_abstain**: `0`
- **validator_vetoes_applied**: `0`

## Hypotheses

### `MX-0016` &mdash; SrTiO3 (perovskite) &mdash; **HOLD**

- seed_novelty=`0.94`, seed_frontier_proximity=`0.95`, veto_applied=`False`, council_confidence=`0.4`
- council_next_step: no strong opinions; revisit later
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|perovskite|SrTiO3|MX-0016' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **abstain** &mdash; mock: insufficient signal for a strong call (verdict=abstain, confidence=0.4)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no phonon screening at the operating temperature
  - no proton conductivity reference (if relevant)

### `MX-0001` &mdash; NiAl2O4 (spinel) &mdash; **HOLD**

- seed_novelty=`0.92`, seed_frontier_proximity=`0.94`, veto_applied=`False`, council_confidence=`0.4`
- council_next_step: no strong opinions; revisit later
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|spinel|NiAl2O4|MX-0001' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **hold** &mdash; mock: no opinion without evidence (verdict=insufficient, confidence=0.2)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no MLIP relaxation baseline
  - no measured magnetic ordering reference

### `MX-0021` &mdash; CaZrO3 (perovskite) &mdash; **HOLD**

- seed_novelty=`0.91`, seed_frontier_proximity=`0.95`, veto_applied=`False`, council_confidence=`0.6`
- council_next_step: needs more evidence before promotion
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|perovskite|CaZrO3|MX-0021' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **accept** &mdash; mock: family heuristics align with claim (verdict=agree, confidence=0.6)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no phonon screening at the operating temperature
  - no proton conductivity reference (if relevant)

### `MX-0009` &mdash; ZnCr2O4 (spinel) &mdash; **HOLD**

- seed_novelty=`0.90`, seed_frontier_proximity=`0.92`, veto_applied=`False`, council_confidence=`0.6`
- council_next_step: needs more evidence before promotion
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|spinel|ZnCr2O4|MX-0009' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **accept** &mdash; mock: family heuristics align with claim (verdict=agree, confidence=0.6)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no MLIP relaxation baseline
  - no measured magnetic ordering reference

### `MX-0005` &mdash; CuCr2O4 (spinel) &mdash; **HOLD**

- seed_novelty=`0.90`, seed_frontier_proximity=`0.92`, veto_applied=`False`, council_confidence=`0.4`
- council_next_step: no strong opinions; revisit later
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|spinel|CuCr2O4|MX-0005' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **hold** &mdash; mock: no opinion without evidence (verdict=insufficient, confidence=0.2)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no MLIP relaxation baseline
  - no measured magnetic ordering reference

### `MX-0008` &mdash; MnAl2O4 (spinel) &mdash; **REJECT**

- seed_novelty=`0.89`, seed_frontier_proximity=`0.94`, veto_applied=`False`, council_confidence=`0.55`
- council_next_step: rejected by majority; archive
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|spinel|MnAl2O4|MX-0008' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **reject** &mdash; mock: similar candidates have failed validation (verdict=disagree, confidence=0.55)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no MLIP relaxation baseline
  - no measured magnetic ordering reference

### `MX-0013` &mdash; FeGa2O4 (spinel) &mdash; **HOLD**

- seed_novelty=`0.87`, seed_frontier_proximity=`0.92`, veto_applied=`False`, council_confidence=`0.4`
- council_next_step: no strong opinions; revisit later
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|spinel|FeGa2O4|MX-0013' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **abstain** &mdash; mock: insufficient signal for a strong call (verdict=abstain, confidence=0.4)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no MLIP relaxation baseline
  - no measured magnetic ordering reference

### `MX-0010` &mdash; NiFe2O4 (spinel) &mdash; **HOLD**

- seed_novelty=`0.85`, seed_frontier_proximity=`0.94`, veto_applied=`False`, council_confidence=`0.4`
- council_next_step: no strong opinions; revisit later
- **Reviews**:
  - `validator_member`: **hold** &mdash; validator verdict=insufficient_evidence (level=insufficient_evidence) (verdict=insufficient, confidence=0.0)
  - `local_knowledge`: **hold** &mdash; no local doc mentions 'materials|spinel|NiFe2O4|MX-0010' (verdict=insufficient, confidence=0.0)
  - `mock_ai`: **abstain** &mdash; mock: insufficient signal for a strong call (verdict=abstain, confidence=0.4)
- **Evidence gaps**:
  - no DFT formation energy on file
  - no MLIP relaxation baseline
  - no measured magnetic ordering reference

