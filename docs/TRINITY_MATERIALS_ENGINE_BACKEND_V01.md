# Trinity Materials Engine Deterministic Backend v0.1

**Sprint:** 5.32
**Status:** local · deterministic · `real_backend` kind · NOT DFT · curated properties table
**Depends on:** Sprint 5.12 (backends registry) · Sprint 5.20 / 5.29 (intake + readers) · Sprint 5.30 (reader metadata in request) · Sprint 5.31 (scientific task classifier)

---

## 1. Why it exists

The Useful Compute worker has had three backend kinds since
Sprint 5.12:

| Kind | What it does |
|------|--------------|
| `placeholder` | deterministic, zero-cost stub. Pipeline-shape only. |
| `sandbox_toy` | stdlib-only deterministic loops. Real cycles, no real meaning. |
| `real_backend` | **reserved**. No backend used this kind before Sprint 5.32. |

Sprint 5.32 lands the **first** `real_backend`:
`local_materials_engine_v01`. It reads the Sprint 5.31 classifier
metadata in the request, looks each candidate material up in a
curated local properties table, scores each requested metric, and
emits a ranked materials comparison.

This is the smallest honest step from *Trinity records science*
to *Trinity produces a materials-specific result*. It is NOT
DFT. It is NOT quantum. The table values are illustrative — they
come from a hand-curated review and are pinned in source so two
workers always agree on the numbers (the cross-worker replay
contract is preserved end-to-end).

---

## 2. Auto-routing — operator CLI stays clean

`useful_compute_worker.py` defaults to `--backend placeholder`.
Sprint 5.32 adds a small auto-router right after argparse:

```python
if (
    backend_name == "placeholder"
    and request.get("source_tool") == "materials_engine"
    and isinstance(
        request["metadata"].get("scientific_task_classification"),
        dict,
    )
):
    effective_backend_name = "local_materials_engine_v01"
```

When the operator runs the queue / operator_loop with the default
backend AND the request was produced by the Sprint 5.31
classifier with materials in scope, the materials_engine fires
automatically. No CLI flag change needed in `task_queue.py`,
`useful_compute_operator_loop.py`, or `task_queue_dashboard.py`.

The operator can **opt out** by passing
`--backend placeholder_scientific_intake` explicitly — that
forces the hash-only stub for those requests.

A regression test
(`test_operator_can_opt_out_to_placeholder`) locks this contract.

---

## 3. Result contract

`schemas/trinity/materials_engine_result.schema.json`
($id `trinity-materials-engine-result/v0.1`, draft-07)

```json
{
  "schema": "trinity-materials-engine-result/v0.1",
  "backend":  "materials_engine",
  "backend_version": "v0.1",
  "mode": "local-dry-run",
  "task_kind": "comparison",
  "materials_compared": ["CeO2", "PrOx"],
  "metrics_requested":  ["oxygen_storage_capacity", "temperature_c", ...],
  "known_materials":   ["CeO2", "PrOx"],
  "unknown_materials": [],
  "resolved_metrics": [
    {"metric": "oxygen_storage_capacity",
     "property": "oxygen_storage_mmol_g",
     "direction": "higher_is_better"},
    {"metric": "temperature_c",
     "property": "optimal_temperature_c",
     "direction": "lower_is_better"}
  ],
  "property_table": {
    "CeO2":  {"oxygen_storage_mmol_g": 1.7, "optimal_temperature_c": 500, ...},
    "PrOx":  {"oxygen_storage_mmol_g": 2.3, "optimal_temperature_c": 450, ...}
  },
  "ranking": [
    {"material": "PrOx", "score": 0.83,
     "metric_breakdown": [{"metric":"...", "property":"...", "value":2.3, "normalised_score":0.77, "direction":"higher_is_better"}, ...]},
    {"material": "CeO2", "score": 0.65, "metric_breakdown": [...]}
  ],
  "score_explanation": "score per material = mean over resolved metrics of (value normalised to [0,1] within property bounds, inverted for lower_is_better directions). Property bounds and metric→property mapping are pinned in local_materials_engine_v01.",
  "limitations": [
    "v0.1 uses a curated local properties table; values are illustrative, NOT measured data, NOT publishable.",
    "no DFT, no quantum, no real simulation, no network.",
    "metric → property mapping is hand-curated; unknown metric labels are dropped from the scoring with a warning."
  ],
  "warnings": [],
  "source_request_sha256": "<64hex>",
  "classification_id":     "scl-<16hex>",
  "marker_hex":            "<16hex>"
}
```

