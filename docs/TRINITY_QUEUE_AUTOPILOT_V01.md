# Trinity Task Queue Autopilot v0.1

**Sprint:** 5.38 (Part B of combined sprint 5.37-5.39)
**Status:** additive · audit-only · zero hash / payment / consensus changes
**Depends on:** Sprint 5.27 (Task Queue Runner / run-batch) · 5.28 (Queue Dashboard) · 5.26 (Task Queue)

---

## 1. Why it exists

Sprint 5.27 added `task_queue.py run-batch` (bounded driver over
`run_once`). Sprint 5.28 added `task_queue_dashboard.py` (read-only
snapshot). Until now the operator had to alternate
`run-batch → dashboard → run-batch → dashboard` by hand to process
a workday's worth of items.

Sprint 5.38 lets the operator hand that hand-cranking to a single
bounded process. The autopilot is not a daemon. It is a one-shot
command with a HARD CAP of 24 batches per invocation.

---

## 2. CLI

```
python3 scripts/trinity/task_queue_autopilot.py run-autopilot \
    --queue-dir         /var/lib/trinity/queues/main \
    --max-batches        4 \
    --max-items-per-batch 8 \
    --pinned-time        2026-05-18T00:00:00+00:00 \
    --dashboard-out-dir  /var/lib/trinity/dashboards \
    [--stop-on-failure]
```

- `--max-batches` is required and capped at **24**. Anything
  greater is refused at argv parse time (script exits with rc=2).
- `--max-items-per-batch` is capped at **50** (same as
  `task_queue.run_batch`).
- `--stop-on-failure` halts at the first batch whose
  `safety_status` is `"failed"`.

---

## 3. What it does

```
for batch_index in 0 .. (max_batches - 1):
    batch_report = task_queue.run_batch(
        queue_dir, max_items=max_items_per_batch,
        pinned_time=pinned_time,
        stop_on_failure=stop_on_failure,
    )
    dashboard = task_queue_dashboard.build_dashboard(
        queue_dir, pinned_time,
    )
    write dashboard JSON + HTML to --dashboard-out-dir

    if stop_on_failure and batch_report.safety_status == "failed":
        stop ("stop_on_failure")
    if batch_report.attempted_count == 0:
        stop ("queue_empty")
```

The autopilot calls `task_queue.run_batch` and
`task_queue_dashboard.build_dashboard` IN-PROCESS — no subprocess,
no shell, no network. The `run_batch` function re-asserts the
local-dry-run mode lock on entry, so the autopilot inherits that
guarantee.

---

## 4. Output

A schema-validated report at:

```
<queue-dir>/reports/_autopilot/
    TRINITY_TASK_QUEUE_AUTOPILOT_REPORT_<autopilot_id>.json
```

`autopilot_id` is `tap-<16hex>`. The schema is
`trinity-task-queue-autopilot-report/v0.1` and contains:

- `batches_attempted`, `batches_succeeded`, `batches_failed`
- `items_completed`, `items_failed`
- `final_queue_counts` (pending / running / completed / failed / total)
- `per_batch[]` (batch_index, batch_id, attempted_count,
  completed_count, failed_count, safety_status)
- `dashboard_paths[]` and `latest_dashboard_basename`
- `stopped_reason` enum: `max_batches_reached` / `queue_empty` /
  `stop_on_failure` / `task_queue_error`
- `safety_status` enum: `ok` / `warning` / `failed`
- `warnings[]`
- `safety_flags` (seven const-true flags):
    - `no_wallet`, `no_private_key`, `no_signing`,
    - `no_broadcast`, `no_autonomous_payment`,
    - `no_network`, `local_dry_run_only`

---

## 5. Safety contract

Static tests assert:

- The script contains no network primitive (`requests`, `urllib`,
  `httpx`, `aiohttp`, `socket.socket`, `http.client`).
- The script contains no `subprocess`, no `os.system`, no
  `os.popen`, no `shell=True`, no `eval`, no `exec`.
- The script contains no `while True` — the bound is explicit.
- The script imports ONLY `task_queue` and
  `task_queue_dashboard` from the sibling tree. Any other
  Trinity import is rejected.
- `AUTOPILOT_MAX_BATCHES_CAP` is hard-coded to 24 in source AND
  the schema's `max_batches.maximum = 24`.
- All seven safety flags are const-true at both the script and
  the schema level.

---

## 6. Non-goals for v0.1

- The autopilot is **NOT** a daemon. It exits when its bounded
  budget is consumed.
- It does NOT change `compute_output_sha256`, the reward model,
  governance, budget, or payment behaviour.
- It does NOT introduce a new file format (operator_run.json,
  worker result JSONs, batch reports, dashboard JSON+HTML are
  all reused as-is).
- It does NOT flip `manual_review_required` for any backend.
