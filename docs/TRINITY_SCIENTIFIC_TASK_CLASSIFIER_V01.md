# Trinity Scientific Task Classifier v0.1

**Sprint:** 5.31
**Status:** local-only · deterministic · no LLM · no network · no wallet / no broadcast · heuristic
**Depends on:** Sprint 5.20 (Intake) · Sprint 5.21 (`--from-scientific-intake`) · Sprint 5.29 (Readers) · Sprint 5.30 (Reader Metadata in Request)

---

## 1. Why it exists

Trinity now reads documents (5.29) and carries reader metadata
into Useful Compute requests (5.30). But the operator still has
to TELL the task builder what kind of scientific question this
is — `--intake-task-kind comparison`, `--intake-output-schema …`,
`--difficulty-class …`. That's a typing burden, and it's where a
typo can quietly mislabel a benchmark as an extraction.

Sprint 5.31 inserts a **classifier layer** between intake and
task builder. It reads the intake's bounded previews, runs a
small set of substring + regex heuristics, and proposes a
structured task plan:

```
intake.json
    │
    ▼
scientific_task_classifier.py
    │   (regex + substring heuristics; no LLM; no network)
    ▼
classification.json
    │
    ▼
task_builder.py --from-scientific-classification + --intake-json
    │   (cross-checks the pair, stitches the request)
    ▼
request.json
    │   (drop-in with operator_loop + task_queue + worker)
    ▼
   queue runs the request
```

The classifier is deliberately **stupid**: substring + regex
only. A model-driven version would belong in a separate sprint
with its own audit trail. This v0.1 is the floor: deterministic,
auditable, reviewable by reading the heuristic tables.

---

## 2. CLI surface

```
python3 scripts/trinity/scientific_task_classifier.py \
    --intake-json /path/to/TRINITY_SCIENTIFIC_PROMPT_INTAKE_<id>.json \
    --out-json /path/to/classification.json \
    [--pinned-time ISO]
```

Exit 0 on success, 2 when the intake is missing, malformed, or
wrong-schema. The classification's `warnings` array is the source
of truth on whether action is needed (e.g. a `low-confidence
classification` warning fires when fewer than three signals
fired).

---

## 3. Heuristics

Three orthogonal signals are extracted from the intake's bounded
prompt + per-document previews:

| Signal | Detection | Output |
|--------|-----------|--------|
| **task kind** | substring match against four buckets (precedence: benchmark > validation > comparison > extraction) | `task_kind` enum |
| **candidate materials** | case-insensitive regex over a hand-curated formula table (CeO2 / PrOx / Sm2O3 / Y2O3 / ZrO2 / TiO2 / MgO / Al2O3 / Fe2O3 / SiO2 / La2O3) | `candidate_materials` list |
| **candidate metrics** | substring match over named metrics (oxygen_storage_capacity / temperature / conductivity / stability / redox_potential / surface_area) PLUS lifted CSV headers from any csv reader's `structured_summary.header` | `candidate_metrics` list |

`confidence` rolls up the three signals into one enum:

| signals fired | confidence |
|---------------|------------|
| 3             | high       |
| 2             | medium     |
| 0 or 1        | low + warning |

`proposed_source_tool`:

- `comparison` or `benchmark` AND at least one material detected → `materials_engine`
- everything else → `trinity_scientific_prompt_intake`

`proposed_difficulty_class`:

- `benchmark` with ≥ 8 documents → `high`
- `comparison` or `benchmark` with ≥ 2 materials → `medium`
- everything else → `low`

`extreme` is reserved (v0.1 never proposes it; operator override).

---

## 4. Classification contract

`schemas/trinity/scientific_task_classification.schema.json`
($id `trinity-scientific-task-classification/v0.1`, draft-07)

