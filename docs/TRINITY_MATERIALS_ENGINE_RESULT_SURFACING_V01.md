# Trinity Materials Engine Result Surfacing v0.1

**Sprint:** 5.33
**Status:** additive · audit-only · zero hash / payment / consensus changes
**Depends on:** Sprint 5.32 (Materials Engine Deterministic Backend) · 5.31 (Classifier) · 5.30 (Reader Metadata) · 5.28 (Queue Dashboard) · 5.24 (Operator Loop Governor Hook) · 5.19 (Operator Loop)

---

## 1. Why it exists

Sprint 5.32 added the first `real_backend` (`local_materials_engine_v01`) and proved it works end-to-end — but manual inspection showed the materials decision (ranking, top material, warnings) was hard to find from the operator's normal viewpoints. The worker result exposes `backend_name` / `backend_kind` / `compute_output_sha256` at the top level, but the actual ranking lives inside the bytes covered by the hash — you have to load the whole result and dig into `compute_output` (via the backend, since the operator only sees the hash).

Sprint 5.33 surfaces a **compact projection** at three audit-friendly layers without touching `compute_output_sha256`, the reward model, the governance gate, or any payment behaviour:

```
  worker_result.json
    └── materials_engine_summary        (NEW — top-level optional field)

  operator_run.json
    ├── materials_engine_summary_count  (NEW — int, default 0)
    └── materials_engine_top_materials  (NEW — array, default [])

  TRINITY_TASK_QUEUE_DASHBOARD_<id>.json
    └── latest_items[*].materials_engine_top_material           (NEW)
                       .materials_engine_summary_count          (NEW)
                       .materials_engine_known_count            (NEW)
                       .materials_engine_unknown_count          (NEW)
                       .materials_engine_warnings_count         (NEW)

  TRINITY_TASK_QUEUE_DASHBOARD_<id>.html
    └── Latest items table  +  "materials_engine" column
        (e.g.  "PrOx  (known 2, unknown 0)")
```

Every new field is additive + optional + has a uniform default. Pre-Sprint-5.33 artifacts on disk still validate against the extended schemas. The classifier, the queue runner, the dashboard CLI, the operator loop CLI — all unchanged from the operator's point of view.

---

## 2. Hash invariant (the critical one)

The materials_engine_summary is built from `backend_result.output_obj` and attached to the **worker result dict** at the TOP level. The hash chain that drives the cross-worker replay contract goes:

```
backend_result.output_obj
      │
      ▼
 canonical_dumps(...) -> output_blob
      │
      ▼
 _sha256_hex(output_blob) -> compute_output_sha256
```

