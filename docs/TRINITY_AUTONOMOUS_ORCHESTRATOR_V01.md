# Trinity Autonomous Orchestrator v0.1

## What Trinity Autonomy is

Trinity Autonomy is the central coordination layer where the SOST AI
council organises four verticals into a single, auditable, dry-run
loop:

1. **Geaspirit / Geo Discovery** — autonomous proposal of underexplored
   areas of interest (AOIs) from open data only.
2. **Materials Engine** — autonomous proposal of candidate materials,
   scored by structural and atomic plausibility.
3. **Useful Compute** — packaging of verifiable compute tasks and a
   pending-reward model in stocks. v0.1 never pays.
4. **SOST AI Council** — central planner that ranks options, decides
   the next action, and logs every decision.

v0.1 is **dry-run, offline, and never on-chain**. It is the wiring,
not the engine that pays. A separate sprint must enable miner-side
contribution and on-chain rewards through governance.

## How SOST AI coordinates

`scripts/trinity/sost_ai_orchestrator_adapter.py` implements a small
adapter with two execution paths:

- **Real free-tier council critic** (default when
  `materials-engine-private` is reachable via
  `TRINITY_MATERIALS_ENGINE_PATH` or `~/SOST/materials-engine-private`).
  The adapter builds a `Hypothesis` per option and asks the
  `AICouncil` (Validator + LocalKnowledge + MockAI) to score it. The
  council is a **critic**, not an authority: its score is blended
  70/30 with a deterministic heuristic.
- **Deterministic heuristic** fallback when the council is not
  available. This keeps Trinity runnable on hosts without the private
  repo (e.g. the production VPS).

Every decision is appended to `TRINITY_AUTONOMY_LEDGER.jsonl` with:
- pinned timestamp
- input hashes (objectives_hash, candidate hashes)
- selected option
- whether the real council was used and from which path
- the reason string
- emitted useful-compute request id (if any)
- pending reward forecast

## How Geaspirit searches for AOIs

`scripts/trinity/geo_discovery_pipeline.py` is the existing v0.1 geo
pipeline. The orchestrator invokes it in-process with the seed and
pinned time from `config/trinity/objectives/geaspirit.json`. Outputs:

- 26-belt offline catalog of candidates
- transparent filter (demo-AOI proximity, bbox overlap, protected
  areas)
- 7-axis weighted scorer
- dossier with seven required disclaimers and a real-council review
- compute plan + campaign manifest + proof bundle

Trinity Autonomy reads the dossier's `aois` list and picks the
`accept` entries.

## How Materials Engine searches for materials

`scripts/trinity/materials_discovery_pipeline.py` (v0.2) follows the
same shape. The orchestrator reads the dossier's `hypotheses` list
and picks the `accept` entries.

## When Useful Compute is requested

For every selected option, the orchestrator checks the vertical's
`min_score_for_uc_request` threshold (geo: 80.0 on a 0–100 scale;
materials: 0.70 on a 0–1 scale). If the candidate clears the
threshold, the orchestrator emits a
`trinity-useful-compute-request/v0.1` manifest via
`useful_compute_task_builder`. The manifest is written to disk and
**never broadcast** — the builder's `--emit` flag is explicitly
rejected in v0.1.

## How pending rewards in stocks are measured

`scripts/trinity/useful_compute_reward_model.py` is the deterministic
reward model. Input:

```
task_id, worker_id,
benchmark_score, verified_compute_seconds,
difficulty_class (low|medium|high|extreme),
result_validated, duplicate_result,
max_reward_stocks
```

Output:

```
{
  "schema": "trinity-useful-compute-reward/v0.1",
  "pending_reward_stocks": <int>,
  "reason": <string>,
  "requires_manual_review": <bool>,
  "deterministic_id": <16-hex>
}
```

Hard rules baked into the model:

- invalid result → 0 stocks
- duplicate result → 0 stocks (configurable factor)
- benchmark below floor → 0 stocks
- normalised seconds capped (anti-DoS)
- benchmark capped (anti-gaming)
- reward capped at `max_reward_stocks`

## Why there is no automatic payout

Two reasons:

1. **Verification.** v0.1 does not yet implement the cross-worker
   replay required to declare a result valid. The reward layer must
   never pay before verification works.
2. **Governance.** Any move from `pending_reward_stocks` to actual
   stocks needs an explicit governance step. v0.1 deliberately
   refuses to ship that step.

## What is missing before production

- A real miner-side worker that fetches tasks, runs them and submits
  results with a verifiable output bundle.
- Cross-worker validation strategy (redundant replay + consensus on
  the output hash).
- Governance gate that promotes `pending_reward_stocks` into actual
  stock issuance.
- Live geo data sources (satellite + DEM + geophysics) — currently
  only the offline catalog is wired.
- A live materials DFT or simulation backend — currently only
  classical scoring is wired.
- A public registry of accepted Trinity proof bundles, separate from
  the existing on-chain proof registry.

## Risks (read before scaling)

- **Gaming.** Workers may report inflated benchmarks. The model caps
  normalised seconds and benchmark, and flags suspicious work for
  manual review, but this is not yet sufficient at scale.
- **False results.** Without cross-worker replay, a malicious worker
  can submit any output. v0.1 forbids automatic payout for this
  reason.
- **Geological overclaim.** Geo dossiers must keep the seven
  disclaimers and never speak of "deposit", "reserve" or "drilling
  evidence" — except in negative form.
- **Compute waste.** The orchestrator throttles uc_requests with
  per-vertical caps and the `min_score_for_uc_request` threshold,
  but determined workers can still consume real CPU on tasks of
  marginal value.
- **Energy cost.** Useful Compute is intentionally heavier than the
  current SbPoW mining loop. Operators must opt in.
- **Human review.** Council verdicts are critics, not authorities.
  Every accepted Trinity candidate still needs a human reviewer
  before any public claim.

## Command

```
python3 scripts/trinity/trinity_orchestrator.py \
  --mode dry-run \
  --seed trinity-autonomy-v0.1 \
  --pinned-time 2026-05-11T00:00:00+00:00 \
  --objectives config/trinity/objectives \
  --count 25
```

Outputs:

- `TRINITY_AUTONOMY_LEDGER.jsonl` — append-only decision ledger
- `TRINITY_AUTONOMY_SUMMARY.md` — human-readable summary
- `TRINITY_USEFUL_COMPUTE_REQUESTS.json` — manifest index
- `TRINITY_USEFUL_COMPUTE_REQUEST_<id>.json` — one per emitted manifest
- `TRINITY_AUTONOMY_LESSONS.md` — lessons learned (error memory)
- `TRINITY_AUTONOMY_PROOF_BUNDLE_v01.json` — final bundle

## Safety invariants

`TRINITY_AUTONOMY_PROOF_BUNDLE_v01.json` carries:

```
{
  "safety_status": {
    "dry_run": true,
    "registered": false,
    "ready_to_register": false,
    "no_rewards_active": true,
    "no_paid_providers": true,
    "no_network_calls": true
  }
}
```

These are not aspirational. The Sprint 5.6 test suite enforces them
statically across every script in `scripts/trinity/` introduced by
this sprint.