```json
{
  "schema": "trinity-scientific-task-classification/v0.1",
  "classification_id": "scl-<16hex>",
  "source_intake_id": "spi-<16hex>",
  "source_intake_sha256": "<64hex>",
  "combined_context_sha256": "<64hex>",
  "documents_count": 5,
  "reader_kind_counts":   {"csv": 1, "latex": 1, "pdf": 1, "text": 2},
  "reader_status_counts": {"ok": 4, "unsupported_missing_dependency": 1},
  "task_kind": "comparison",
  "confidence": "high",
  "candidate_materials": ["CeO2", "PrOx"],
  "candidate_metrics":   ["oxygen_storage_capacity", "temperature", "oxygen_storage_mmol_g", ...],
  "proposed_source_tool": "materials_engine",
  "proposed_difficulty_class": "medium",
  "expected_output_schema": "trinity-useful-compute-result/v0.4",
  "public_description": "Trinity scientific task classification from intake spi-<id> (task_kind=comparison) materials=CeO2,PrOx metrics=...",
  "warnings": [],
  "evidence": [
    "prompt: Compare ceria and praseodymia for oxygen storage capacity.",
    "table.csv (csv header): compound oxygen_storage_mmol_g temperature_c",
    "notes.md (extracted_text_preview): # Oxygen storage\n\nCompare ceria and praseodymia.\n"
  ],
  "threat_refs": ["T01", "T04", "T09"],
  "pinned_time": "2026-05-17T00:00:00+00:00"
}
```

The schema locks every pattern and enum. `evidence` items are
each capped at 256 chars; the array is capped at 16 items. No
field can carry full extracted text.

`classification_id` is `sha16(canonical({intake_id, pinned_time,
task_kind, materials, metrics}))` — deterministic for stable
input.

---

## 5. Task builder bridge

`useful_compute_task_builder.py` gains:

```
--from-scientific-classification PATH    # the classifier output
--intake-json PATH                       # required alongside the above
```

The builder:

1. Loads both files.
2. Cross-checks `classification.source_intake_id ==
   intake.intake_id` and
   `classification.source_intake_sha256 == sha256(intake_file)`.
   Refuses with rc=2 on mismatch.
3. Builds a request where:
   - `source_tool` = `classification.proposed_source_tool`
   - `task_type` = `scientific_intake` (locked — the worker
     contract stays stable regardless of the proposed routing)
   - `difficulty_class` = `classification.proposed_difficulty_class`
   - `expected_output_schema` = `classification.expected_output_schema`
   - `public_description` = `classification.public_description`
   - `metadata` carries THREE blocks:
     - `scientific_intake` (Sprint 5.21)
     - `scientific_reader_manifest` (Sprint 5.30)
     - `scientific_task_classification` (Sprint 5.31; bulky
       fields like `evidence` stay in the classification file,
       only the decision-shape lands in the request)

The CLI rejects combinations that would override the
classification's decisions: `--source-tool`,
`--difficulty-class`, `--public-description`,
`--expected-output-schema`, `--input-bundle`,
`--from-scientific-intake`. The operator still supplies
`--deadline`, `--max-reward-stocks` and the output path.

---

## 6. Privacy invariants

- The classifier **never reads any document file**. It reads the
  intake artifact alone. Sprint 5.20's bounded previews (1024
  chars apiece) are the upper bound on what the classifier sees.
- `evidence` items are sliced from those bounded previews and
  further capped at 200 chars each. A test poisons a document
  with a long sentinel string and asserts the classifier output
  contains at most two copies (preview + maybe one re-quote) —
  full text leakage would push the count far higher.
- The classifier never copies absolute paths. Only basenames.
- The classification's `source_intake_sha256` lets a reviewer
  bind the classification to the exact intake artifact that
  produced it.

---

