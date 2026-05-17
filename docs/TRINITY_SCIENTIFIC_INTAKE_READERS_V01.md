# Trinity Scientific Intake Readers v0.1

**Sprint:** 5.29
**Status:** local-only · deterministic · no LLM · no network · no wallet / no broadcast
**Depends on:** Sprint 5.20 (Scientific Prompt Intake) · Sprint 5.21 (task_builder `--from-scientific-intake`)

---

## 1. Why it exists

Before this sprint, `scientific_prompt_intake.py` accepted only
`.txt` / `.md` / `.json` documents. Real scientific work comes in
PDFs, LaTeX sources and CSV tables. Trinity could hash them, but
only by adding extension flags one at a time — and the artifact
recorded nothing about WHAT the document contained beyond the raw
bytes hash.

Sprint 5.29 ships a **pluggable reader registry**:

| Extension | Reader | Notes |
|-----------|--------|-------|
| `.txt`    | text   | extracted_text = decoded UTF-8 |
| `.md`     | text   | extracted_text = decoded UTF-8 |
| `.json`   | json   | extracted_text = canonical JSON (or raw on parse_error) |
| `.tex`    | latex  | strips comments, math, most commands; deterministic prose extraction |
| `.csv`    | csv    | row_count, column_count, header, preview rows |
| `.pdf`    | pdf    | graceful: pypdf / PyPDF2 if importable, else `unsupported_missing_dependency` |

No LLM. No network. No subprocess. No shell-out to pdftotext or
pandoc. The PDF backend is loaded via **dynamic import** so a host
without pypdf does not crash at import time — it produces a
deterministic missing-dependency record instead.

---

## 2. New per-document fields

Every document entry in the intake artifact now carries six
additional fields alongside the Sprint 5.20 originals:

```json
{
  "path_basename": "...",
  "sha256": "<64-hex>",
  "bytes": 1234,
  "text_preview": "...",

  "reader_kind": "text | json | pdf | latex | csv | unsupported",
  "reader_status": "ok | unsupported_extension | unsupported_missing_dependency | parse_error",
  "extracted_text_sha256": "<64-hex>",
  "extracted_text_preview": "...",
  "structured_summary": { ... reader-specific ... },
  "warnings": []
}
```

