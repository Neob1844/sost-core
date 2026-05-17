# Trinity Task Queue Runner v0.1

**Sprint:** 5.27
**Status:** local-dry-run only · bounded · Governor-observed · Watchdog-checked · no wallet / no broadcast
**Depends on:** Sprint 5.23 (Governor) · Sprint 5.24 (Operator Loop Hook) · Sprint 5.25 (Watchdog) · Sprint 5.26 (Task Queue)

---

## 1. Why it exists

Sprint 5.26 landed the **queue**: enqueue items, then call
`task_queue.py run-once` to consume them one at a time. That is a
manual loop — the operator types `run-once` per item.

Sprint 5.27 adds the **runner**: a bounded wrapper that calls
`run_once()` up to `--max-items` times, records each outcome,
writes a deterministic batch report, and inherits every fail-closed
invariant from 5.26.

It is deliberately **not a daemon**:

- Hard upper bound of 50 items per invocation.
- Optional inter-item sleep capped at 3600 s.
- One process per `run-batch` call; cron / systemd timers can
  drive a loop, but the runner itself returns.
- Mode lock and confirmation token from 5.26 still apply.

The audit primitives from earlier sprints flow through unchanged:

```
                run-batch (N items)
                    │
        ┌───────────┴───────────┐
        │   for i in 1..N:      │
        │       run_once(queue) │  ← 5.26 logic, untouched
        │       record outcome  │
        │       (optional sleep)│
        └───────────┬───────────┘
                    ▼
            batch report JSON
       (schema trinity-task-queue-runner-report/v0.1)
```

---

## 2. CLI surface

```
python3 scripts/trinity/task_queue.py run-batch \
    --queue-dir DIR \
    --max-items N            # required, 1..50
    --pinned-time ISO        # required, goes into batch_id
    [--stop-on-failure]      # halt on first failed item
    [--sleep-seconds S]      # 0..3600, default 0
    [--report-path PATH]     # default: queue/reports/_batches/<batch_id>.json
```

Exit code: 0 unless the runner itself can't start (missing queue,
out-of-range bounds → rc=2). The report's `safety_status` is the
source of truth on whether action is needed.

---

## 3. Batch report contract

`schemas/trinity/task_queue_runner_report.schema.json`

```json
{
  "schema": "trinity-task-queue-runner-report/v0.1",
  "batch_id": "tqr-<16hex>",
  "pinned_time": "2026-05-17T00:00:00+00:00",
  "queue_dir_basename": "my-queue",
  "max_items": 5,
  "attempted_count": 5,
  "completed_count": 5,
  "failed_count": 0,
  "skipped_count": 0,
  "stop_on_failure": false,
  "sleep_seconds": 0,
  "item_ids": ["qit-…", …],
  "completed_item_ids": ["qit-…", …],
  "failed_item_ids": [],
  "safety_status": "ok",
  "warnings": []
}
```

`safety_status` precedence:

| status | when |
|--------|------|
| `ok` | every attempted item ended in `completed` |
| `warning` | at least one item failed AND `--stop-on-failure` was NOT set; the runner kept going to honour `--max-items` |
| `failed` | at least one item failed AND `--stop-on-failure` WAS set; the runner halted early |

The schema locks `batch_id` to `^tqr-[0-9a-f]{16}$`, every item id
to `^qit-[0-9a-f]{16}$`, `max_items` to 1..50 and `sleep_seconds`
to 0..3600.

---

## 4. Counters

- **`attempted_count`** = number of items the runner actually fed
  to `run_once()`. Capped at `max_items`. Stops short if the queue
  ran out of pending items, or if `--stop-on-failure` fired.
- **`completed_count`** = items ending in `completed/<id>.json`.
- **`failed_count`** = items ending in `failed/<id>.json`.
- **`skipped_count`** = `max_items − attempted_count`. Pure
  arithmetic; if the queue was empty and `max_items=5`,
  `attempted=0` and `skipped=5`.

The three sum identities the runner enforces:

```
attempted_count == completed_count + failed_count
attempted_count + skipped_count == max_items
len(item_ids) == attempted_count
len(completed_item_ids) == completed_count
len(failed_item_ids) == failed_count
```

(All four enforced by the schema test + runner functional test.)

---

## 5. Fail-closed contract (inherited from 5.26)

The runner does NOT re-decide failure: every per-item verdict is
the same one `run_once()` would produce when called directly.

- Operator loop rc=3 (Governor hard-block: `halt_file_present` or
  `policy_mutated_at_runtime`) → item failed, `last_error` starts
  with `governor_hard_block`. The runner records the failure and
  continues to the next item unless `--stop-on-failure` is set.
- Watchdog `safety_status=critical` → item failed even when the
  operator loop returned rc=0.