Hard rules in the schema:

- `backend`, `backend_version`, `mode`, `schema` are `const`-locked
  to the v0.1 strings.
- `task_kind` enum matches the classifier's four kinds.
- `direction` enum is exactly `{higher_is_better, lower_is_better}`.
- `score` and every `normalised_score` is in `[0, 1]`.
- `source_request_sha256` is 64-hex.
- `classification_id` matches `^scl-[0-9a-f]{16}$` OR is empty
  string (the backend tolerates missing classification metadata).
- The whole object has `additionalProperties: false`.

---

## 4. The curated properties table

`_MATERIALS_PROPERTIES_TABLE_V01` in
`scripts/trinity/useful_compute_backends.py`:

| Material | OSC (mmol/g) | T_opt (°C) | redox | stability | conductivity | surface (m²/g) |
|----------|--------------|------------|-------|-----------|--------------|----------------|
| CeO2     | 1.7          | 500        | 0.90  | 0.85      | 0.65         | 120 |
| PrOx     | 2.3          | 450        | 0.95  | 0.75      | 0.55         | 90  |
| Sm2O3    | 0.9          | 600        | 0.60  | 0.90      | 0.40         | 60  |
| Y2O3     | 0.7          | 700        | 0.50  | 0.95      | 0.30         | 40  |
| ZrO2     | 0.5          | 800        | 0.40  | 0.98      | 0.25         | 50  |
| TiO2     | 0.3          | 600        | 0.30  | 0.95      | 0.35         | 80  |

Values are **illustrative**. They are pinned in source so two
workers always read the same numbers; they are NOT measured
laboratory data and they should NOT be used to make scientific
claims. The disclaimer + limitations in the result make this
explicit.

A static safety test ensures every property used by the table
also has an entry in `_PROPERTY_BOUNDS` (otherwise the scorer
silently scores 0).

---

## 5. Scoring algorithm v0.1

For each known material × each resolved metric:

1. Look up the property value from the curated table.
2. Normalise to `[0, 1]` using `_PROPERTY_BOUNDS`:
   `raw = (value − lo) / (hi − lo)`, clamped to `[0, 1]`.
3. If the direction is `lower_is_better`, invert:
   `normalised = 1 − raw`.

Material score = arithmetic mean of all metric `normalised_score`s.
Ranking sorts descending by score, then alphabetically by name
for tiebreaks. Deterministic for stable input.

Worked example for "Compare ceria and praseodymia for OSC + temperature":

- OSC: PrOx 2.3 → 0.77, CeO2 1.7 → 0.57 (higher_is_better)
- temperature: PrOx 450 → 0.75, CeO2 500 → 0.67 (lower_is_better, inverted)
- PrOx final = (0.77 + 0.75) / 2 = **0.76**
- CeO2 final = (0.57 + 0.67) / 2 = **0.62**
- Ranking: PrOx → CeO2

---

