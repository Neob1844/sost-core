# Trinity Scientific Prompt Intake v0.1

Sprint **5.20**. The intake layer is Trinity's *science inbox*: a
deterministic, audit-friendly way to bring a scientific prompt and
local reference documents (papers, notes, datasets) into the
Trinity audit trail.

## What this layer DOES

1. Reads a prompt string (or `--prompt-file`) and zero or more
   `--document` paths.
2. Validates each document's extension is in the allowed set
   (default `.txt`, `.md`, `.json`).
3. Sha256-hashes every input and records a bounded text preview.
4. Writes one canonical-JSON artifact:
   `TRINITY_SCIENTIFIC_PROMPT_INTAKE_<intake_id>.json`.

```
intake_id = sha16(canonical(
    mode, pinned_time, prompt_sha256, combined_context_sha256
))
combined_context_sha256 = sha256(canonical(
    {"prompt_sha256": ..., "documents": [{sha256, bytes}, ...]}
))
```

Two runs with the same inputs and the same `--pinned-time` produce
**byte-identical** artifacts.

## What this layer does NOT do

- It NEVER calls an LLM or any remote API.
- It NEVER opens a network connection. No HTTP, no socket, no
  WebSocket, no FTP imports.
- It NEVER touches a wallet, NEVER signs, NEVER broadcasts.
- It NEVER stores the full document content. The artifact records
  only `path_basename` + sha256 + size + a bounded `text_preview`
  (default 256 chars).
- It NEVER stores absolute paths. Folder structure of the operator's
  system is not leaked into the audit trail.
- It NEVER produces a partial artifact: every size / extension /
  count limit is checked before any JSON is written.

## Safety flags (all const-true in the schema)

| Flag | Value |
| --- | --- |
| `local_only` | `const: true` |
| `no_network` | `const: true` |
| `no_llm_call` | `const: true` |
| `no_wallet_access` | `const: true` |
| `no_broadcast` | `const: true` |
| `no_private_keys` | `const: true` |
| `deterministic_output` | `const: true` |

## Default limits

| Limit | Default | Override |
| --- | --- | --- |
| max prompt bytes | 32 KiB | `--max-prompt-bytes` |
| max bytes per document | 1 MiB | `--max-doc-bytes` |
| max number of documents | 16 | `--max-docs` |
| preview chars per item | 256 | `--preview-chars` |
| allowed extensions | `.txt .md .json` | `--allowed-ext` (repeat) |

## Pre-argparse rejection

Every one of these flags would imply behaviour the intake is not
allowed to have in v0.1. Pre-argparse scan rejects them with
exit code 2:

`--broadcast`, `--send`, `--payout-now`, `--auto-pay`,
`--sign-now`, `--export-private-key`, `--wallet`, `--llm-call`,
`--http-call`, `--upload`.

## CLI

```
python3 scripts/trinity/scientific_prompt_intake.py \
    --mode local-dry-run \
    --prompt "Compare ceria and praseodymia oxygen storage." \
    --document ./notes/note-a.md \
    --document ./notes/note-b.txt \
    --document ./refs/data.json \
    --out-dir ./out \
    --pinned-time 2026-05-13T00:00:00+00:00
```

Or with the prompt in a file:

```
python3 scripts/trinity/scientific_prompt_intake.py \
    --mode local-dry-run \
    --prompt-file ./prompt.md \
    --document ./refs/paper.txt \
    --out-dir ./out \
    --pinned-time 2026-05-13T00:00:00+00:00
```

## Output shape

```json
{
  "schema": "trinity-scientific-prompt-intake/v0.1",
  "intake_id": "spi-<16hex>",
  "mode": "local-dry-run",
  "pinned_time": "2026-05-13T00:00:00+00:00",
  "prompt_sha256": "<64hex>",
  "prompt_preview": "...",
  "documents_count": 2,
  "documents": [
    {
      "path_basename": "note-a.md",
      "sha256": "<64hex>",
      "bytes": 1234,
      "text_preview": "..."
    },
    ...
  ],
  "combined_context_sha256": "<64hex>",
  "safety_status": {
    "local_only": true,
    "no_network": true,
    "no_llm_call": true,
    "no_wallet_access": true,
    "no_broadcast": true,
    "no_private_keys": true,
    "deterministic_output": true
  },
  "warnings": []
}
```

## Determinism notes

- Documents are sorted by their sha256 (then basename) BEFORE the
  artifact is built. This means the CLI order of `--document` does
  not affect the resulting `intake_id`.
- The artifact is written with
  `json.dumps(..., sort_keys=True, separators=(",", ":"),
  ensure_ascii=True)` followed by a trailing newline.
- Documents that share a basename but differ by sha256 are kept as
  distinct entries; a warning is appended noting the collision.

## Where this fits in the Trinity stack

This sprint is Trinity's **science inbox** — nothing more, nothing
less:

- It does NOT decide a task. (Task decisions live in
  `useful_compute_task_builder` and, future, the operator loop.)
- It does NOT call an LLM. v0.1 stays offline by design.
- It DOES produce an artifact that a future sprint can hand to
  `useful_compute_task_builder` (e.g. as the
  `--input-bundle` payload, or as a referenced
  `combined_context_sha256` inside the request body).

The audit chain after that future bridge:

```
Scientific Prompt Intake  ->  Useful Compute Task Builder
        |                              |
        v                              v
  intake_id + combined        request_id (uc-<id>)
  context sha256              referencing intake_id
```

## Future sprints (proposed)

- **5.21 — Intake-Bridge**: `task_builder` can read a
  `--from-intake <TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json>` flag,
  hashing the intake's `combined_context_sha256` into the request
  so the entire downstream chain (worker / replay / governance /
  budget / proposal / draft) can prove which prompt + documents
  drove the work.
- **5.22 — Offline summariser**: a deterministic, local-only
  preview enrichment that builds keyword + entity summaries WITHOUT
  ever leaving the box. Still no LLM.
- **5.23 — Gated LLM advisor**: optional, off by default, behind a
  separate token. Only summarises the intake; never authorises any
  payment or task.

## Files added in Sprint 5.20

| File | Purpose |
| --- | --- |
| `scripts/trinity/scientific_prompt_intake.py` | the intake script |
| `schemas/trinity/scientific_prompt_intake.schema.json` | strict v0.1 schema |
| `tests/trinity/test_scientific_prompt_intake.py` | functional / determinism / rejection / schema |
| `tests/trinity/test_scientific_prompt_intake_schema.py` | schema-level invariants |
| `tests/trinity/test_scientific_prompt_intake_safety.py` | static safety surface |
| `docs/TRINITY_SCIENTIFIC_PROMPT_INTAKE_V01.md` | this document |
