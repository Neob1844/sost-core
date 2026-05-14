# Trinity Task Builder × Scientific Intake — v0.1

Sprint **5.21**. The bridge between the Sprint 5.20 *science inbox*
and the existing Useful Compute pipeline.

## What this sprint adds

`scripts/trinity/useful_compute_task_builder.py` gains a new code
path: `--from-scientific-intake <path>`. When that flag is set, the
task builder consumes a Sprint 5.20 intake artifact
(`TRINITY_SCIENTIFIC_PROMPT_INTAKE_<id>.json`) and produces a
`trinity-useful-compute-request/v0.1` manifest that references the
intake **by hash**, never by content.

```
Scientific Prompt Intake artifact (v0.20)
        |  combined_context_sha256 (64-hex)
        |  prompt_sha256
        |  documents_count
        |  intake_id (spi-<16hex>)
        v
useful_compute_task_builder --from-scientific-intake ...
        |
        v
trinity-useful-compute-request/v0.1 with
        source_tool = "trinity_scientific_prompt_intake"
        task_type   = "scientific_intake"
        input_bundle_sha256 = intake.combined_context_sha256
        metadata.scientific_intake = { ... ids + hashes only ... }
        |
        v
EXISTING Useful Compute pipeline (worker / replay / governance / ...)
```

## What the bridge DOES NOT do (v0.1)

- It does NOT interpret the prompt semantically. No LLM is called.
- It does NOT copy document content into the request. Only
  identifiers and hashes are carried over.
- It does NOT store absolute paths. Only `path_basename` exists in
  the intake artifact, and the bridge does not even propagate that
  to the request.
- It does NOT touch a wallet, sign anything, broadcast anything.
- It does NOT change the on-chain wire format. The schema
  `trinity-useful-compute-request/v0.1` keeps the same `$id` and
  the same `const` schema string; the only changes are additive
  (new enum values + an optional `metadata` field).

## Safety gates the bridge enforces

Before producing a request, the bridge **refuses** the intake if
any of these is wrong:

| Check | Required value |
| --- | --- |
| `schema` | exactly `trinity-scientific-prompt-intake/v0.1` |
| `intake_id` | matches `^spi-[0-9a-f]{16}$` |
| `combined_context_sha256` | 64 lowercase hex |
| `prompt_sha256` | 64 lowercase hex |
| `documents_count` | non-negative integer |
| `safety_status.local_only` | `true` |
| `safety_status.no_network` | `true` |
| `safety_status.no_llm_call` | `true` |
| `safety_status.deterministic_output` | `true` |

If any of these fails, the bridge exits with code 2 and writes no
request. The downstream pipeline cannot inherit context from a
non-local / non-deterministic / LLM-flavoured intake.

## CLI

```
python3 scripts/trinity/useful_compute_task_builder.py \
    --from-scientific-intake \
        ./out/TRINITY_SCIENTIFIC_PROMPT_INTAKE_spi-<id>.json \
    --intake-task-kind benchmark \
    --intake-output-schema trinity-useful-compute-result/v0.4 \
    --difficulty-class low \
    --deadline 2026-06-30T00:00:00+00:00 \
    --max-reward-stocks 100000 \
    --out-json ./out/request.json
```

In intake mode the following legacy flags are **rejected** because
they conflict with values derived from the intake:

- `--source-tool` (forced to `trinity_scientific_prompt_intake`)
- `--input-bundle` (`input_bundle_sha256` comes from the intake)
- `--expected-output-schema` (use `--intake-output-schema` instead)
- `--public-description` (auto-generated from the intake)

The required intake-mode flags are:

- `--from-scientific-intake <path>`
- `--intake-task-kind <benchmark|comparison|extraction|validation>`
- `--intake-output-schema <schema-id>`
- `--difficulty-class`, `--deadline`, `--out-json` (still required;
  operator-driven)

`--candidate-id` is optional in intake mode; when omitted, the
request's `candidate_id` is derived from the intake_id as
`candidate-<intake_id>`.

## Request shape (intake-driven)

