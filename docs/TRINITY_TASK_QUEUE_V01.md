# Trinity Task Queue v0.1

**Sprint:** 5.26
**Status:** local-dry-run only · Governor-observed · Watchdog-checked · no wallet / no broadcast
**Depends on:** Sprint 5.23 (Governor) · Sprint 5.24 (Operator Loop Governor Hook) · Sprint 5.25 (Watchdog)

---

## 1. Why it exists

Sprints 5.23 – 5.25 established the audit primitives: the Governor
evaluates each pipeline step, the operator loop records every
decision, the Watchdog summarises the trail externally. None of
those changes shifted Trinity off the **manual one-shot** model —
an operator still had to type one `useful_compute_operator_loop.py`
invocation per request.

The Task Queue is the first step toward autonomous operation. It
is a local, deterministic, schema-validated queue of Useful Compute
requests. The queue runner picks one pending item, feeds it
through the operator loop **with the Governor hook always on**,
runs the Watchdog over the resulting decisions, and marks the item
completed / failed based on the audit verdict.

It deliberately stays **dry-run only**:

- The runner only accepts `--mode local-dry-run`.
- Every operator-loop invocation passes the explicit confirmation
  token `I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP`.
- It never touches wallets, signs, broadcasts, or shells out.
- A Governor hard-block (rc=3) marks the item failed and refuses
  to retry inside the same `run-once` call.
- A Watchdog `safety_status=critical` marks the item failed even
  if the operator loop returned rc=0.

```
            ┌─────────────┐  enqueue   ┌─────────────────────┐
operator -->│ task_queue  │ ─────────► │ pending/<id>.json    │
            └─────┬───────┘            └─────────────────────┘
                  │ run-once
                  ▼
            ┌─────────────────────┐ subprocess(argv only)
            │ operator_loop.py    │ ──────────────────► decisions/
            │ + --governor-policy │
            └─────────┬───────────┘
                      │ rc 0 / 2 / 3
                      ▼
            ┌─────────────────────┐ subprocess(argv only)
            │ governor_watchdog.py│ ──────────────────► report.json
            └─────────┬───────────┘
                      │ safety_status
                      ▼
       ┌─────────────────────────────────┐
       │ completed/<id>.json     (ok)    │
       │ failed/<id>.json        (else)  │
       └─────────────────────────────────┘
```

---

## 2. Queue layout

```
queue-dir/
    queue.json                      ← index of items + queue_id
    pending/<id>.json               ← waiting
    running/<id>.json               ← in-flight (rare: only mid-run)
    completed/<id>.json             ← finished + audit paths
    failed/<id>.json                ← failed + last_error
    reports/<id>/
        operator_run/               ← operator_loop --out-dir
            operator_run.json
            governor_decisions/
                TRINITY_AUTONOMY_GOVERNOR_DECISION_*.json
        watchdog/                   ← watchdog --out-dir
            TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json
```

The per-status filesystem layout is **for inspection**, not for
authoritative state. The single authoritative state file is
`queue.json` — its `items[].status` is what `list` and `run-once`
read. The per-status directories are a kind self-documenting
mirror of the index.

---

## 3. CLI surface

```
python3 scripts/trinity/task_queue.py init \
    --queue-dir DIR \
    [--pinned-time ISO]

python3 scripts/trinity/task_queue.py enqueue \
    --queue-dir DIR \
    --request-json FILE \
    --worker-address-map FILE \
    --governor-policy FILE \
    --pinned-time ISO \
    [--max-attempts N]            # default 3

python3 scripts/trinity/task_queue.py list \
    --queue-dir DIR

python3 scripts/trinity/task_queue.py run-once \
    --queue-dir DIR

python3 scripts/trinity/task_queue.py inspect \
    --queue-dir DIR \
    --queue-item-id qit-<16hex>

python3 scripts/trinity/task_queue.py validate \
    --queue-dir DIR
```

All commands exit 0 on success, 2 on any `QueueError` (missing
file, malformed input, validation failure, etc.). `run-once`
specifically returns 0 even when the item ends in `failed/` —
the `last_error` in the item JSON is the source of truth.

---

## 4. Queue item contract

`schemas/trinity/task_queue.schema.json` exposes the item shape
under `$defs/queue_item`. Required fields:

| field | shape |
|-------|-------|
| `schema` | const `"trinity-task-queue-item/v0.1"` |
| `queue_item_id` | `^qit-[0-9a-f]{16}$`, sha16 of `(pinned_time, request_sha256, policy_sha256, worker_address_map_basename)` |
| `request_json_path` | absolute path on disk |
| `worker_address_map_path` | absolute path on disk |
| `governor_policy_path` | absolute path on disk |
| `request_json_path_basename` | audit-friendly basename |
| `worker_address_map_path_basename` | audit-friendly basename |
| `governor_policy_path_basename` | audit-friendly basename |
| `status` | `pending` / `running` / `completed` / `failed` |
| `created_at` · `updated_at` · `pinned_time` | ISO strings |
| `attempt_count` · `max_attempts` | int, max_attempts ≤ 16 |
| `last_error` | string or null |
| `operator_run_path` | path to operator_run.json or null |
| `watchdog_report_path` | path to watchdog report or null |
| `policy_sha256` | sha256 of governor policy at enqueue time |
| `request_sha256` | sha256 of request.json at enqueue time |
| `threat_refs` | items match `^T[0-9]{2}$` |
| `governor_decisions_count` | int ≥ 0 |
| `watchdog_safety_status` | enum `{ok, warning, stale, critical}` or null |