## 6. Tests added in Sprint 5.32

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_materials_engine_backend.py` | 14 | direct handler CeO2 vs PrOx ranking deterministic · same-inputs determinism · unknown materials warned not crashed · fallback when no recognised metrics · temperature inversion (lower_is_better) · zero-known-materials handled · source_request_sha256 is 64-hex and changes with request · backend registered with correct kind / version / task_types / experimental=False · disclaimer says NOT DFT and curated · worker auto-routes classifier-derived materials_engine request · two workers produce same compute_output_sha256 · operator opt-out to placeholder works · non-materials_engine request stays on placeholder · backend output validates against result schema |
| `tests/trinity/test_materials_engine_backend_schema.py` | 13 | schema valid draft-07 · v0.1 $id · 4 const locks · task_kind enum · direction enum · score range · normalised_score range · source_request_sha pattern · marker_hex pattern · classification_id pattern-or-empty · additionalProperties locked · required set complete |
| `tests/trinity/test_materials_engine_backend_safety.py` | 11 | backends file has no NEW network / shell / subprocess / eval / LLM-client tokens after 5.32 · worker file ditto · `_materials_engine_v01` handler present · properties table pinned in source with all 6 materials · `_METRIC_TO_PROPERTY` mapping has the classifier-emitted labels · every property in the table appears in `_PROPERTY_BOUNDS` · disclaimer says NOT DFT · worker auto-router wired · task_queue does NOT pass `local_materials_engine_v01` directly (so the operator opt-out path stays intact) |
| `tests/trinity/test_useful_compute_backends.py` | 1 edited | `test_no_backend_uses_real_backend_kind_in_v01` was the v0.1 reservation guard. Renamed to `test_only_materials_engine_uses_real_backend_kind_in_v01` and switched to an allowlist of one (`local_materials_engine_v01`) so future real backends still need a sprint that audits the contract. |

Total: **38 new tests + 1 edited existing test**.

---

## 7. Non-goals for v0.1

- **No DFT.** Disclaimer says so in three places. Tests assert
  "NOT DFT" appears in the disclaimer.
- **No quantum, no real simulation.** The "compute" is a table
  lookup + arithmetic.
- **No network.** Static safety test forbids every stdlib
  network primitive.
- **No LLM.** Static safety test forbids `anthropic`, `openai`,
  `langchain`, `transformers`, `llama_cpp` in the backend AND
  the worker source.
- **No subprocess from the backend.** The backend handler is
  pure Python dict-of-dict arithmetic.
- **No new task_type or source_tool enum values.** Auto-routing
  uses the existing `source_tool=materials_engine` /
  `task_type=scientific_intake` combination that Sprint 5.31
  already produced.
- **No external properties database.** Curated table lives in
  source so a reviewer can audit at a glance. v0.2 may move it
  to `data/trinity/materials_engine/*.json` with a sha256 lock.
- **No measured-data claims.** The result's `limitations` field
  is the official statement: values are illustrative, NOT
  measured, NOT publishable.

---

## 8. Manual demo

Using the Sprint 5.31 classifier output as input:

```bash
INTAKE=$(ls /tmp/trinity-5-29-final-intake/out/TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json | head -1)
mkdir -p /tmp/trinity-5-32-materials

python3 scripts/trinity/scientific_task_classifier.py \
    --intake-json "$INTAKE" \
    --out-json /tmp/trinity-5-32-materials/classification.json \
    --pinned-time 2026-05-17T00:00:00+00:00

python3 scripts/trinity/useful_compute_task_builder.py \
    --from-scientific-classification /tmp/trinity-5-32-materials/classification.json \
    --intake-json "$INTAKE" \
    --deadline 2026-06-30T00:00:00+00:00 \
    --max-reward-stocks 100000 \
    --out-json /tmp/trinity-5-32-materials/request.json

rm -rf /tmp/trinity-5-32-queue
python3 scripts/trinity/task_queue.py init --queue-dir /tmp/trinity-5-32-queue
python3 scripts/trinity/task_queue.py enqueue --queue-dir /tmp/trinity-5-32-queue \
    --request-json /tmp/trinity-5-32-materials/request.json \
    --worker-address-map tests/trinity/fixtures/useful_compute/address_map.json \
    --governor-policy config/trinity_autonomy_governor.example.json \
    --pinned-time 2026-05-17T00:00:00+00:00
python3 scripts/trinity/task_queue.py run-once --queue-dir /tmp/trinity-5-32-queue
```

Expected: queue completes with `governor_decisions_count=7` and
`watchdog_safety_status=ok`. Inspecting the operator_loop's
`reports/<id>/operator_run/` will show two
`TRINITY_USEFUL_COMPUTE_RESULT_*.json` files (worker-A and
worker-B), each with:

- `backend_name = local_materials_engine_v01`
- `backend_kind = real_backend`
- identical `compute_output_sha256`

The replay validator (already in the pipeline) confirms the
cross-worker contract holds for the new backend.

---

## 9. Traceability

- New schema: `trinity-materials-engine-result/v0.1` (this sprint).
- Backend registered in `_BACKENDS` of
  `scripts/trinity/useful_compute_backends.py` with
  `kind=real_backend`, `experimental=False`, `task_types=[scientific_intake]`.
- Worker auto-router added in `useful_compute_worker.py`; no
  change to operator_loop / queue / dashboard / governor /
  watchdog.
- The classifier (Sprint 5.31) is unchanged; its
  `proposed_source_tool=materials_engine` decision is what
  triggers the auto-router.
- Replay validator + governance gate + reward budget +
  payment_proposal + payment_draft are all hash-based; the new
  backend's deterministic output flows through them unchanged.
- Pure scripts + schemas + docs + tests. Zero `src/`, zero
  consensus, zero wallet / payment / broadcast changes.
