# Trinity — Option B Review (v0)

Branch: `trinity/option-b-v0` (in both `sost-core` and `materials-engine-private`).
Date: 2026-05-10.
Scope: review the existing multiagent infrastructure, decide what Trinity needs that does not already exist, and ship a working v0 demo on the Kalgoorlie AOI.

---

## 1.a. Inventory of existing multiagent infrastructure

`/home/sost/SOST/materials-engine-private/src/multi_ai_review/` contains **213 modules** at the time of writing. The pieces relevant to a Trinity bridge are already implemented:

| Concern | Module / class | File:line |
|---|---|---|
| Council coordinator | `AICouncil.review(hypothesis, *, budget, allow_network, allow_paid)` | `src/multi_ai_review/ai_council.py:40` |
| Aggregated decision | `CouncilDecision` (accept / reject / hold / contradicted) | `src/multi_ai_review/ai_council.py:18` |
| Council members (free, always-on) | `ValidatorMember`, `LocalKnowledgeMember`, `MockAIMember` | `src/multi_ai_review/council/{validator_member,local_knowledge_member,mock_ai_member}.py` |
| Council members (network/paid, opt-in) | `OllamaMember`, `OpenRouterMember`, `HuggingFaceMember`, `PaidJudgeInterface` | same dir |
| Member base class | `CouncilMember` and `CouncilOpinion` | `src/multi_ai_review/council/base.py:10,25` |
| Hypothesis schema | `Hypothesis`, `HypothesisScore` | `src/multi_ai_review/hypothesis_schema.py:75,59` |
| Hypothesis types incl. `mineral_target`, `aoi_priority`, `commodity_transfer`, `uncertainty_target` | `HYPOTHESIS_TYPES` | `src/multi_ai_review/hypothesis_schema.py:15` |
| Per-project hypothesis generators | `generate_geaspirit_hypotheses(...)`, `generate_materials_hypotheses(...)`, `generate_sost_hypotheses(...)` | `src/multi_ai_review/hypotheses/*.py` |
| Hypothesis dispatcher | `HypothesisFactory.generate(project, ...)` | `src/multi_ai_review/hypothesis_factory.py:14` |
| Validation dossier schema | `ValidationDossier` (current_evidence / missing_evidence / validation_plan / pass_fail_criteria / publishability) | `src/multi_ai_review/validation_dossier.py` |
| Budget gating (4 modes: `tiny / normal / deep / paid_judge`) | `ProviderBudget`, `BudgetSnapshot` | `src/multi_ai_review/provider_budget.py` |
| Localhost-only ops dashboard (existing, port 8766) | `ai_ops_dashboard_server.run(...)` + `console_security.LOCALHOST_HOSTS` | `src/multi_ai_review/ai_ops_dashboard_server.py` |
| Token gating for the dashboard | `ai_ops_token` | `src/multi_ai_review/ai_ops_token.py` |
| Free-resources policy (arxiv, OpenAlex, Crossref, PubChem, Materials Project gated, JARVIS local) | written + enforced | `docs/multi_ai_free_resources_policy.md` |
| AI Council policy (validator-veto, evidence-required-for-accept, hold-by-default) | written + enforced | `docs/multi_ai_ai_council_policy.md` |

The Council policy specifies (paraphrased from `docs/multi_ai_ai_council_policy.md`):

> **Validator veto.** If the M2 ValidatorMember returns `contradicted`, the council outputs `contradicted` regardless of what other members say.
> **Strong rejection.** Any other member returning `contradicted` leads to `reject` unless validator agrees strongly.
> **Promotion needs evidence.** A hypothesis is `accept`ed only if ≥2 members agree and no member disagrees.
> **Hold by default.** When opinions are weak or contradictory, the decision is `hold` — never `accept` by inertia.

Capsule registration is supported by SOST Core itself: `include/sost/capsule.h:34-39` defines `CapsuleType::OPEN_NOTE_INLINE = 0x01` and `CapsuleType::DOC_REF_OPEN = 0x03`, which are the two natural carriers for a dossier hash + label or a dossier hash + URL.

## 1.b. Honest critique of the two competing views

