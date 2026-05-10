# Trinity — Campaign Engine v0

Branch: `trinity/campaign-engine-v0` (in both `sost-core` and `materials-engine-private`).
Cut from: `trinity/useful-compute-planner-v0`.
Date: 2026-05-10.

This document explains why Trinity gained an **autonomous campaign layer**, how it composes the dossier and the Useful Compute Plan into a single reproducible proof bundle, and what the layer deliberately refuses to do.

---

## 1. Position in the Trinity stack

After Sprint 2 the stack looked like this:

```
       GeaSpirit             Materials Engine
            \                       /
             \                     /
              v                   v
       aoi_to_dossier.py     (review · validator-veto · hold-by-default)
              |
              v
       Trinity dossier  (sha256 d0bbc47e...)
              |
              v
       useful_compute_plan.py
              |
              v
       Useful Compute Plan  (sha256 1e7ab30a...)
```

Two artefacts. Two SHAs. Both reproducible cross-machine after the dossier-reproducibility hotfix. But for a third-party reviewer they still read as "two files the operator says go together" — the binding lives in the operator's head.

Sprint 3 adds an explicit binding artefact:

```
       Trinity dossier        Useful Compute Plan
              \                       /
               \                     /
                v                   v
          trinity_campaign.py
                       |
                       v
              Campaign Manifest
                       |
                       v
               +-----------------+
               |  PROOF BUNDLE   |
               | scorecard_sha   |
               | dossier_sha     |
               | plan_sha        |
               | campaign_sha    |
               +-----------------+
                       |
                       v
        (manual) sost-cli send --capsule-mode doc-ref-open ...
```

The Campaign Manifest is the third reproducible artefact. Its SHA-256 (`canonical_json(manifest)` → `sha256`) is what the operator would register on chain. Three independent SHAs now anchor one campaign.

## 2. What the engine reads vs writes

### Reads

- `TRINITY_DEMO_DOSSIER_<aoi>.json` (raw bytes; SHA-256 of the bytes is what the manifest stores).
- `TRINITY_USEFUL_COMPUTE_PLAN_<aoi>.json` (same).
- Nothing else. No network. No external API. The CLI script accepts only file paths.

### Writes

- `TRINITY_CAMPAIGN_<name>.json` — canonical JSON of the manifest.
- `TRINITY_CAMPAIGN_<name>.md` — human-readable view with the proof bundle table, evidence gaps, ranked next actions, the mirrored UC queue, the safety status block, and a "What this document is NOT" disclaim block.

The engine does **not** touch the dossier or plan files. They remain the upstream sources of truth.

## 3. Components

### `materials-engine-private/src/trinity/campaign_engine.py`

Bridge module. ~640 LOC. Public dataclasses:

- `CampaignObjective` — what the engine is trying to achieve, derived from the inputs.
- `EvidenceGap` — one per recognised deficiency. `gap_id` is taken from the closed taxonomy `ALL_GAPS`. Severity ∈ {info, medium, high, critical}.
- `NextAction` — one concrete proposal. Classified into a bucket and a safety tier; carries a `forbidden_reason` if the bucket is `unsafe_or_forbidden`.
- `CampaignManifest` — the assembled output. Includes `ready_to_register=True` and `registered=False` as immutable defaults; no code path sets `registered=True`.
- `ProofBundle` — thin view over the four anchor SHAs that would be registered together.

Public functions:

- `detect_evidence_gaps(dossier, useful_compute_plan)` — returns a deterministically-sorted list of EvidenceGap.
- `_propose_actions_for_gaps(gaps, plan, aoi)` (private) — generates the action candidate list, including always-present `unsafe_or_forbidden` anchor entries (activate rewards / publish reward tasks / register on chain / move funds / modify consensus).
- `rank_next_actions(actions)` — sort by (safety asc, impact desc, prerequisites asc, bucket order, action_id). Safety is the outermost key so forbidden items land at the bottom regardless of declared impact.
- `build_campaign_from_dossier(dossier, useful_compute_plan, *, campaign_name, dossier_sha256, useful_compute_plan_sha256, generated_at_utc)` — top-level builder.
- `generate_proof_bundle(manifest, *, campaign_sha256)` — wraps the four anchor SHAs into a ProofBundle.

