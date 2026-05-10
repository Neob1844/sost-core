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

## Sprint 2 — proposed, not implemented

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

## Next session entry point

If continuing on Trinity:
1. Read `TRINITY_OPTION_B_REVIEW.md` for the architecture rationale.
2. Read this file's "Definition of done" and "Sprint 2" lists.
3. Pick the smallest Sprint 2 item that produces a tangible artefact.
4. Update this file's "Last session log" before exiting.