**View 1** (bridge-only): "the existing `multi_ai_review` package already is the multiagent layer; the missing Trinity piece is a single bridge that takes Geaspirit ranked targets, queries Materials Engine, packages them as `Hypothesis`, runs `AICouncil.review`, writes a dossier with SHA-256."

This view is **largely correct against the actual code**. Every component the bridge needs already exists at the file:line refs above. View 1 underestimated the *richness* of the existing layer (it pegged the missing piece at ~500 LOC; the real number is closer to 250 LOC for the bridge plus 200 LOC for the entrypoint plus tests). View 1 also did not enumerate `validation_dossier.py` as the natural output schema, which it is.

**View 2** (parallel orchestrator): "build a small Trinity Multiagent Core: a top-level mission file, a single task board, a parallel orchestrator script that fans out to multiple language models, JSON task/response format, optional paid-LLM API-key connection."

This view is **partially redundant against the actual code**. Specifically:
- Canonical objectives already exist as `src/multi_ai_review/canonical_objectives.py`, with a roadmap in `canonical_roadmap.py`. Creating a parallel top-level mission file would duplicate them in a different format and create a drift risk.
- A task board is fine because the existing layer's `self_task_*` modules and `console_chat_history.py` are private/internal; a single shared markdown task board is the right amount of coordination for the human + AI loop. **One** file. The single-file instinct is right; the four-file proposal would have been gold-plating.
- A new parallel orchestrator is **fully redundant** — `AICouncil.review(...)` already coordinates 7 typed members with budget gating. Building a parallel orchestrator would create two systems of record for "what did the council say about this hypothesis", and that drift is poison.
- Optional paid-LLM API-key connection — already covered by the existing budget mode `paid_judge` and the `PaidJudgeInterface` member. v0 does not enable it.

**Conclusion**: View 1 is the right starting frame; View 2's task-board instinct is good in single-file form but its orchestrator is duplication.

## 1.c. Recommended architecture (hybrid, minimal)

```
Geaspirit  scorecard / ranked targets
                |
                v
        geo_target_council.py             [NEW, materials-engine-private]
                |
                |  builds Hypothesis(project="geaspirit", type="mineral_target", ...)
                |  attaches Materials Engine deposit-type context (hardcoded mapping in v0)
                v
        AICouncil.review(...)             [REUSED, no fork]
                |
                v
        CouncilDecision  +  ValidationDossier        [REUSED schema]
                |
                v
        aoi_to_dossier.py                 [NEW, sost-core/scripts/trinity]
                |
                |  serialises canonical JSON, renders Markdown,
                |  computes SHA-256, prints capsule-ready references
                v
        TRINITY_DEMO_DOSSIER_<AOI>.md  +  .json  +  printed sha256
                |
                v
        (manual, out of v0) `sost-cli send --capsule-mode doc-ref-open ...`
```

Files created:

| New file | Reason it cannot reuse something existing |
|---|---|
| `materials-engine-private/src/trinity/__init__.py` | New sub-package namespace; cannot live inside `multi_ai_review/` because it is not "a council member" but the project-level integration glue. |
| `materials-engine-private/src/trinity/geo_target_council.py` | The bridge between Geaspirit scorecards and `Hypothesis` + `AICouncil`. The existing `generate_geaspirit_hypotheses` is generic (scans local docs heuristically); the bridge needs to consume a real scorecard and emit per-target hypotheses, which no existing module does. |
| `materials-engine-private/tests/test_geo_target_council.py` | Tests for the new module. Mirrors the layout of `tests/test_multi_ai_*`. |
| `sost-core/scripts/trinity/aoi_to_dossier.py` | The CLI entrypoint that produces the dossier. Uses the bridge plus `ValidationDossier`. Lives in `sost-core` so it is reachable from the same shell that runs `sost-cli` for the eventual capsule registration step. |
| `sost-core/tests/trinity/test_aoi_to_dossier.py` | Tests for the entrypoint. |
| `sost-core/TRINITY_TASK_BOARD.md` | Single coordination file for the human + AI loop. |
| `sost-core/TRINITY_OPTION_B_REVIEW.md` | This document. |
| `sost-core/TRINITY_DEMO_DOSSIER_kalgoorlie.md` | The demo dossier output, committed for review. |

