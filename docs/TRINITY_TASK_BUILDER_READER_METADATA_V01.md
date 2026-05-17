# Trinity Task Builder Reader Metadata v0.1

**Sprint:** 5.30
**Status:** additive · deterministic · no extracted-text leak · no absolute paths
**Depends on:** Sprint 5.20 (Intake) · Sprint 5.21 (Task Builder `--from-scientific-intake`) · Sprint 5.29 (Scientific Intake Readers)

---

## 1. Why it exists

Sprint 5.29 added pluggable readers to the scientific intake: every
document now carries a `reader_kind`, a `reader_status`, an
`extracted_text_sha256`, a `structured_summary`, and per-doc
warnings. That metadata lives in the intake artifact.

Sprint 5.21 introduced `--from-scientific-intake` on the task
builder, which writes `metadata.scientific_intake` into the
Useful Compute request. Six fields: `intake_id`,
`combined_context_sha256`, `prompt_sha256`, `documents_count`,
`intake_task_kind`, `intake_artifact_sha256`. Useful, but
**flat**: a worker (or queue, or dashboard) reading the request
had no idea whether the intake included LaTeX or CSV, whether a
PDF gracefully degraded, or whether any reader emitted a warning.

Sprint 5.30 bridges that gap. A new
`metadata.scientific_reader_manifest` field carries the reader
breakdown into the request, projected down to the subset
downstream consumers actually need:

- counts by `reader_kind` and `reader_status`
- per-document: basename, raw sha256, reader_kind,
  reader_status, **extracted_text_sha256** (the hash, not the
  text), `structured_summary`, per-doc warnings
- top-level `intake_warnings` lifted from the intake

The raw extracted text NEVER reaches the request. Operator-
private absolute paths NEVER reach the request. Only basenames,
hashes, summaries and short warning strings.

---

## 2. Where the manifest lands

```
request.json
├── source_tool:  trinity_scientific_prompt_intake
├── task_type:    scientific_intake
├── input_bundle_sha256: <combined_context_sha256 from intake>
├── metadata:
│   ├── scientific_intake:           (Sprint 5.21, unchanged)
│   │   ├── intake_id
│   │   ├── combined_context_sha256
│   │   ├── prompt_sha256
│   │   ├── documents_count
│   │   ├── intake_task_kind
│   │   └── intake_artifact_sha256
│   └── scientific_reader_manifest:  (Sprint 5.30, NEW)
│       ├── documents_count
│       ├── combined_context_sha256  (mirrored for cross-check)
│       ├── reader_kind_counts:      {text: 2, csv: 1, latex: 1, pdf: 1}
│       ├── reader_status_counts:    {ok: 4, unsupported_missing_dependency: 1}
│       ├── documents: [
│       │   {
│       │     path_basename, sha256,
│       │     reader_kind, reader_status,
│       │     extracted_text_sha256,
│       │     structured_summary, warnings
│       │   }, …
│       │ ]
│       └── intake_warnings: [
│           "sample.pdf: no PDF backend available …"
│         ]
└── …
```

The manifest field is **optional** in the request schema. A
pre-Sprint-5.30 request without it still validates, so old
artifacts on disk aren't invalidated.

---

## 3. Reader-sensitivity already flows through to the worker

Sprint 5.29 changed the intake's `combined_context_sha256`
formula to mix in `extracted_text_sha256` and `reader_status`
per document. Sprint 5.21's task builder already uses
`combined_context_sha256` as the request's `input_bundle_sha256`.
The worker's `compute_output_sha256` depends on `input_sha`
through its deterministic seed.

So the chain is unchanged by Sprint 5.30 — **but it now works
on real readers**:

```
extracted_text_sha256 (Sprint 5.29)
        ↓
combined_context_sha256 (Sprint 5.29 mix-in)
        ↓
input_bundle_sha256 (Sprint 5.21 bridge)
        ↓
compute_output_sha256 (Sprint 5.12+ worker seed)
```

A regression test
(`test_worker_compute_output_changes_when_extracted_text_changes`)
mutates a document body between two runs and asserts the worker's
`compute_output_sha256` differs. That's the proof Sprint 5.30
keeps the chain intact end-to-end.

The Sprint 5.30 manifest itself is **not** mixed into
`compute_output_sha256`. It's an audit-and-display surface; the
hash that drives consensus is `input_bundle_sha256`, which
already encodes the same information.

---

## 4. Privacy invariants

Tests poison a document with a sentinel string and assert:

| What | Appears in request? |
|------|---------------------|
| document body (raw bytes) | NO |
| `text_preview` (Sprint 5.20 body-preview) | NO |
| `extracted_text_preview` (Sprint 5.29 reader-preview) | NO |
| absolute filesystem path | NO |
| document basename | YES (deliberate, public identifier) |
| sha256 of raw bytes | YES (audit identifier) |
| sha256 of extracted text | YES (sensitivity to reader output) |
| reader_kind, reader_status, structured_summary | YES |

The existing 5.21 test
`test_request_does_not_copy_document_content` was tightened to
match: it still rejects the body and any preview, and now
explicitly allows `path_basename` (which is deliberately
exposed by the Sprint 5.30 manifest).

---

