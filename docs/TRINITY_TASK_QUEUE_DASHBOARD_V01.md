# Trinity Task Queue Dashboard v0.1

**Sprint:** 5.28
**Status:** read-only · static HTML · no network · no subprocess · no wallet / no broadcast
**Depends on:** Sprint 5.23 (Governor) · Sprint 5.24 (Operator Hook) · Sprint 5.25 (Watchdog) · Sprint 5.26 (Task Queue) · Sprint 5.27 (Task Queue Runner)

---

## 1. Why it exists

Sprints 5.23 – 5.27 built a working autonomy loop:

```
enqueue → run-batch → operator_loop+governor → watchdog → completed/failed
```

Each step writes JSON audit artifacts. The trail is complete — and
totally invisible unless a human types `cat` against the right
path. The Dashboard is the missing **read-only pane of glass**: it
walks every queue artifact, summarises the state into a
deterministic JSON, and renders a static HTML page suitable for
serving from a private file path or piping into a static-site
viewer.

This sprint adds **no new autonomy**. It only makes the existing
autonomy observable.

```
queue.json + items + reports     ─┐
                                  │
   scripts/trinity/                ├─→  TRINITY_TASK_QUEUE_DASHBOARD_<id>.json
   task_queue_dashboard.py        ─┘                                  + .html
        (read-only)
```

---

## 2. CLI surface

```
python3 scripts/trinity/task_queue_dashboard.py \
    --queue-dir DIR \
    --out-dir DIR \
    [--pinned-time ISO]      # default: now (operators should pin)
    [--latest-limit N]       # default: 25; caps latest_items + latest_batches
```

Exit code: 0 on success, 2 when the queue dir is missing or
queue.json is unreadable. The dashboard JSON's `safety_status` is
the source of truth on whether action is needed.

---

## 3. Dashboard JSON contract

`schemas/trinity/task_queue_dashboard.schema.json`
($id `trinity-task-queue-dashboard/v0.1`, draft-07)

```json
{
  "schema": "trinity-task-queue-dashboard/v0.1",
  "dashboard_id": "dsh-<16hex>",
  "pinned_time": "2026-05-17T00:00:00+00:00",
  "queue_dir_basename": "trinity-5-28-demo",
  "queue_id": "tq-<16hex>",
  "counts": {
    "pending": 0,
    "running": 0,
    "completed": 2,
    "failed":    0,
    "batches":   1
  },
  "latest_items": [
    {
      "queue_item_id": "qit-<16hex>",
      "status": "completed",
      "updated_at": "2026-05-17T00:00:00+00:00",
      "attempt_count": 1,
      "operator_run_path_basename": "operator_run.json",
      "watchdog_report_path_basename": "TRINITY_GOVERNOR_WATCHDOG_REPORT_<id>.json",
      "governor_decisions_count": 7,
      "watchdog_safety_status": "ok"
    }
  ],
  "latest_batches": [
    {
      "batch_id": "tqr-<16hex>",
      "attempted_count": 2,
      "completed_count": 2,
      "failed_count": 0,
      "safety_status": "ok"
    }
  ],
  "warnings": [],
  "safety_status": "ok"
}
```

Hard rules in the schema:

- `dashboard_id` matches `^dsh-[0-9a-f]{16}$`.
- `queue_id` matches `^tq-[0-9a-f]{16}$`, `queue_item_id`
  `^qit-[0-9a-f]{16}$`, `batch_id` `^tqr-[0-9a-f]{16}$`.
- `safety_status` (dashboard-wide) enum `{ok, warning, failed}`.
- Per-item `watchdog_safety_status` enum
  `{ok, warning, stale, critical}` or null.
- Per-batch `safety_status` enum `{ok, warning, failed}`.
- All path fields end in `_basename`. The dashboard NEVER
  persists absolute paths — only the basename of the queue dir
  and the basenames of the audit files.

---

## 4. `safety_status` rollup

Dashboard-wide precedence (strict):

| status | trigger |
|--------|---------|
| `failed` | any per-item `watchdog_safety_status == "critical"`, OR any per-batch `safety_status == "failed"` |
| `warning` | any queue item with `status == "failed"`, OR any per-batch `safety_status == "warning"`, OR any per-item `watchdog_safety_status in {warning, stale}`, OR any malformed input |
| `ok` | none of the above |

The "any malformed input" bucket covers:

- queue.json missing or wrong schema (raises, never produces a
  dashboard);
- per-item file missing on disk but present in the index;
- per-item file present on disk but not in the index;
- per-item / per-batch / watchdog file with invalid JSON or wrong
  schema string.

---

## 5. Static HTML view

The dashboard also writes
`TRINITY_TASK_QUEUE_DASHBOARD_<id>.html` next to the JSON. The
HTML is deliberately conservative:

- **No JavaScript.** Pure HTML + a tiny inline `<style>` block.
- **No external assets.** Zero `https://`, zero `http://`, zero
  CDN, zero remote fonts.
