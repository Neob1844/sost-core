# Trinity — Useful Compute extension (Sprint 2 partial)

Branch: `trinity/useful-compute-planner-v0` (in both `sost-core` and `materials-engine-private`).
Cut from: `trinity/option-b-v0`.
Date: 2026-05-10.

This document explains why Trinity gained a fourth pillar (Useful Compute Planner), what it does, what it deliberately does NOT do, and how to use it.

---

## 1. Why a fourth pillar

The original Trinity v0 connected three:

```
       GeaSpirit             Materials Engine               SOST
   (terrain evidence)    (materials hypotheses)     (proof, hash, register)
```

The bottleneck for everything Materials does heavy is **compute**. DFT runs, MLIP batch relaxations, AOI tile feature extraction, cross-worker descriptor validation — none of these are tractable on the operator's two laptops + one VPS. The protocol's own answer to that bottleneck already exists in scaffold form: **Useful Compute** — a distributed compute layer where operators of other machines accept tasks and (in a future activated phase) get paid in SOST.

Sprint 2 turns Trinity into a **planner** for that layer: given a Trinity dossier (the output of `aoi_to_dossier.py`), it generates the candidate Heavy Task families that would be useful, classifies them as reward-worthy or not, and simulates a queue. It is NOT a publisher, NOT a scheduler, NOT an activator of rewards.

```
       GeaSpirit             Materials Engine               SOST
            \                       |                        /
             \                      |                       /
              +-----> Trinity dossier (aoi_to_dossier.py)
                                    |
                                    v
                    Trinity Useful Compute Planner
                    (useful_compute_planner.py +
                     useful_compute_plan.py)
                                    |
                                    v
                   Plan: candidate families + reward status
                   + simulated queue + SHA-256
                                    |
                                    v
                    (manual, future) operator decision to
                    open Useful Compute paid queue — out
                    of this branch's scope, requires a
                    separate consensus + governance step.
```

## 2. Components

### `materials-engine-private/src/trinity/useful_compute_planner.py`

Bridge module. ~530 LOC. Public surface:

- `TaskFamilySpec` — catalogue entry describing a Heavy Task family (runtime, memory, dependencies, N-worker verification cardinality, project, description). Pure data.
- `CandidateHeavyTask` — what the planner emits per `(review × family)` pair. Carries the source hypothesis hash so dossiers and plans are linkable.
- `RewardWorthinessReport` — wrapper around the existing `multi_ai_review.heavy_task_classifier.TaskClassification` plus a Trinity-level `reward_status ∈ {candidate_reward_worthy, deferred, not_reward_worthy}` and a `why` explanation.
- `SimulatedQueueReport` — output of the greedy longest-processing-time-first queue simulator.
- `UsefulComputePlan` — the top-level dataclass aggregating the above plus the source AOI and a `safety_notice` string.
- `classify_reward_worthiness(task)` — runs the existing 5-axis classifier and routes to `candidate / deferred / not`.
- `simulate_useful_compute_queue(tasks, workers)` — pure arithmetic, no execution.
- `propose_heavy_task_families_from_reviews(reviews)` — walks the dossier's `reviews` array and emits `CandidateHeavyTask` instances based on hypothesis type → family mapping `_TYPE_TO_FAMILIES`.
- `plan_from_dossier(dossier, workers=8)` — top-level convenience.

Catalogue families shipped in v0 (all `dry_run=True`):

| Family id | Project | Description summary |
|---|---|---|
| `mlip_relaxation` | materials | Deterministic MLIP relaxation pre-DFT |
| `dft_input_preparation` | materials | DFT input bundle sanity, no execution |
| `spectral_template_scoring` | geaspirit | Per-tile mineral template scoring |
| `aoi_tile_scoring` | geaspirit | Per-tile feature scoring across AOI |
| `cross_worker_descriptor_validation` | materials | N≥2 cross-check of derived descriptors |
| `geology_aware_negative_resampling` | geaspirit | Negative training samples for ranking models |
| `quantum_chemistry_toy_benchmark` | materials | **Held DEFERRED in v0** (verification path open) |
| `trivial_busy_wait_REJECTED` | materials | Anti-pattern; only the test suite uses it; the proposer never emits it |

### `sost-core/scripts/trinity/useful_compute_plan.py`

CLI entrypoint. ~250 LOC. Honours `TRINITY_MATERIALS_ENGINE_PATH` to locate the planner without depending on a WSL layout. Reads a Trinity dossier JSON, runs `plan_from_dossier`, renders Markdown + canonical JSON, computes SHA-256 over the canonical bytes, prints both paths and the hash.

CLI surface:

