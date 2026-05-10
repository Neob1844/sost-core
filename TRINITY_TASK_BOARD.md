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
- [x] **Dossier reproducibility hotfix.** `source.scorecard_path`
      replaced with `source.scorecard_sha256` +
      `source.scorecard_basename`. WSL ↔ VPS now produce
      byte-identical dossier JSON. Branch
      `trinity/dossier-reproducibility-hotfix`, merged forward
      into both downstream branches.
- [ ] Replace hardcoded deposit-type → materials map with live call to Materials Engine API (port 8100).
- [ ] Persist dossiers into `canonical_memory.HypothesisRecord` for cross-session memory.
- [ ] Add `--register` flag that *prepares* (but does not broadcast) a `DOC_REF_OPEN` capsule body for the proof bundle.
- [ ] Add an Ollama-only run mode for richer rationales without paid API.
- [ ] Generate a second demo dossier on Pilbara or Zambia once their scorecards exist with real features.

## Sprint 3 — Campaign Engine v0

- [x] **Autonomous Campaign Engine v0.** Branch
      `trinity/campaign-engine-v0` cut from
      `trinity/useful-compute-planner-v0`. Engine in
      `materials-engine-private/src/trinity/campaign_engine.py`,
      entrypoint `sost-core/scripts/trinity/trinity_campaign.py`,
      design doc `TRINITY_CAMPAIGN_ENGINE.md`. Demo
      `TRINITY_CAMPAIGN_kalgoorlie_phase1.{md,json}` with proof
      bundle anchoring four SHAs:

          scorecard:  836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246
          dossier:    d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf
          UC plan:    1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49
          campaign:   7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df

      `ready_to_register=True`, `registered=False`, `dry_run=True`
      at every level. Six action buckets enforced; five
      always-present `unsafe_or_forbidden` anchor entries. Total
      tests: 109 (67 materials-engine + 42 sost-core).

## Sprint 4 — Proof Bundle v0

- [x] **Trinity Proof Bundle v0.** Branch
      `trinity/proof-bundle-v0` cut from
      `trinity/campaign-engine-v0`. Builder
      `scripts/trinity/trinity_proof_bundle.py`, verifier
      `scripts/trinity/verify_trinity_bundle.py`, design doc
      `TRINITY_PROOF_BUNDLE.md`. Demo
      `TRINITY_PROOF_BUNDLE_kalgoorlie_phase1.{md,json}` ties
      the four base SHAs into a single root artefact:

          scorecard:        836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246
          dossier:          d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf
          plan:             1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49
          campaign:         7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df
          merkle_root:      a818a1e4799ec34fd5a65b17d180a9534f791d4cd49f54c97b21c11d7b0e28b4
          proof_bundle_sha: 3a28a4b112fe95df85ab2ab91deb7698ebeb1d9182297f06635fd12fd4053a02

      Verifier runs 12 closed checks (schema, anchor shapes,
      Merkle root, four safety flags, host-path leak, capsule
      execution status, local file re-hashes). Tests: 20 new
      (proof bundle + verifier), 62 total in this repo, 67 in
      materials-engine-private. Cross-repo total: 129.

## Sprint 5 — proposed, not implemented

- [ ] `--register` flag on the proof-bundle builder that
      *prepares* (but does not execute) the exact `sost-cli send`
      command for OPEN_NOTE_INLINE or DOC_REF_OPEN.
- [ ] Multi-bundle index: meta-bundle anchoring N proof bundles
      via the same Merkle algorithm at the next layer up.
- [ ] Optional ECDSA signature over `proof_bundle_sha256` using
      the operator's mining key.
- [ ] Live Materials Engine API integration for deposit-type
      context (replaces the hardcoded map in `geo_target_council`).
- [ ] `canonical_memory` persistence of campaign manifests so
      multiple Trinity sessions share state.
- [ ] Pilbara or Zambia campaign once feature processing lands.
- [ ] Ollama-only Council run mode.

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

**2026-05-10 (continued)** — Dossier reproducibility hotfix. `source.scorecard_path` (absolute filesystem path) replaced with `source.scorecard_sha256` + `source.scorecard_basename`. WSL ↔ VPS now produce byte-identical dossier JSON for the same scorecard content. Branch `trinity/dossier-reproducibility-hotfix` merged forward into `trinity/useful-compute-planner-v0`. Cross-machine verification of three SHAs: scorecard `836b677c...`, dossier `d0bbc47e...`, Useful Compute Plan `1e7ab30a...` — identical between machines.

**2026-05-10 (continued)** — Sprint 3: Autonomous Campaign Engine v0 shipped on branch `trinity/campaign-engine-v0` cut from `useful-compute-planner-v0`. New engine `materials-engine-private/src/trinity/campaign_engine.py` (~640 LOC) + entrypoint `sost-core/scripts/trinity/trinity_campaign.py` (~280 LOC) + design doc `TRINITY_CAMPAIGN_ENGINE.md`. Reads a dossier and a Useful Compute Plan, emits a Campaign Manifest with proof bundle (four anchor SHAs), 11-item closed evidence-gap taxonomy, 6-bucket action classification, and the always-present `unsafe_or_forbidden` anchor list (activate rewards / publish reward tasks / register on chain / move funds / modify consensus — all routed to forbidden via substring veto). Demo `TRINITY_CAMPAIGN_kalgoorlie_phase1.{md,json}` with campaign SHA-256 `7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df`. All anchors `ready_to_register=True`, `registered=False`, `dry_run=True`. Total test count across both repos: 109 (67 materials-engine + 42 sost-core).

## Next session entry point

If continuing on Trinity:
1. Read `TRINITY_OPTION_B_REVIEW.md` for the architecture rationale.
2. Read this file's "Definition of done" and "Sprint 2" lists.
3. Pick the smallest Sprint 2 item that produces a tangible artefact.
4. Update this file's "Last session log" before exiting.