The summary lives **outside** this chain (it's a sibling field in the worker result, NOT inside `output_obj`). Adding or removing it does NOT change `compute_output_sha256`. A dedicated regression test
(`test_compute_output_sha256_unchanged_by_summary`) runs two workers over the same classifier-derived request and asserts the two hashes still match. Sprint 5.12+'s cross-worker replay contract — every worker on the same request must reach the same `compute_output_sha256` — is fully preserved.

---

## 3. Summary contract

`schemas/trinity/materials_engine_summary.schema.json`
($id `trinity-materials-engine-summary/v0.1`, draft-07)

```json
{
  "schema": "trinity-materials-engine-summary/v0.1",
  "backend_name": "local_materials_engine_v01",
  "backend_kind": "real_backend",
  "classification_id": "scl-<16hex>",
  "known_materials": ["CeO2", "PrOx"],
  "unknown_materials": [],
  "resolved_metrics": [
    {"metric": "oxygen_storage_capacity",
     "property": "oxygen_storage_mmol_g",
     "direction": "higher_is_better"},
    ...
  ],
  "top_ranked_material": "PrOx",
  "top_ranked_score": 0.822222,
  "ranking": [
    {"material": "PrOx", "score": 0.822222},
    {"material": "CeO2", "score": 0.711111}
  ],
  "warnings": [...],
  "limitations": [...]
}
```

Hard rules:

- `additionalProperties: false`. `required` covers every field.
- `ranking` is capped at **5 items** (`maxItems: 5`). The full per-metric breakdown stays in the hashed `output_obj`; the summary is for at-a-glance audit, not for replaying scoring.
- `top_ranked_score` and every `ranking[*].score` are in `[0, 1]`.
- `classification_id` is either `scl-<16hex>` or empty string (the backend tolerates missing classification metadata).
- `backend_name` / `backend_kind` are present for fast filtering — a downstream consumer can pick out materials_engine results without parsing the full backend identity block.

The result schema (`useful_compute_result.schema.json`) gains `materials_engine_summary` as an OPTIONAL property mirroring this shape, so the result still validates whether or not the backend produced it.

---

## 4. Operator run roll-up

`useful_compute_operator_run.schema.json` gains two new optional top-level fields, both initialised with safe defaults so the schema is uniform across all runs:

```json
{
  "materials_engine_summary_count": 0,
  "materials_engine_top_materials": []
}
```

After the worker step records its files, the operator loop:

1. Walks `worker_out/TRINITY_USEFUL_COMPUTE_RESULT_*.json`.
2. For each that carries a `materials_engine_summary`, increments the count.
3. Collects `top_ranked_material` values into a deduplicated, sorted list.

The roll-up is read-only on the worker result files; it never modifies them, never invokes the network, never reads the bulky `property_table` or per-metric breakdowns. Malformed worker results are silently skipped — the per-item invariant tests on the worker already enforce the shape.

The Sprint 5.24 operator-loop schema-strict-required test continues to pass because the new fields are in `properties` only, not `required`.

---

## 5. Dashboard per-item surfacing

`task_queue_dashboard.py::_per_item_audit` gains a materials-engine pass over each completed item:

- Reads `operator_run.json`'s roll-up when present (the fast path, post-5.33).
- Falls back to walking `reports/<item_id>/operator_run/worker_out/*.json` directly (covers pre-5.33 operator runs and the dashboard-built-without-operator-loop case).
- Surfaces FIVE fields on each `latest_items[*]` entry:

```json
{
  "materials_engine_summary_count": 2,
  "materials_engine_top_material": "PrOx",
  "materials_engine_known_count":   2,
  "materials_engine_unknown_count": 0,
  "materials_engine_warnings_count": 1
}
```

The HTML `render_html` adds a new `materials_engine` column between the watchdog and operator_run columns. Cell content for an item with the demo data:

```
PrOx (known 2, unknown 0, warn 1)
```

Material name painted purple (`#a78bfa`), counts in the existing meta colour. Items without materials_engine results show `-`. The Sprint 5.28 privacy contracts (no JS, no external assets, no absolute paths, XSS-escaped via `html.escape`) are preserved — the new cell uses the same `_e()` helper as every other text insertion.

---

## 6. Tests added in Sprint 5.33

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_materials_engine_result_surfacing.py` | 13 | Worker result includes summary · summary validates against schema · **compute_output_sha256 unchanged by summary (cross-worker)** · safety_status still manual_review_required · full worker result validates against extended schema · non-materials_engine worker has no summary · operator_run rolls up count + top materials · operator_run defaults to 0/[] when no materials_engine · dashboard surfaces top material per item · HTML displays PrOx · HTML doesn't leak /tmp paths · HTML has no JS or external assets · `_build_materials_engine_summary` returns None for non-materials output + caps ranking at 5 |

Plus three pre-existing schemas extended additively (covered by their existing schema tests):

- `useful_compute_result.schema.json` — `+materials_engine_summary` (optional) + `+scientific_intake` added to `task_type` enum (latent pre-Sprint-5.20 schema gap)
- `useful_compute_operator_run.schema.json` — `+materials_engine_summary_count`, `+materials_engine_top_materials` (optional)
- `task_queue_dashboard.schema.json` — `+materials_engine_*` × 5 (optional)

Total: **13 new tests + 4 schema extensions**.

---

## 7. Non-goals for v0.1

- **No change to `compute_output_sha256` formula.** The summary lives outside `output_obj`. The cross-worker replay contract from Sprint 5.12 is preserved.
- **No change to reward / governance / budget / payment behaviour.** The summary is metadata-for-humans; no reward model reads it, no payment flows from it.
- **No flipping `manual_review_required`.** Real-backend results still require manual review by design — Sprint 5.32 set that; Sprint 5.33 enforces it via a regression test.
- **No new RPC, no new endpoint, no new file format.** Just additive fields on existing JSON artifacts.
- **No bulky data leaked into the summary.** No `property_table`, no per-metric breakdown, no `source_request_sha256` (that's already on the worker result). The summary is intentionally a thin projection.
- **No new dashboard JS.** The materials cell is a static HTML span with inline CSS colour — same constraint as every other cell.

---

## 8. Manual demo

Using the Sprint 5.31 classifier-derived request:

```bash
INTAKE=$(ls /tmp/trinity-5-29-final-intake/out/TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json | head -1)

# (1) Build classifier + request as before
python3 scripts/trinity/scientific_task_classifier.py \
    --intake-json "$INTAKE" \
    --out-json /tmp/trinity-5-33/classification.json \
    --pinned-time 2026-05-17T00:00:00+00:00

python3 scripts/trinity/useful_compute_task_builder.py \
    --from-scientific-classification /tmp/trinity-5-33/classification.json \
    --intake-json "$INTAKE" \
    --deadline 2026-06-30T00:00:00+00:00 \
    --max-reward-stocks 100000 \
    --out-json /tmp/trinity-5-33/request.json

# (2) Run through queue (the auto-router still picks materials_engine)
python3 scripts/trinity/task_queue.py init   --queue-dir /tmp/trinity-5-33-q
python3 scripts/trinity/task_queue.py enqueue --queue-dir /tmp/trinity-5-33-q \
    --request-json /tmp/trinity-5-33/request.json \
    --worker-address-map tests/trinity/fixtures/useful_compute/address_map.json \
    --governor-policy config/trinity_autonomy_governor.example.json \
    --pinned-time 2026-05-17T00:00:00+00:00
python3 scripts/trinity/task_queue.py run-once --queue-dir /tmp/trinity-5-33-q

# (3) Generate the dashboard over the queue
python3 scripts/trinity/task_queue_dashboard.py \
    --queue-dir /tmp/trinity-5-33-q \
    --out-dir   /tmp/trinity-5-33-dashboard \
    --pinned-time 2026-05-17T00:00:00+00:00
```

Expected — at each layer:

- **Worker result**: `materials_engine_summary.top_ranked_material = "PrOx"`, score ~0.82, both workers' `compute_output_sha256` identical.
- **Operator run**: `materials_engine_summary_count = 2`, `materials_engine_top_materials = ["PrOx"]`.
- **Dashboard JSON**: `latest_items[0].materials_engine_top_material = "PrOx"`, `known_count = 2`, `unknown_count = 0`.
- **Dashboard HTML**: Latest items table has a new `materials_engine` column with `PrOx (known 2, unknown 0)` painted purple.

---

## 9. Traceability

- Worker result `$id` unchanged (`trinity-useful-compute-result/v0.4`) — additive change. The `task_type` enum gained `scientific_intake` as a side-effect (latent pre-Sprint-5.20 schema gap that this sprint's tests surfaced).
- Operator run `$id` unchanged (`trinity-useful-compute-operator-run/v0.1`) — additive.
- Dashboard `$id` unchanged (`trinity-task-queue-dashboard/v0.1`) — additive.
- New schema: `trinity-materials-engine-summary/v0.1`.
- Pure scripts + schemas + docs + tests. Zero `src/`, zero consensus, zero wallet / payment / broadcast changes.