```
python3 scripts/trinity/useful_compute_plan.py <dossier.json>
        [--workers N] [--out-md path] [--out-json path] [--pinned-time iso]
```

The Markdown output always includes:
1. A DRY-RUN ONLY warning at the top.
2. Reward-worthiness summary table.
3. One section per candidate family with description, reward status, classifier axes, and the reasoning.
4. The simulated queue (workers, wallclock, per-worker seconds).
5. The safety notice (verbatim).
6. SHA-256 of the canonical JSON.
7. A "What this document is NOT" block enumerating what the document does not claim.

### Tests

- `materials-engine-private/tests/test_useful_compute_planner.py` — 24 tests covering catalogue completeness, the three classifier branches (`candidate / deferred / not`), proposer (per hypothesis type, dedup, anti-pattern non-emission), queue simulator (empty / single / multi / invalid args), full plan dry-run propagation, safety-notice presence, empty dossier handling, and an explicit "no public function activates rewards" assertion that scans the module's public surface.
- `sost-core/tests/trinity/test_useful_compute_plan.py` — 10 tests covering canonical JSON serialisation, the entrypoint runs deterministically (pinned-time → byte-identical output), nonexistent / invalid dossiers return error codes, and the rendered Markdown carries the DRY-RUN warning and the "What this document is NOT" disclaim block.

All 73 tests across both repos pass with no network access.

## 3. What this branch deliberately does NOT do

The instruction from the operator was explicit:

> **Trinity can design, simulate, and evaluate Heavy Tasks. Trinity CANNOT activate real rewards or publish reward-bearing tasks.**

Concretely:

- No code path in this branch enables Useful Compute rewards. The existing `project_registry.json` keeps `can_publish_useful_compute_task: false` and `can_enable_useful_compute_rewards: false` for every project; the planner respects that.
- No HTTP client. No new endpoint exposed. The public Useful Compute API is unchanged.
- No new systemd service.
- No worker change. `scripts/useful_compute_worker.py` was read as reference only.
- No SOST RPC call. No wallet handling.
- No new dashboard / console / chat UI.
- No new `AICouncil` class.
- The classifier reused is the existing `multi_ai_review.heavy_task_classifier`, not a parallel one.

The `reward_status` field is a **classification**, not a switch. There is no `activate_rewards(task)` function, no `publish_task(task)` function, no `enqueue_task(task)` function, and the test suite asserts that the public surface of the planner does not contain any name that smells like one.

## 4. Recommended use today

```bash
# 1. Generate (or have) a Trinity dossier.
python3 scripts/trinity/aoi_to_dossier.py kalgoorlie

# 2. Run the planner against it.
python3 scripts/trinity/useful_compute_plan.py \
        TRINITY_DEMO_DOSSIER_kalgoorlie.json --workers 8

# Output goes to TRINITY_USEFUL_COMPUTE_PLAN_kalgoorlie.{md,json}
# with a SHA-256 the operator can optionally register on chain.
```

On the VPS where the materials-engine-private repo lives at a non-WSL path:

```bash
export TRINITY_MATERIALS_ENGINE_PATH=/opt/materials-engine-trinity-option-b-v0
python3 scripts/trinity/useful_compute_plan.py \
        TRINITY_DEMO_DOSSIER_kalgoorlie.json --workers 8
```

## 5. Demo output on the Kalgoorlie dossier

On the WSL host where Kalgoorlie's scorecard is `features_available=0` and the dossier consequently runs in `fallback_mode`:

- 3 candidate Heavy Task families emitted: `aoi_tile_scoring`, `spectral_template_scoring`, `geology_aware_negative_resampling`.
- All three classified as `candidate_reward_worthy` by the 5-axis classifier.
- Simulated wallclock with 8 workers: ~300 s (limited by the longest single family).
- The plan carries `dry_run=True` on every level and renders the "What this document is NOT" block at the bottom.

## 6. Next Sprint candidates (Sprint 3 — not implemented)

- Replace the in-module `_TYPE_TO_FAMILIES` mapping with a per-AOI heuristic that asks Materials Engine (`/explain-formula`, `/similar`) for the typical materials of each deposit type. This would make the planner adapt to the actual AOI rather than emitting a generic family list.
- Per-family runtime / memory calibration from real worker telemetry (when the activated phase opens, if ever).
- Promote `quantum_chemistry_toy_benchmark` from `deferred` to `candidate_reward_worthy` once the BLAS-vendor + SCF-tolerance verification protocol is designed.
- Optionally cross-link to `canonical_memory.HypothesisRecord` so each plan entry is recorded against its source hypothesis in the same persistent store the wider `multi_ai_review` layer already uses.

Sprint 3 is **not** implemented in this branch.