Files **not** created (deliberately):
- No new dashboard, console, or chat UI.
- No new `AICouncil` class. `MockAIMember`, `ValidatorMember`, `LocalKnowledgeMember` are reused as-is.
- No `trinity_orchestrator.py`. The orchestration IS `AICouncil.review`.
- No `TRINITY_CANON.md`. `canonical_objectives.py` already encodes the canonical objectives at module scope.
- No marketing copy, pricing tiers, roadmap docs.

## 1.d. Seven canonical objectives — operational restatement

| Objective | How v0 satisfies it |
|---|---|
| **Autonomy** | A single command `python3 scripts/trinity/aoi_to_dossier.py kalgoorlie` produces a complete dossier with no human intervention beyond invocation. |
| **Utility** | The dossier output is byte-identical between runs given the same inputs (deterministic), and can be registered on chain immediately as a `DOC_REF_OPEN` capsule pointing at the file SHA-256. |
| **Memory** | Dossier and SHA-256 are written to disk; the existing `canonical_memory.HypothesisRecord` is left as the upgrade path for Sprint 2 to persist into the project's central memory. |
| **Cross-critique** | `AICouncil.review` already evaluates each hypothesis with three independent free members (validator, local-knowledge, mock-AI). A `contradicted` from the validator vetoes the hypothesis. |
| **Economics** | The output is the unit of sale (one dossier = one priced artefact). v0 deliberately does not implement billing — only the artefact. |
| **Security** | No keys handled. No network in tests. No paid model invoked. The bridge runs entirely with `allow_network=False, allow_paid=False`. The dossier never embeds a private key, only a SHA-256 of public content and the AOI name. |
| **Anti-vapour** | Every claim in the dossier carries a council attribution and a verdict. The `honesty_matrix` from the source scorecard (e.g. Kalgoorlie Tier 1 — Remote proxy evidence only) is propagated verbatim into the dossier so users see the data limitations alongside the verdict. |

## 1.e. Risk register

| Risk | Code-level mitigation |
|---|---|
| API cost ceiling exceeded | v0 pinned to `members=[ValidatorMember(), LocalKnowledgeMember(), MockAIMember()]`; no paid or network calls possible. Sprint 2 enabling Ollama would still respect `ProviderBudget(mode='tiny')`. |
| Divergence between AIs | Single source of truth = `AICouncil.CouncilDecision`. Bridge does not implement its own scoring or its own decision engine. |
| Key safety | No key access in the bridge or entrypoint. SOST capsule registration is left as a manual `sost-cli send` step the operator runs after reviewing the dossier. |
| Over-engineering | The two new files are ~250 + ~200 LOC. No factory of factories. No abstract Member layer. The mapping from deposit type to typical materials is a Python dict in v0, not a service. |
| No-monetisation drift | The unit produced (one dossier) is the unit a buyer would pay for. There is no roadmap document describing future hypothetical features in the v0 scope. |
| Fallback when scorecard is degenerate (Kalgoorlie has features_available=0) | The bridge detects this and emits a single `aoi_priority` hypothesis with the honesty-matrix caveats embedded; the council reviews on context only. The dossier explicitly labels this as `fallback_mode`. |

---

## Recommendation

Build the v0 exactly as in section 1.c. Do not build anything else from View 2 beyond what is in 1.c. After v0 ships and a real dossier exists with a SHA-256, the natural Sprint 2 candidates are:

1. Replace the hardcoded deposit-type → materials mapping with a live call to the Materials Engine API on port 8100 (`/explain-formula`, `/similar`, `/candidates/exotic/rank`).
2. Wire the dossier into the existing `canonical_memory.HypothesisRecord` so Trinity has cross-session memory.
3. Optional: add an Ollama-only run mode for richer rationales without paid API.
4. Optional: a small wrapper that registers the dossier hash automatically as a SOST capsule when `--register` is passed.

Sprint 2 is not implemented in this branch.