- Any other non-zero operator rc → item failed with output tail
  in `last_error`.

The runner adds **one new fail-mode** at the batch level:
`--stop-on-failure`. With it, the first failed item raises
`safety_status` to `failed` and the runner halts. Without it, the
batch keeps going and `safety_status` lands at `warning`.

---

## 6. Tests added in Sprint 5.27

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_task_queue_runner.py` | 25 (incl. parametrised) | empty queue · 1 pending item · max<pending · max==pending · max>pending (skipped_count) · oldest-first · failed-item ⇒ warning · stop-on-failure ⇒ failed + halt · max-items 0/51/-1/1000 rejected · sleep-seconds bounds rejected · queue not initialised refused · `_sleep_hook` called between items but not after the last · sleep=0 ⇒ no hook calls · default report path · explicit `--report-path` · batch_id determinism · report validates (ok/empty/failed branches) · CLI happy path · CLI invalid `--max-items` ⇒ rc=2 |
| `tests/trinity/test_task_queue_runner_safety.py` | 10 | runner has no wallet/sign/broadcast/payment/shell/network tokens · subcommand wired · bounds are named constants · `run_once()` reused not duplicated (`_run_operator_loop` and `_run_watchdog` each appear exactly twice: definition + single call site in `run_once`) · mode lock re-asserted in `run_batch` · safety_status branches wired · no sibling-module imports · cross-check Governor + Watchdog safety surfaces unchanged |

Total: **35 new tests**.

---

## 7. Manual demo

```bash
rm -rf /tmp/trinity-5-27-runner
python3 scripts/trinity/task_queue.py init \
    --queue-dir /tmp/trinity-5-27-runner

# Enqueue two copies of the scientific_intake fixture
python3 scripts/trinity/task_queue.py enqueue \
    --queue-dir /tmp/trinity-5-27-runner \
    --request-json tests/trinity/fixtures/useful_compute/request_scientific_intake.json \
    --worker-address-map tests/trinity/fixtures/useful_compute/address_map.json \
    --governor-policy config/trinity_autonomy_governor.example.json \
    --pinned-time 2026-05-17T00:00:00+00:00

python3 scripts/trinity/task_queue.py enqueue \
    --queue-dir /tmp/trinity-5-27-runner \
    --request-json tests/trinity/fixtures/useful_compute/request_scientific_intake.json \
    --worker-address-map tests/trinity/fixtures/useful_compute/address_map.json \
    --governor-policy config/trinity_autonomy_governor.example.json \
    --pinned-time 2026-05-17T01:00:00+00:00

# Run both in one batch
python3 scripts/trinity/task_queue.py run-batch \
    --queue-dir /tmp/trinity-5-27-runner \
    --max-items 2 \
    --pinned-time 2026-05-17T00:00:00+00:00

python3 scripts/trinity/task_queue.py list \
    --queue-dir /tmp/trinity-5-27-runner

python3 scripts/trinity/task_queue.py validate \
    --queue-dir /tmp/trinity-5-27-runner
```

Expected: one batch report under
`/tmp/trinity-5-27-runner/reports/_batches/` with
`attempted_count=2 completed_count=2 failed_count=0
safety_status=ok`, and two completed items each with
`governor_decisions_count=7` and `watchdog_safety_status=ok`.

---

## 8. Non-goals for v0.1

- **No daemon.** Hard upper bound, single invocation, returns when
  done. Cron / systemd timer / shell loop are the supported ways
  to drive it.
- **No concurrent batches.** Two `run-batch` calls against the
  same queue would race on the queue.json index — same caveat as
  `run-once` in 5.26. Proper locking lands with the daemon sprint.
- **No retry policy.** Failed items stay failed. A future sprint
  may add `--include-failed N` to re-enqueue.
- **No priority.** Strict FIFO by item `created_at`.
- **No webhook / external dispatch.** The runner is local-only;
  external visibility flows through the Watchdog (Sprint 5.25),
  not the runner.
- **No `--fail-on critical` exit-code mode.** The CLI returns 0
  even when the batch's `safety_status` is `failed`. Callers that
  need a non-zero exit can grep the report or write a wrapper.
  rc=2 is reserved for "the runner could not start at all".
- **No wallet / signing / broadcast.** Mode lock + token from
  5.26 + Governor hook + static safety test all enforce this in
  independent places.

---

## 9. Traceability

- The runner delegates per-item logic to Sprint 5.26's `run_once`,
  unchanged. Schema `trinity-task-queue/v0.1` is untouched.
- The new report schema sits alongside the existing queue schema
  at `schemas/trinity/task_queue_runner_report.schema.json`.
- Pure additive change. Zero `src/`, zero consensus, zero wallet
  / payment / broadcast changes.