`structured_summary` is reader-specific (kept open / additive on
purpose so future readers don't need a schema bump):

- **text**: `line_count`, `char_count`
- **json**: `top_level_kind` (object/array/scalar/invalid), and
  either `top_level_keys_count` or `top_level_length`
- **latex**: `has_document_env`, `section_count`,
  `char_count_raw`, `char_count_extracted`
- **csv**: `row_count`, `column_count`, optional `header`,
  `preview_rows` (up to 5)
- **pdf**: `pdf_backend` (pypdf / PyPDF2 / null), `page_count`

The schema declares the six new fields as **optional** properties
(in `properties`, not in `required`) so:

- a pre-5.29 artifact still validates against the v0.1 schema;
- the v0.1 strict-required-set test for the documents items still
  passes;
- the v0.1 `additionalProperties: false` still rejects truly
  unknown fields.

---

## 3. `combined_context_sha256` change

Pre-5.29, the combined hash mixed in only `prompt_sha256` and
per-document `(sha256, bytes)`. Sprint 5.29 also mixes in:

- `extracted_text_sha256` per document, and
- `reader_kind` and `reader_status` per document.

This makes the audit trail honest: if a `.pdf` document went from
`unsupported_missing_dependency` (no pypdf on the host) to `ok`
(pypdf newly installed) the bytes did not change, but the
extracted text did — and `combined_context_sha256` now reflects
that. The existing test
`test_document_change_changes_combined_context_sha` continues to
pass (changing the raw bytes still changes the hash); a new test
`test_combined_sha_changes_when_reader_status_changes` locks the
reader_status dimension.

---

## 4. Graceful PDF dependency

`_pdf_reader_module()` is a dynamic-import helper:

```python
def _pdf_reader_module():
    try:
        import pypdf
        return ("pypdf", pypdf)
    except ImportError:
        pass
    try:
        import PyPDF2
        return ("PyPDF2", PyPDF2)
    except ImportError:
        pass
    return None
```

When it returns `None`, the PDF reader writes:

```json
{
  "reader_kind": "pdf",
  "reader_status": "unsupported_missing_dependency",
  "extracted_text_sha256": "<sha of empty string>",
  "structured_summary": {"pdf_backend": null, "page_count": 0},
  "warnings": ["no PDF backend available …"]
}
```

The intake **does not** install anything, **does not** shell out
to a `pdftotext` binary, **does not** crash. The static safety
test asserts pypdf / PyPDF2 are never imported at module top
level — only inside `_pdf_reader_module()`.

The pdf-with-backend test is skipped via `pytest.mark.skipif` when
no backend is importable. The missing-dependency branch is tested
deterministically on every host via `monkeypatch.setattr(intake,
"_pdf_reader_module", lambda: None)` — so CI coverage of the
graceful path is unconditional.

A safety hard cap of `PDF_MAX_PAGES_TO_EXTRACT = 200` keeps an
adversarial PDF from blowing up the artifact; pages past the cap
are skipped with a warning.

---

## 5. `.tex` extraction

Minimal but deterministic. In order:

1. Prefer the body between `\begin{document}` and `\end{document}`
   when both are present (recorded as
   `structured_summary.has_document_env`).
2. Strip line-leading `%` comments.
3. Strip display math (`\[…\]`, `\begin{equation}…`,
   `\begin{align}…`).
4. Strip inline math (`$…$`).
5. Rewrite `\section{X}` / `\textbf{X}` / `\emph{X}` / `\cite{X}`
   and friends to keep the brace argument (`X`).
6. Drop every other bare `\command` token.
7. Replace stray `{` and `}` with spaces.
8. Collapse 3+ consecutive newlines to two.

No pandoc, no LaTeX runtime, no `subprocess.Popen("xelatex", …)`.
The extraction is intentionally lossy on math and references — v0.1
is a hash-and-preview pass, not a typesetter.

---

## 6. `.csv` extraction

Uses the stdlib `csv` module on a `StringIO`. Records:

- `row_count`
- `column_count` = max row length
- `header` (only when the first row has at least one cell AND every
  cell in row 0 looks non-numeric — a small heuristic, easy to
  reason about)
- `preview_rows` up to 5

The `extracted_text` is a deterministic flat representation:
newline-joined rows of tab-joined cells, each cell capped at
`CSV_MAX_CELL_CHARS = 256`. Tabs and newlines inside cells are
replaced with spaces so the round-trip stays line-stable.

---

## 7. Unsupported extensions

Two distinct paths:

1. **Extension not in `--allowed-ext`** — refused outright with
   rc=2, no artifact written. Preserves the Sprint 5.20 contract
   (existing test `test_unknown_extension_rejected` still holds).
2. **Extension in `--allowed-ext` but not in the reader
   registry** — accepted; the file is hashed; the record gets
   `reader_kind: unsupported`, `reader_status:
   unsupported_extension`, empty `extracted_text`, a per-document
   warning, and a top-level warning. No crash.

This means an operator can drop a `.yaml` file into the intake by
adding `--allowed-ext .yaml`, and the intake will record it as
unsupported rather than refusing it. Future readers can be added
without breaking the contract.

---

## 8. Tests added in Sprint 5.29

| File | Tests | What they cover |
|------|-------|-----------------|
| `tests/trinity/test_scientific_intake_readers.py` | 17 (incl. 1 skipped without pdf backend) | text reader for .md preserves Sprint 5.20 fields and adds new ones · json reader ok / parse_error · latex reader strips comments, math, commands; deterministic; with and without document env · csv reader row / column / header / preview / numeric-first-row heuristic · csv extracted_text deterministic · pdf reader missing-dep branch deterministically tested via monkeypatch · pdf reader extracts when backend available (skip otherwise) · unsupported extension via `--allowed-ext .yaml` records warning, no crash · truly-unknown extension still rejected rc=2 (preserves Sprint 5.20 contract) · combined_sha changes when extracted text changes · combined_sha changes when reader_status flips · `READER_KINDS` and `READER_STATUSES` enums exposed correctly |
| `tests/trinity/test_scientific_intake_readers_safety.py` | 6 | Delta safety: no new subprocess / shell / eval / exec introduced by the readers · reader dispatch table is a simple ext → callable map · default allowed-exts includes all 6 extensions · pypdf / PyPDF2 are NOT top-level imports (must be dynamic) · unsupported branch wired |

Total: **23 new tests**.

---

## 9. Non-goals for v0.1

- **No OCR.** PDFs without a text layer extract to an empty string
  (with the warnings from the backend). v0.2 may add a flag that
  shells out to a sandboxed OCR binary — explicitly **not** v0.1.
- **No pandoc.** `.tex` extraction is regex-based and bounded; it
  is not trying to round-trip a paper.
- **No XML / DOCX / EPUB / NetCDF / HDF5 / Parquet.** Each is its
  own dependency tree and its own audit surface. v0.2+ as separate
  sprints.
- **No installation of dependencies.** The intake never `pip
  install`s anything. Missing-dep is a deterministic record, not
  a side-effect.
- **No remote fetches.** The intake remains 100% local.
- **No LLM call for extraction.** The "scientific" word is about
  the input domain, not about model use.

---

## 10. Manual demo

```bash
mkdir -p /tmp/trinity-5-29-intake
cat > /tmp/trinity-5-29-intake/sample.md <<EOF
# Notes

Some prose for the intake.
EOF
cat > /tmp/trinity-5-29-intake/sample.tex <<'EOF'
\documentclass{article}
% comment removed
\begin{document}
\section{Methods}
We compare \textbf{ceria} and praseodymia ($T = 500^\circ$C).
\end{document}
EOF
cat > /tmp/trinity-5-29-intake/sample.csv <<EOF
compound,oxygen_storage_mmol_g,temperature_c
ceria,1.7,500
praseodymia,2.3,500
EOF

python3 scripts/trinity/scientific_prompt_intake.py \
    --mode local-dry-run \
    --prompt "Compare ceria and praseodymia." \
    --document /tmp/trinity-5-29-intake/sample.md \
    --document /tmp/trinity-5-29-intake/sample.tex \
    --document /tmp/trinity-5-29-intake/sample.csv \
    --out-dir /tmp/trinity-5-29-intake/out \
    --pinned-time 2026-05-17T00:00:00+00:00
```

Inspect the resulting JSON: each document should carry
`reader_kind`, `reader_status: "ok"`, an `extracted_text_sha256`,
and a `structured_summary` tailored to the format.

---

## 11. Traceability

- Schema id is unchanged (`trinity-scientific-prompt-intake/v0.1`).
  All new fields are additive and optional in the schema; the
  v0.1 strict-required-set test continues to pass.
- `combined_context_sha256` formula now includes
  `extracted_text_sha256` + `reader_status`. The existing test
  asserting that changing document content changes the combined
  sha still passes; a new test locks the reader_status dimension.
- Pure scripts + schemas + docs + tests merge. Zero `src/`, zero
  consensus, zero wallet / payment / broadcast changes.