Action bucket taxonomy (closed set):

| Bucket | Meaning |
|---|---|
| `immediate_local` | Operator can run on their laptop today; no external dependency. |
| `useful_compute_candidate` | Maps to a `candidate_reward_worthy` family in the plan. Currently dry-run. |
| `needs_external_data` | Requires data not in the repo (Sentinel tiles, geophysical surveys, etc.). |
| `needs_operator_review` | Action requires human judgement before automation. |
| `blocked` | Cannot proceed until a prerequisite action completes. |
| `unsafe_or_forbidden` | The engine refuses to enqueue this; the bucket is permanent. |

The `unsafe_or_forbidden` veto runs as a substring match on title + description against a closed list of phrases (`activate reward`, `publish reward-bearing`, `enable rewards`, `broadcast capsule`, `register hash on chain`, `modify consensus`, `move funds`, `transfer sost`, `broadcast transaction`, `open public api`, `expose public endpoint`, `deploy public dashboard`, `edit useful_compute_worker`, etc.). The veto runs FIRST and overrides any suggested bucket from the caller.

### `sost-core/scripts/trinity/trinity_campaign.py`

CLI entrypoint. ~280 LOC. Reads the two input JSON files, computes their SHAs from raw bytes (so the recorded value equals `sha256sum <file>`), calls the engine, computes the manifest's SHA over its canonical bytes, renders the Markdown report. Honours `TRINITY_MATERIALS_ENGINE_PATH` for VPS portability.

Pinned-time flag fixes `generated_at_utc` so the canonical JSON and its SHA are reproducible across runs and machines.

## 4. Evidence gap taxonomy

| `gap_id` | Severity | Trigger |
|---|---|---|
| `fallback_mode_active` | critical | `dossier.fallback_mode == True` |
| `features_available_zero` | critical | `source.scorecard_features_available == 0` |
| `missing_scorecard_provenance` | critical | dossier predates the reproducibility hotfix (no `source.scorecard_sha256`) |
| `no_ranked_targets` | high | no `mineral_target` hypotheses in `dossier.reviews` |
| `missing_geophysical_layer` | high | `honesty_matrix.what_it_doesnt_see` cites ERT / gravity / magnetics / geophysics |
| `missing_spectral_evidence` | high | features=0 AND blind spots mention spectral / vegetation / C-band |
| `no_coordinates` | medium | any `mineral_target` review missing lat/lon |
| `no_deposit_type` | medium | any `mineral_target` review missing canonical deposit_type |
| `weak_council_confidence` | medium | avg confidence < 0.6 OR any decision in {hold, contradicted} |
| `missing_validation_dataset` | medium | any review with an empty `validation_path` |
| `dry_run_useful_compute_only` | info | `plan.dry_run == True` (always today) |

The taxonomy is closed; new gap types require a code change and a new test.

## 5. Demo output on Kalgoorlie phase 1

```
campaign:                kalgoorlie_phase1
scorecard_sha256:        836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246
dossier_sha256:          d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf
useful_compute_plan_sha: 1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49
campaign_sha256:         7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df

evidence gaps emitted:    7
  critical: fallback_mode_active, features_available_zero
  high:     no_ranked_targets, missing_geophysical_layer, missing_spectral_evidence
  medium:   weak_council_confidence
  info:     dry_run_useful_compute_only

next actions: 13 (ranked safe-first, high-impact-first within safety tier)
  immediate_local:           (after blocked prerequisites land)
  needs_external_data:       2
  needs_operator_review:     1
  useful_compute_candidate:  4
  blocked:                   1
  unsafe_or_forbidden:       5  ← anchor list

ready_to_register: True
registered:        False
dry_run:           True at every level
```

