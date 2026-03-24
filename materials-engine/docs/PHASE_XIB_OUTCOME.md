# Materials Engine — Phase XI.B Outcome Report

**Date:** 2026-03-24
**Phase:** XI.B — Autonomy Governance

---

## Executive Summary

Phase XI.B introduces the autonomy governor — a governance layer that controls what the engine can decide on its own. The engine can now auto-select campaigns, auto-promote/demote candidates, recommend seeds based on evidence, and identify when human review is actually needed.

---

## Autonomy Levels

| Level | Name | Auto-Campaign | Auto-Promote | Auto-Demote | Policy Adapt |
|-------|------|--------------|-------------|------------|-------------|
| 0 | Manual Only | No | No | No | No |
| 1 | Assisted | No | No | No | No |
| 2 | Supervised | Yes | No | Yes | No |
| 3 | Guided | Yes | Yes | Yes | Yes |
| 4 | High Autonomy | Yes | Yes | Yes | Yes |

## Key Capabilities

**Campaign Auto-Selection:** Scores all 13 profiles against current goals and evidence history. Returns best profile with reason and expected value.

**Auto-Seeding:** Recommends seed pairs based on family reliability (low overconfidence, low MAE → preferred). Penalizes families with poor validation history.

**Auto-Promotion:** Promotes candidates to priority_validation when: `is_novel_gnn AND score ≥ 0.55 AND confidence ≥ 0.55 AND readiness ≥ 0.55`. Fully traceable.

**Auto-Demotion:** Demotes when: `score < 0.35 AND confidence < 0.30` OR `evidence_warns AND score < 0.45`.

**Human Review Triggers:** Only requests human review for:
- High-value candidate with high uncertainty
- Near handoff threshold (readiness 0.55-0.65)
- High OOD risk with decent score

All decisions logged with event type, detail, level, and timestamp.

## Tests

- Phase XI.B: 22/22 pass
- All previous: 108/108 pass
- **Total: 130/130** (zero regressions)

## Honest Limitations

- Autonomy does NOT replace scientific validation
- Auto-promotion threshold is conservative by design
- Evidence-based decisions only as good as accumulated evidence
- Level 4 still requires human veto capability
- No experimental validation automation

*The governor reduces supervision overhead, not scientific rigor.*
