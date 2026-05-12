# Trinity Background Autonomy Daemon v0.1

## What the daemon does

`scripts/trinity/trinity_background_daemon.py` is the smallest piece
of code that turns the four Trinity verticals into a **controlled,
local, dry-run loop**:

1. **Orchestrator** — runs `trinity_orchestrator.run_orchestrator()`
   in-process, captures the useful-compute requests it emits, and
   normalises them into `inbox/requests/`.
2. **Worker** — for each request without a result from the current
   `--worker-id`, runs `useful_compute_worker.run_worker()` and
   writes the result + pending reward files into `work/results/`
   and `work/rewards/`.
3. **Replay validator** — for every request that now has results
   from `>= --min-workers` distinct workers, runs
   `useful_compute_replay_validator.run_validation()` and writes
   the validation report into `validation/`.
4. **Governance gate** — runs
   `useful_compute_governance_gate.run_governance_gate()` over the
   accumulated validations + pending rewards and writes the
   review-only batch into `governance/`.

After every cycle the daemon writes:

- `TRINITY_BACKGROUND_DAEMON_STATE.json` (schema
  `trinity-background-daemon-state/v0.1`, strict, additionalProperties
  false)
- `TRINITY_BACKGROUND_DAEMON_SUMMARY.md` (human-readable)
- `TRINITY_BACKGROUND_EVENTS.jsonl` (append-only)
- `lessons/TRINITY_AUTONOMY_ERROR_LEDGER.jsonl` (error_memory)

## What it does NOT do

The daemon:

- does NOT pay
- does NOT sign, broadcast, send, or activate any transaction
- does NOT touch any wallet, private key, or seed phrase
- does NOT make any network call (HTTP, socket, RPC, beacon)
- does NOT spawn subprocesses; every sub-tool is imported via
  `importlib`
- does NOT register anything on-chain
- does NOT modify consensus, tx_validation, tx_signer or transaction
  format

The CLI explicitly rejects `--broadcast`, `--payout`, `--send`,
`--wallet`, `--network`. The only accepted `--mode` is
`local-dry-run`.

## Why local-dry-run

Because v0.1 of Trinity has no governance-signed payment surface
yet. The daemon is the runtime that makes Trinity *behave like a
system*, but until the payment sprint lands, the daemon must never
produce a side effect that survives outside its workspace.

`safety_status.human_review_required_before_payment = true` is the
load-bearing flag in every emitted state document. A human review
step is the contract.

## Folder layout

```
<workspace>/
  inbox/requests/        TRINITY_USEFUL_COMPUTE_REQUEST_<rid>.json
  work/results/          TRINITY_USEFUL_COMPUTE_RESULT_<rid>_<wrid>.json
  work/rewards/          TRINITY_USEFUL_COMPUTE_PENDING_REWARD_<rid>_<wrid>.json
  validation/            TRINITY_USEFUL_COMPUTE_VALIDATION_<rid>.json
  governance/            TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_<batch_id>.json
  summaries/             per-cycle MD summaries (reserved)
  lessons/               TRINITY_AUTONOMY_ERROR_LEDGER.jsonl
  orchestrator/          internal: full orchestrator output

  TRINITY_BACKGROUND_DAEMON_STATE.json
  TRINITY_BACKGROUND_DAEMON_SUMMARY.md
  TRINITY_BACKGROUND_EVENTS.jsonl
```

## How it learns from errors

Every stage records a lesson in
`lessons/TRINITY_AUTONOMY_ERROR_LEDGER.jsonl` (via
`trinity_error_memory.record_lesson`) when:

- the orchestrator fails (cause `compute_failed`)
- the worker fails on a specific request (cause `compute_failed`,
  inputs tagged with `request_id` + `worker_id`)
- the replay validator fails (cause `validation_failed`)
- the validator declares `mismatch` (cause `overclaim_risk`, written
  by the validator itself)
- the governance gate rejects an item (cause varies by reason,
  written by the gate itself)