## 6. What the engine refuses

The closed forbidden-substring veto blocks the following classes of action from ever appearing as `executable`:

- activate Useful Compute rewards;
- publish reward-bearing tasks to the public Useful Compute API;
- enable rewards (any phrasing);
- broadcast a capsule or register a hash on chain;
- modify consensus / miner / node / RPC schema;
- move funds, transfer SOST, broadcast a transaction;
- open a public API / expose a public endpoint / deploy a public dashboard;
- edit or modify `useful_compute_worker.py`.

The veto is implemented in `_route_action_bucket` and is enforced by tests at every layer (`test_forbidden_substrings_route_to_unsafe`, `test_unsafe_actions_always_present`, `test_no_executable_action_is_forbidden`).

## 7. Cross-machine reproducibility

After this branch the chain is:

```
sha256sum scorecard_kalgoorlie.json
    → matches source.scorecard_sha256 inside the dossier
    → 836b677c14a73ee3f44b3cf066c82bd5e933c692eaf359c468674d9b48ba8246

sha256sum TRINITY_DEMO_DOSSIER_kalgoorlie.json
    → matches dossier_sha256 inside the manifest
    → d0bbc47e62f3d51baa5c535cbf4cf20e9e3d1395003588c9b8b53e43e3d22fdf

sha256sum TRINITY_USEFUL_COMPUTE_PLAN_kalgoorlie.json
    → matches useful_compute_plan_sha256 inside the manifest
    → 1e7ab30aa1595c8f19114382710536ed8faf0b6122ae16f441a34b55a2647b49

canonical_json(manifest) | sha256
    → 7253cf30cf2f45e6dc5979fd8c2ea058397fa7d35356b7a2a2f28bb7ca4d85df
```

A third party with only the four hashes can:
1. Independently verify each artefact (`sha256sum` on the JSON files matches the recorded SHA).
2. Re-run `python3 trinity_campaign.py --pinned-time ...` with the same inputs and obtain byte-identical manifest output.
3. Inspect the manifest's `safety_status` block to confirm dry-run and no on-chain side effects.

## 8. Tests (109 total across both repos)

- `materials-engine-private/tests/test_campaign_engine.py` — 23 tests: evidence-gap detection (per-gap, deterministic order, closed taxonomy), action routing (forbidden-substring veto, fallback bucket, safe defaults), manifest assembly (shape contract, dry_run propagation, ready_to_register/registered defaults, unsafe anchor presence, invalid-input errors), ranking (impact within safety, forbidden last), reproducibility (deterministic SHA, no absolute path leak), proof-bundle composition, and a static check on the module's public surface.
- `sost-core/tests/trinity/test_trinity_campaign.py` — 13 tests: end-to-end main() runs, SHA-256 of inputs matches `hashlib.sha256(bytes)`, pinned-time determinism, error paths, Markdown safety rendering (DRY-RUN banner, "What this document is NOT" block), and a path-hygiene check that `tmp_path` and host markers do not leak into the canonical JSON.

All tests are deterministic and run without network.

## 9. Sprint 4 — proposed, not implemented

- Replace the heuristic deposit-type-to-materials map in `geo_target_council.py` with a live Materials Engine API call (`/explain-formula`, `/similar`) to ground the dossier's industrial-relevance text in actual data.
- Persist campaign manifests into `multi_ai_review.canonical_memory` so cross-session memory tracks all generated bundles.
- Add `--register` flag that **prepares** a `DOC_REF_OPEN` capsule body with the four-anchor proof bundle, prints the exact `sost-cli send` command, but **does not broadcast** (the broadcast step remains operator-driven for safety until N=2 verification of the Useful Compute path lands).
- Generate a second campaign on Pilbara or Zambia once those scorecards exist with real features.

Sprint 4 is **not** implemented in this branch.