## 5. Tests added in Sprint 5.30

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_task_builder_reader_metadata.py` | 13 | Manifest present and well-formed · `reader_kind_counts` match the 5 documents · `reader_status_counts` reflect PDF missing-dep on hosts without pypdf · per-doc required fields all populated · intake warnings carried through · sentinel body never appears + `text_preview` / `extracted_text_preview` never appear · basenames present, absolute paths absent · `combined_context_sha256` in request matches intake (twice — under `scientific_intake` and `scientific_reader_manifest`) · `input_bundle_sha256` equals the combined hash · worker `compute_output_sha256` changes when extracted_text changes (the Sprint 5.29 chain end-to-end) · new request validates against schema · legacy pre-5.30 request without manifest still validates · per-doc record defaults for pre-5.29 intakes · per-doc record preserves Sprint 5.29 fields and drops `extracted_text_preview` |
| `tests/trinity/test_task_builder_from_scientific_intake.py` (edited) | 1 changed | The 5.21 anti-leak test was narrowed: still bans body + `text_preview` + `extracted_text_preview`, no longer bans `path_basename` (deliberately exposed) |

Total: **13 new tests + 1 edited existing test**.

---

## 6. Schema additions

`schemas/trinity/useful_compute_request.schema.json` gains a new
optional property under `metadata`:

```json
"scientific_reader_manifest": {
  "type": "object",
  "additionalProperties": false,
  "required": [
    "documents_count", "combined_context_sha256",
    "reader_kind_counts", "reader_status_counts",
    "documents", "intake_warnings"
  ],
  "properties": {
    "documents_count":         { "type": "integer", "minimum": 0 },
    "combined_context_sha256": { "type": "string", "pattern": "^[0-9a-f]{64}$" },
    "reader_kind_counts":   { "type": "object", "additionalProperties": {"type": "integer", "minimum": 0} },
    "reader_status_counts": { "type": "object", "additionalProperties": {"type": "integer", "minimum": 0} },
    "documents": { "type": "array", "items": { "type": "object", "required": [...], "additionalProperties": false, "properties": { ... } } },
    "intake_warnings": { "type": "array", "items": { "type": "string", "minLength": 1, "maxLength": 512 } }
  }
}
```

Per-document item is locked: `path_basename` (string),
`sha256` (64-hex), `reader_kind` enum, `reader_status` enum,
`extracted_text_sha256` (64-hex), `structured_summary` (open
object), `warnings` (array of short strings).

The request schema's `$id` stays `trinity-useful-compute-request/v0.1`
— this is an additive change, not a v0.2 bump.

---

## 7. Non-goals for v0.1

- **No extracted text in the request.** Only its sha256.
  Operators who need to read the text go to the per-item
  operator_run.json or the original intake artifact.
- **No `extracted_text_preview` in the request.** The preview
  exists in the intake artifact; carrying it across would
  defeat the point of bounded request sizes.
- **No new worker logic.** The worker continues to derive
  `compute_output_sha256` from `input_bundle_sha256`; that
  hash already encodes reader sensitivity courtesy of
  Sprint 5.29.
- **No schema version bump.** Additive. Pre-5.30 requests
  validate unchanged.
- **No source-tool expansion.** `source_tool` enum is
  unchanged; only `trinity_scientific_prompt_intake` produces
  a manifest. Other source tools (materials_engine,
  geaspirit, trinity_orchestrator) keep their existing
  request shape with no manifest field.
- **No `--show-manifest` CLI flag.** The manifest is in the
  request JSON; the operator already has `cat` and `jq`.

---

## 8. Manual demo

Using the Sprint 5.29 final intake at
`/tmp/trinity-5-29-final-intake/out/`:

```bash
INTAKE=$(ls /tmp/trinity-5-29-final-intake/out/TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json | head -1)

python3 scripts/trinity/useful_compute_task_builder.py \
    --from-scientific-intake "$INTAKE" \
    --intake-task-kind comparison \
    --intake-output-schema trinity-useful-compute-result/v0.4 \
    --difficulty-class low \
    --deadline 2026-06-30T00:00:00+00:00 \
    --max-reward-stocks 100000 \
    --out-json /tmp/trinity-5-30-request.json

python3 - <<PY
import json
req = json.load(open("/tmp/trinity-5-30-request.json"))
rm = req["metadata"]["scientific_reader_manifest"]
print("source_tool:", req["source_tool"])
print("task_type:", req["task_type"])
print("combined_context_sha256:", rm["combined_context_sha256"])
print("reader_kind_counts:", rm["reader_kind_counts"])
print("reader_status_counts:", rm["reader_status_counts"])
print("documents:", len(rm["documents"]))
raw = json.dumps(req)
assert "extracted_text_preview" not in raw
assert "text_preview" not in raw
print("no extracted-text preview in request: OK")
PY
```

The request is also drop-in compatible with the
`useful_compute_operator_loop.py --request-json` flow and with
the `task_queue.py enqueue` / `run-once` / `run-batch` flow —
both continue to complete with the augmented request.

---

## 9. Traceability

- Schema `$id` unchanged
  (`trinity-useful-compute-request/v0.1`) — additive change.
- The Sprint 5.21 metadata block (`scientific_intake`) is
  preserved verbatim. Sprint 5.30 adds a sibling field.
- The worker's pre-Sprint-5.30 validation surface for
  `metadata.scientific_intake` is untouched. The worker silently
  ignores `metadata.scientific_reader_manifest` (the schema
  validates it; the worker doesn't depend on it).
- Pure scripts + schemas + docs + tests. Zero `src/`, zero
  consensus, zero wallet / payment / broadcast changes.