Before running the worker on a request, the daemon queries the
ledger for `has_repeat_lesson("useful_compute", {"request_id": rid,
"worker_id": worker_id})`. If a lesson exists, the request is
**skipped** unless `--allow-known-failures` is set. This is the
"don't repeat the same failure" contract from Sprint 5.6, applied
to the autonomy loop.

The summary surfaces the top causes so a human reviewer can decide
whether to clear a class of lessons.

## How it connects the four verticals

- **Geaspirit** and **Materials Engine** live inside the
  orchestrator stage. If `materials-engine-private` is not
  reachable, those pipelines fail; the daemon records lessons and
  continues with whatever requests already exist in the inbox.
- **Useful Compute** lives in the worker, replay validator and
  governance gate stages. The daemon glues them so a request flows
  from inbox → result → validation → governance batch on its own.
- **SOST AI** is invoked by the orchestrator (real free-tier
  council when available, deterministic heuristic otherwise). Its
  decisions appear in the orchestrator's ledger
  (`orchestrator/TRINITY_AUTONOMY_LEDGER.jsonl`); the daemon does
  not call the council directly.

## Running it

### Run-once (deterministic)

```
python3 scripts/trinity/trinity_background_daemon.py \
  --mode local-dry-run \
  --run-once \
  --workspace /tmp/trinity-daemon-test \
  --objectives config/trinity/objectives \
  --seed trinity-autonomy-v0.1 \
  --pinned-time 2026-05-12T00:00:00+00:00 \
  --count 25 \
  --worker-id miner-local-001 \
  --reviewer-id reviewer-local-001
```

Same seed, same pinned-time, same workspace basename → same state
bytes.

### Watch (loop)

```
python3 scripts/trinity/trinity_background_daemon.py \
  --mode local-dry-run \
  --watch \
  --interval-seconds 300 \
  --max-cycles 12 \
  --workspace /tmp/trinity-daemon \
  --objectives config/trinity/objectives \
  --worker-id miner-local-001 \
  --reviewer-id reviewer-local-001
```

`--interval-seconds` is clamped to `[1, 3600]`. `--max-cycles`
defaults to unlimited; supply a number to keep watch runs bounded.

### Stopping

`Ctrl-C` is enough. The daemon does not register signal handlers
beyond Python's default. Each cycle is atomic: state on disk after
cycle N is consistent and re-readable.

## Risks (read before scaling)

- **Loops with no work.** If the orchestrator cannot reach the
  council, every cycle produces zero new requests. The daemon will
  still log a lesson and write state. Use `--max-cycles` to bound
  empty loops.
- **Energy cost.** Each cycle reruns the orchestrator + worker +
  validator + gate. With the v0.1 placeholders this is cheap; once
  real backends land (Sprint 5.12) the cost will not be.
- **Reward inflation within caps.** The conservative governance
  policy floors rewards across replicators, but a coalition of N
  workers controlled by the same operator can still saturate at
  the per-task cap. Human review remains required.
- **Worker fatigue.** A single `--worker-id` cannot generate the
  `>= --min-workers` agreement needed for an `accepted` validation.
  In real deployments, multiple operators with distinct worker_ids
  must contribute. The daemon does not gossip results across
  machines.
- **Repeated failures.** A request that keeps failing will be
  skipped silently after the first lesson. The summary surfaces the
  top causes; the operator must decide when to clear them.
- **Determinism vs. wall-clock.** `--pinned-time` is required for
  byte-identical state. Without it, `started_at` /
  `last_cycle_at` reflect real time and the state file changes
  every cycle.

## How to read the summary

`TRINITY_BACKGROUND_DAEMON_SUMMARY.md` is the file a human should
open. It carries:

- the workspace basename + cycle index
- counts (requests, results, validations, batches, errors, lessons)
- the list of pending request_ids
- the list of accepted_validation_ids
- the list of approved_batch_ids
- the top error_memory causes
- the safety flags

A reviewer who only reads the summary should be able to decide
whether the daemon is healthy, whether to clear a stale lesson, and
whether a governance batch is worth promoting to the (future)
payment sprint.