The two `sha256` fields are pinned at **enqueue** time. If either
file is mutated between enqueue and run-once, the operator loop's
own Governor hook detects the policy mutation (`rc=3` →
`governor_hard_block`); a mutated request.json produces a
mismatched `input_bundle_sha256` further down and the operator
loop exits non-zero on its own.

---

## 5. Fail-closed semantics

`run-once` has exactly four exit branches per item:

| Operator rc | Watchdog `safety_status` | Item status | `last_error` |
|-------------|--------------------------|-------------|--------------|
| 0           | `ok` / `warning` / `stale` | `completed` | null |
| 0           | `critical`               | `failed`    | "watchdog reported safety_status=critical …" |
| 3           | (not run)                | `failed`    | "governor_hard_block: operator_loop exited rc=3 …" |
| any other ≠ 0 | (not run)              | `failed`    | "operator_loop exited rc=N …" |

There is **no retry** inside `run-once`. `attempt_count` is bumped
each time the operator decides to handle the item; bringing the
queue back to retry a `failed` item is an operator decision
(future sprint will likely add an `--include-failed` flag for that).

---

## 6. Tests added in Sprint 5.26

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_task_queue.py` | 19 | init creates structure · init refuses re-init · queue_id determinism · enqueue with hashes · duplicate refused · missing files refused · basenames persisted · list counts · inspect · inspect unknown id · **run-once happy path (subprocess to operator_loop + watchdog)** · operator_run + watchdog audit paths populated · no pending ⇒ None · missing request.json ⇒ failed · halt-file ⇒ governor_hard_block ⇒ failed · validate clean queue · validate catches malformed item · validate catches corrupt queue.json · mode lock rejects non-local-dry-run · CLI init+enqueue+list+run-once+validate end-to-end |
| `tests/trinity/test_task_queue_schema.py` | 14 | Schema is valid draft-07 · v0.1 id · status enums (queue + item) · `queue_item.schema` const lock · queue_item_id / queue_id / sha256 / threat_refs patterns · watchdog status enum · max_attempts bounds · queue.json validates after init · queue item validates after enqueue · completed item after run-once validates with full audit fields |
| `tests/trinity/test_task_queue_safety.py` | 11 | Source has no wallet/sign/broadcast/payment/shell/network tokens · subprocess used in argv form only · `local-dry-run` mode is the only allowed value · confirmation token always passed · `--governor-policy` always passed · hard-block + watchdog critical paths referenced · does NOT import sibling Trinity modules · cross-check Governor + Watchdog safety unchanged |

Total: **44 new tests**.

---

## 7. Non-goals for v0.1

- **No daemon.** v0.1 is `run-once` per invocation. Cron / systemd
  timer / loop in shell are fine; a long-running daemon is a
  later sprint.
- **No retries.** A failed item stays failed. The operator decides
  whether to re-enqueue. (`max_attempts` is recorded on the item
  so a future retry mode has the budget primitive ready.)
- **No priorities.** Strict FIFO by `created_at`.
- **No concurrency.** v0.1 assumes one runner. Two concurrent
  `run-once` calls against the same queue would race on the
  index update. The atomic queue.json write narrows the window
  but does not eliminate it — proper locking lands with the
  daemon sprint.
- **No remote queue.** Queue is local files. Network-shared queue
  storage is out of scope.
- **No autonomous re-enqueue.** The queue does not create new
  requests; an external producer (operator, intake script, future
  source-tool registry) must enqueue.
- **No wallet, signing, broadcasting, or real payment.** Even with
  `--governor-policy`. The mode lock + token + static safety test
  pin this in three independent places.

---

## 8. Manual demo

Using the Sprint 5.24 fixtures + the Sprint 5.23 example policy:

```bash
# 1. init
python3 scripts/trinity/task_queue.py init \
    --queue-dir /tmp/trinity-5-26-queue \
    --pinned-time 2026-05-17T00:00:00+00:00

# 2. enqueue one scientific_intake request
python3 scripts/trinity/task_queue.py enqueue \
    --queue-dir /tmp/trinity-5-26-queue \
    --request-json tests/trinity/fixtures/useful_compute/request_scientific_intake.json \
    --worker-address-map tests/trinity/fixtures/useful_compute/address_map.json \
    --governor-policy config/trinity_autonomy_governor.example.json \
    --pinned-time 2026-05-17T00:00:00+00:00

# 3. run-once: operator_loop with --governor-policy + watchdog scan
python3 scripts/trinity/task_queue.py run-once \
    --queue-dir /tmp/trinity-5-26-queue

# 4. inspect the final item
python3 scripts/trinity/task_queue.py list \
    --queue-dir /tmp/trinity-5-26-queue
```

Expected on a clean run: one item ends in `completed/` with
`governor_decisions_count=7` and `watchdog_safety_status=ok`.

---

## 9. Traceability

- `request_json` files must conform to the Sprint 5.22 schema
  `trinity-useful-compute-request/v0.1`.
- `governor_policy` files must conform to the Sprint 5.23 schema
  `trinity-autonomy-governor-policy/v0.1`.
- The runner invokes Sprint 5.24's operator loop with
  `--governor-policy` always set, so every completed item carries
  exactly **7** governor decisions in its `reports/<id>/operator_run/
  governor_decisions/`.
- The Watchdog (Sprint 5.25) consumes those decisions and produces
  exactly **1** report under `reports/<id>/watchdog/`. The report's
  `safety_status` is lifted into the queue item's
  `watchdog_safety_status` and gates the completed-vs-failed
  branch.
- Pure scripts + schemas + docs + tests merge. Zero `src/`, zero
  consensus, zero wallet / payment / broadcast changes.
