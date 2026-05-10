# Trinity — Task Board

Single coordination file for the human + AI loop on Trinity work.
Branch: `trinity/option-b-v0` (in both `sost-core` and `materials-engine-private`).

---

## Mission this week

Ship a working v0 of the Trinity bridge: produce one real dossier on the Kalgoorlie AOI, with a SHA-256, ready to be registered on chain as a SOST capsule. Reuse the existing `multi_ai_review` AI Council; do not duplicate it.

## Definition of done for v0

- [x] Inventory existing `multi_ai_review` infrastructure with file:line refs.
- [x] Critique the two competing views (View 1 = bridge-only; View 2 = orchestrator) against the actual code.
- [x] Decide architecture (hybrid, minimal — see `TRINITY_OPTION_B_REVIEW.md` §1.c).
- [x] Create branch `trinity/option-b-v0` in both repos.
- [x] Implement `materials-engine-private/src/trinity/geo_target_council.py`.
- [x] Implement `sost-core/scripts/trinity/aoi_to_dossier.py`.
- [x] Tests for both modules. `pytest -v`. No network in tests.
- [x] Run the entrypoint against the real Kalgoorlie scorecard, capture dossier + SHA-256.
- [x] Local commits in both branches. No push (operator reviews first).

## Sprint 2 — partial completion

- [x] **Useful Compute Planner integration (Trinity's fourth pillar).** New bridge
      `materials-engine-private/src/trinity/useful_compute_planner.py` plus
      entrypoint `sost-core/scripts/trinity/useful_compute_plan.py`. Reads
      a Trinity dossier and emits candidate Heavy Task families with
      reward-worthiness classification (`candidate_reward_worthy` /
      `not_reward_worthy` / `deferred`), a simulated worker queue, and a
      SHA-256 hash. **DRY-RUN ONLY** — never activates rewards, never
      publishes tasks, never enqueues. See
      `TRINITY_USEFUL_COMPUTE_EXTENSION.md` for the architectural rationale.
      Branch: `trinity/useful-compute-planner-v0`.
- [ ] Replace hardcoded deposit-type → materials map with live call to Materials Engine API (port 8100).
- [ ] Persist dossiers into `canonical_memory.HypothesisRecord` for cross-session memory.
- [ ] Add `--register` flag that auto-builds and broadcasts a `DOC_REF_OPEN` capsule pointing at the dossier hash.
- [ ] Add an Ollama-only run mode for richer rationales without paid API.
- [ ] Generate a second demo dossier on Pilbara or Zambia once their scorecards exist with real features.

## Conventions

- Author for commits: `NeoB <noreply@sostprotocol.org>`. No personal email.
- No mentions of any AI brand name in source files or commit messages.
- Each module under 600 LOC; if larger, split.
- Tests for every new public function. No network in tests.
- Commit messages explain WHY, not just WHAT.
- Single coordination file = this one. Do not create parallel task boards.

## Last session log

**2026-05-10** — initial v0 implementation. Wrote review doc + task board. Created `geo_target_council.py` (bridge) and `aoi_to_dossier.py` (entrypoint). Generated demo dossier on Kalgoorlie using the existing scorecard at `geaspirit-research/GeaSpirit_outputs/phase60/scorecard_kalgoorlie.json`. Tests pass with no network. Local commit on `trinity/option-b-v0` in both repos; not pushed.

**2026-05-10 (continued)** — env-var portability patch on `trinity/option-b-v0`: `aoi_to_dossier.py` now honours `TRINITY_GEASPIRIT_OUTPUTS_PATH` and `TRINITY_MATERIALS_ENGINE_PATH`. 6 new tests. SHA-256 of the Kalgoorlie demo unchanged. Pushed both branches.

**2026-05-10 (continued)** — Sprint 2 partial: Trinity Useful Compute Planner shipped on a new branch `trinity/useful-compute-planner-v0` cut from `option-b-v0`. New bridge `materials-engine-private/src/trinity/useful_compute_planner.py` + entrypoint `sost-core/scripts/trinity/useful_compute_plan.py`. Generates candidate Heavy Task families from dossier reviews, classifies them as `candidate_reward_worthy` / `not_reward_worthy` / `deferred`, simulates a queue, computes SHA-256. **DRY-RUN ONLY** — no rewards activated. Demo run on the Kalgoorlie dossier yields 3 candidate families (aoi_tile_scoring, spectral_template_scoring, geology_aware_negative_resampling), all candidate_reward_worthy, wallclock ~300 s on 8 workers. Total test count across both repos: 73 (44 materials-engine-private + 29 sost-core). See `TRINITY_USEFUL_COMPUTE_EXTENSION.md`.

## Next session entry point

If continuing on Trinity:
1. Read `TRINITY_OPTION_B_REVIEW.md` for the architecture rationale.
2. Read this file's "Definition of done" and "Sprint 2" lists.
3. Pick the smallest Sprint 2 item that produces a tangible artefact.
4. Update this file's "Last session log" before exiting.