```json
{
  "schema": "trinity-useful-compute-request/v0.1",
  "request_id": "uc-<16 hex>",
  "source_tool": "trinity_scientific_prompt_intake",
  "task_type": "scientific_intake",
  "candidate_id": "candidate-spi-<intake-16hex>",
  "input_bundle_sha256": "<intake.combined_context_sha256>",
  "expected_output_schema": "trinity-useful-compute-result/v0.4",
  "validation_method": "deterministic_hash_check",
  "estimated_compute_cost": { "seconds": 60, "tier": "low" },
  "max_reward_stocks": 100000,
  "deadline": "2026-06-30T00:00:00+00:00",
  "manual_review_required": false,
  "public_description": "Trinity Useful Compute task derived from scientific intake spi-<id> (N documents); prompt preview: ...",
  "metadata": {
    "scientific_intake": {
      "intake_id": "spi-<16 hex>",
      "combined_context_sha256": "<64 hex>",
      "prompt_sha256": "<64 hex>",
      "documents_count": N,
      "intake_task_kind": "benchmark",
      "intake_artifact_sha256": "<64 hex>"
    }
  }
}
```

`intake_artifact_sha256` is the sha256 of the intake JSON file bytes
on disk at build time — a second-layer integrity hash beyond
`combined_context_sha256`, so the operator can prove the request was
derived from a specific intake artifact file rather than just a
matching internal hash.

## Determinism

- The bridge does not depend on wall-clock time; the only
  time-shaped input is `--deadline`, which the operator supplies.
- Same intake + same operator flags → same `request_id` and
  byte-identical `request.json`. Verified by
  `test_same_intake_same_request_id`.
- Changing `--intake-task-kind` changes the `request_id`
  (`metadata.scientific_intake.intake_task_kind` is part of the
  canonical hash).

## End-to-end example

```bash
# Step 1 — produce the intake artifact (Sprint 5.20).
python3 scripts/trinity/scientific_prompt_intake.py \
    --mode local-dry-run \
    --prompt "Compare ceria and praseodymia oxygen storage." \
    --document ./notes/ceria.md \
    --document ./notes/praseodymia.md \
    --document ./refs/data.json \
    --out-dir ./out/intake \
    --pinned-time 2026-05-13T00:00:00+00:00

# Step 2 — turn that intake into an auditable Useful Compute task.
INTAKE=$(ls ./out/intake/TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json \
    | head -1)
python3 scripts/trinity/useful_compute_task_builder.py \
    --from-scientific-intake "$INTAKE" \
    --intake-task-kind comparison \
    --intake-output-schema trinity-useful-compute-result/v0.4 \
    --difficulty-class low \
    --deadline 2026-06-30T00:00:00+00:00 \
    --max-reward-stocks 100000 \
    --out-json ./out/request.json

# Step 3 — the rest of the Useful Compute pipeline (worker /
# replay / governance / budget / proposal / draft) is unchanged.
# `--source-tool=trinity_scientific_prompt_intake` is a new enum
# value all downstream scripts already accept because they only
# pattern-match on schema + request_id, not on source_tool.
```

## Files modified / added

| File | Change |
| --- | --- |
| `schemas/trinity/useful_compute_request.schema.json` | additive: `source_tool` enum + `task_type` enum + optional `metadata.scientific_intake`. `$id` and `const schema` unchanged. |
| `scripts/trinity/useful_compute_task_builder.py` | new `--from-scientific-intake` / `--intake-task-kind` / `--intake-output-schema` flags; intake validator; legacy path preserved. |
| `tests/trinity/test_task_builder_from_scientific_intake.py` | NEW — 26 functional tests. |
| `tests/trinity/test_task_builder_from_scientific_intake_safety.py` | NEW — 11 static-safety tests. |
| `docs/TRINITY_TASK_BUILDER_FROM_SCIENTIFIC_INTAKE_V01.md` | NEW — this document. |
| `website/trinity-useful-compute.html` | mini-card "Task Builder From Scientific Intake v0.1". |
| `website/api/explorer_version.json` | v245 with the milestone text. |