- **No clickable links** that could leak referrer information.
- **All text escaped** via `html.escape(quote=True)`. A test
  poisons the dashboard's text inputs with `<script>alert(...)`
  and `<img onerror=...>` and asserts the rendered HTML contains
  the escaped form (`&lt;script&gt;…`) but never the raw tag.
- **No absolute paths.** A test creates a queue at a path with a
  recognisable basename and asserts the full absolute prefix
  never appears in the HTML.
- **`<meta name="robots" content="noindex,nofollow">`.** The
  dashboard is private operator content; if it ever lands on a
  webserver by accident, search engines stay out.

Layout:

1. Heading + queue basename + queue_id + dashboard_id.
2. Single-line dashboard-wide `safety_status` with color coding.
3. Counts table (5 cells).
4. Latest items table — id · status · updated_at · attempts ·
   governor_decisions · watchdog status · operator_run basename ·
   watchdog_report basename.
5. Latest batches table — id · attempted · completed · failed ·
   safety_status.
6. Warnings list (or "none.").

---

## 6. Tests added in Sprint 5.28

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_task_queue_dashboard.py` | 19 | empty queue rendering · 2 completed items + 1 batch counts · latest_items have `governor_decisions_count` + watchdog status · latest_batches present · failed item ⇒ warning rollup · halt-file blocked item ⇒ at least warning · malformed item ⇒ warning + warning list · unreferenced on-disk file ⇒ warning · missing queue dir refused · empty dir (no queue.json) refused · HTML escapes injected `<script>` AND `<img onerror>` via two independent insertion paths · HTML never contains absolute queue path · HTML has no JavaScript or external assets · HTML carries `noindex,nofollow` meta · `dashboard_id` deterministic for same inputs · `--latest-limit` caps arrays but not counts · CLI writes both JSON and HTML with matching stem · CLI rc=2 on missing queue · sanity schema validation |
| `tests/trinity/test_task_queue_dashboard_schema.py` | 15 | Schema is valid draft-07 · v0.1 $id · `safety_status` enum · counts required keys · `dashboard_id` / `queue_id` / item id / batch id patterns · item status enum · per-item watchdog enum · per-batch safety_status enum · end-to-end validation in 4 branches (empty, ok, warning, full) |
| `tests/trinity/test_task_queue_dashboard_safety.py` | 10 | Source has no wallet/sign/broadcast/payment/shell/subprocess/network/mutating-fs tokens · declares v0.1 schema constant · uses `html.escape` and `_e()` helper · does NOT import sibling Trinity modules · HTML carries `noindex,nofollow` meta · never writes into the queue dir · cross-check Governor + Watchdog + Task Queue/Runner safety unchanged |

Total: **44 new tests**.

---

## 7. Non-goals for v0.1

- **No live updates.** The dashboard is a snapshot. Re-run
  `task_queue_dashboard.py` to refresh it.
- **No history / time series.** Each invocation writes a fresh
  pair of files; no aggregation across runs.
- **No drill-down navigation.** The HTML is a single page; the
  basenames in the tables let a human jump to the right file on
  disk, but there are no in-page links.
- **No external dispatch.** The dashboard is local-only by
  design; the Watchdog (Sprint 5.25) is the layer reserved for
  any future external visibility.
- **No queue mutation.** Read-only on the queue dir.
- **No subprocess.** All inputs are JSON files; no need to invoke
  the operator loop, watchdog, or runner.
- **No wallet / signing / broadcast.** Same safety surface as
  every Trinity component since Sprint 5.23.

---

## 8. Manual demo

```bash
rm -rf /tmp/trinity-5-28-dashboard
python3 scripts/trinity/task_queue_dashboard.py \
    --queue-dir /tmp/trinity-5-27-posttag \
    --out-dir /tmp/trinity-5-28-dashboard \
    --pinned-time 2026-05-17T00:00:00+00:00

ls /tmp/trinity-5-28-dashboard/
# TRINITY_TASK_QUEUE_DASHBOARD_<id>.json
# TRINITY_TASK_QUEUE_DASHBOARD_<id>.html
```

Expected output line:

```
[task_queue_dashboard] dashboard_id=dsh-<…> safety_status=ok
    pending=0 running=0 completed=2 failed=0 batches=1
    json=… html=…
```

Open the HTML file in a browser to see the same data rendered.

---

## 9. Traceability

- Reads queue layout written by Sprint 5.26 (`task_queue.py init`
  / `enqueue` / `run-once`) and Sprint 5.27 (`run-batch`).
- Pulls `governor_decisions_count` from the per-item
  `operator_run.json` (Sprint 5.24 schema) and
  `watchdog_safety_status` from the per-item
  `TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json` (Sprint 5.25 schema).
- The Watchdog itself is unchanged; the Dashboard is a passive
  reader of its reports.
- Pure scripts + schemas + docs + tests. Zero `src/`, zero
  consensus, zero wallet / payment / broadcast changes.
