# Trinity / Materials Track — v0 Architecture

Trinity is **one** scientific discovery system with **two** verticals. This
document describes the second one, Materials Track, and how it shares
infrastructure with the existing Earth Track.

```
                          T R I N I T Y
                                │
        ┌───────────────────────┴───────────────────────┐
        │                                               │
   EARTH TRACK                                   MATERIALS TRACK
   (shipped v0.4)                                (this sprint, v0.0)
        │                                               │
  GeaSpirit scorecard                       materials_scorecard
        │                                               │
  AI Council dossier  ◄──── shared classifier ────►  AI Council dossier
        │                                               │
  Useful Compute plan ◄──── shared family catalog ───►  Useful Compute plan
        │                                               │
  Campaign manifest   ◄──── shared bucket taxonomy ─►  Campaign manifest
        │                                               │
        └────────────► trinity_proof_bundle ◄───────────┘
                              │
                  optional registration on SOST
                  (operator-driven, manual)
```

## What is shared

Every layer below the **scorecard** is track-agnostic and lives in the same
codebase. The same `trinity_proof_bundle.py`, `verify_trinity_bundle.py`,
`trinity_proof_registry.py` and `verify_trinity_registry.py` accept output
files from both tracks. The proof bundle algorithm (binary Merkle over four
SHA-256 leaves) does not care whether the upstream data came from satellite
imagery or from a candidate material structure.

The proof registry schema (`trinity-proof-registry/v0`) gains one optional
field per entry — `track` ∈ {`earth`, `materials`} — defaulting to `earth`
for backward compatibility with the existing Kalgoorlie Phase 1 record.

## What is new for Materials Track v0

| File | Role |
|---|---|
| `scripts/trinity/materials_scorecard.py` | Mock-first builder for `TRINITY_MATERIALS_SCORECARD_<campaign>.json`. Produces pinned deterministic data resembling Materials Engine's `frontier` + `novelty` modules. |
| `scripts/trinity/materials_dossier.py` | Bridge from materials scorecard to per-candidate hypotheses. Runs each through a deterministic mock AI Council (validator + materials_expert + novelty_judge) with strict-veto combine rule. |
| `scripts/trinity/materials_compute_plan.py` | Builds a Useful Compute Plan biased toward DFT / MLIP / quantum families that materially address the candidates' open evidence gaps. |
| `scripts/trinity/materials_campaign.py` | Composes dossier + plan into a Campaign Manifest. Reuses the 11-gap taxonomy and 6-bucket NextAction ranking concepts. Forbidden-substring safety veto stays mandatory. |
| `TRINITY_MATERIALS_TRACK.md` | This document. |

## What is **not** done in v0

- **No live Materials Engine integration.** Every script supports a
  `--live-materials-engine` flag in v0 that logs `not yet implemented;
  using mock`. The flag exists so v0.1 can wire it without changing the
  CLI surface.
- **No on-chain registration.** The produced
  `TRINITY_MATERIALS_PROOF_BUNDLE_novel_frontier_phase1.json` carries
  `registered=false`, `ready_to_register=true`. The Trinity Proof Registry
  is not updated with a materials entry; that decision is reserved for
  the operator and is independent from Sprint 5.2.
- **No web page rewrite.** Per operator directive, only the intro copy on
  `sost-trinity.html` and the explorer banner have been adjusted (commit
  `f9e31e4`) to read utility-first. The full two-vertical layout is
  deferred until the operator approves publishing Materials Track on the
  site.
- **No rewards activation.** Useful Compute rewards stay dry-run. The
  Materials Track plan is a planning artefact only.
- **No consensus / RPC / node / wallet change.**

## v0 demo campaign — `novel_frontier_phase1`

The user-chosen demo campaign mirrors the Kalgoorlie Phase 1 honesty
matrix: low `features_available`, validator-veto-driven `hold` on most
candidates, explicit evidence-gap inventory. This proves the pipeline
works end-to-end without overclaiming a real materials discovery.

Candidate seed set (pinned for v0):

| candidate | formula | family | seed_novelty | seed_frontier_proximity |
|---|---|---|---|---|
| C-01 | Fe2MgO4 | spinel oxide | 0.62 | 0.71 |
| C-02 | LiNi0.5Mn1.5O4 | layered oxide / cathode candidate | 0.48 | 0.59 |
| C-03 | BaZrO3:Y | perovskite / proton conductor | 0.55 | 0.66 |
| C-04 | CaCu3Ti4O12 | giant-permittivity oxide | 0.41 | 0.52 |
| C-05 | Co3O4 | transition-metal oxide reference | 0.30 | 0.40 |

These are public, well-studied formulas. The point of v0 is **not** to
claim novelty for them but to demonstrate that the pipeline correctly
runs each through the AI Council, identifies evidence gaps, proposes
heavy-compute tasks (e.g. MLIP relaxation, DFT input prep) and seals the
campaign into a verifiable bundle.

## Why mock-first

1. **Cross-machine reproducibility.** Pinned-data outputs are
   byte-identical on WSL and the VPS. A live Materials Engine call would
   depend on a private repo's exact state and reduce reproducibility.
2. **No `materials-engine-private` import in `sost-core`.** Keeping the
   private repo out of the public branch's dependency surface preserves
   the deployment story.
3. **Explicit honesty.** The dossier's `source` block records
   `mode: "mock"` so any reader knows the underlying interpretations are
   placeholder, not Materials Engine's real reviews. The `--live-`
   flag's stub log makes that explicit at run time.

## v0.1 candidates (out of scope for this sprint)

- Wire `--live-materials-engine` to actually import the AI Council from
  `TRINITY_MATERIALS_ENGINE_PATH` and replace the mock reviews.
- Pull frontier/novelty inputs from live Materials Engine endpoints.
- Add a `track=materials` entry to the Proof Registry once the operator
  approves on-chain registration.
- Add a two-vertical column layout to `sost-trinity.html` showing Earth
  Track and Materials Track side by side.