## 7. Tests added in Sprint 5.31

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_scientific_task_classifier.py` | 22 | Canonical demo → comparison + high confidence + materials + metrics · classification_id pattern · sha256 + combined_ctx pinned · reader counts roll-up · task-kind heuristics for each of the four kinds (prompt-only neutral docs, to avoid corpus pollution) · default = extraction · low-confidence warning · medium-confidence when 2 of 3 signals · source_tool fallback when no materials · threat_refs present · deterministic classification_id · sentinel-poison test for extracted-text privacy · classification validates · all four task_kind branches validate · CLI rejects missing intake · CLI rejects wrong-schema · task_builder --from-scientific-classification builds valid request · cross-check refuses mismatched intake · CLI requires --intake-json with classification · CLI rejects conflicting flags |
| `tests/trinity/test_scientific_task_classifier_schema.py` | 12 | Schema valid draft-07 · v0.1 $id · classification_id pattern · source_intake_id pattern · task_kind enum · confidence enum · proposed_source_tool enum · proposed_difficulty_class enum · threat_refs pattern · evidence item size cap · additionalProperties locked · required set complete |
| `tests/trinity/test_scientific_task_classifier_safety.py` | 9 | Source has no wallet/sign/broadcast/payment/shell/subprocess/network/mutating-fs/LLM-client tokens · declares v0.1 schema constant · does NOT import sibling Trinity modules · evidence caps are named constants · heuristic tables are named module-level constants · threat_refs constant is exactly T01/T04/T09 · cross-check intake unchanged · cross-check task builder unchanged |

Total: **43 new tests**.

---

## 8. Non-goals for v0.1

- **No LLM.** Substring + regex only. A model-backed classifier
  belongs in a separate sprint with its own audit trail.
- **No network.** The classifier never opens a socket. The static
  safety test forbids every stdlib network primitive.
- **No document I/O.** The classifier reads ONE JSON file (the
  intake artifact) and writes ONE JSON file. No `.tex` / `.csv`
  / `.pdf` file is opened by the classifier; it works off the
  intake's bounded previews.
- **No new source_tool / task_type enum values.** The
  classifier proposes among the existing enum. v0.2 may add
  more granular task types.
- **No automatic task creation.** The classifier writes a
  classification JSON; the operator (or a future autonomous
  pipeline) decides whether to feed it into the task builder.
- **No materials_engine routing override in v0.1.** When the
  classifier picks `materials_engine`, the builder still locks
  `task_type=scientific_intake` so the worker contract stays
  identical to the Sprint 5.29 / 5.30 flow.

---

## 9. Manual demo

Using the Sprint 5.29 final intake at
`/tmp/trinity-5-29-final-intake/out/`:

```bash
INTAKE=$(ls /tmp/trinity-5-29-final-intake/out/TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json | head -1)
mkdir -p /tmp/trinity-5-31-classifier
python3 scripts/trinity/scientific_task_classifier.py \
    --intake-json "$INTAKE" \
    --out-json /tmp/trinity-5-31-classifier/classification.json \
    --pinned-time 2026-05-17T00:00:00+00:00

python3 scripts/trinity/useful_compute_task_builder.py \
    --from-scientific-classification /tmp/trinity-5-31-classifier/classification.json \
    --intake-json "$INTAKE" \
    --deadline 2026-06-30T00:00:00+00:00 \
    --max-reward-stocks 100000 \
    --out-json /tmp/trinity-5-31-classifier/request.json
```

Then drop the request into the queue + run-once and confirm
`governor_decisions_count=7` + `watchdog_safety_status=ok`.

---

## 10. Traceability

- Schema `$id`:
  `trinity-scientific-task-classification/v0.1` (new file).
- Request schema gains a new optional `scientific_task_classification`
  property under `metadata` — additive, `$id` unchanged.
- `combined_context_sha256` continues to flow:
  classifier reads it from the intake → builder copies it into
  request → worker's `compute_output_sha256` derives from it.
  The reader-sensitivity chain established in Sprints 5.29 + 5.30
  is preserved.
- Pure scripts + schemas + docs + tests. Zero `src/`, zero
  consensus, zero wallet / payment / broadcast changes.
