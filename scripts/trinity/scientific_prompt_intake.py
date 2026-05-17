#!/usr/bin/env python3
"""Trinity / Scientific Prompt Intake v0.1 (Sprint 5.20)
+ Readers v0.1 (Sprint 5.29).

Local-only ingest of a scientific prompt plus any number of
reference documents. Hashes every input, records bounded previews,
and writes a deterministic audit artifact at:

    TRINITY_SCIENTIFIC_PROMPT_INTAKE_<intake_id>.json

Supported document readers (Sprint 5.29):
    .txt / .md  → text reader
    .json       → json reader (decoded as text, structure validated)
    .tex        → minimal LaTeX text-extraction reader
    .csv        → csv reader with row / column / header summary
    .pdf        → pdf reader (graceful: degrades to
                  unsupported_missing_dependency when no pypdf /
                  PyPDF2 / pdfplumber is importable)

What this layer DOES:
    - read the prompt string and each --document file from disk
    - sha256 each input (raw bytes)
    - extract a deterministic plain-text view per document
    - sha256 the extracted text
    - canonical-JSON the result and write it once

What this layer does NOT do (and cannot do):
    - call any LLM or remote API
    - open a socket / make an HTTP request
    - read a wallet, sign anything, broadcast anything
    - touch any chain CLI
    - rewrite the document on disk
    - OCR a PDF (v0.1 — text-layer extraction only)

The script bounds every input by size and count; an out-of-range
input is refused BEFORE the artifact is written so there is no
half-finished output on disk. Unsupported file types whose
extension is in --allowed-ext are accepted and recorded with
reader_status set accordingly — they never crash the intake.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_INTAKE = "trinity-scientific-prompt-intake/v0.1"

# Conservative v0.1 defaults. The operator can lower them but
# raising them past the configured ceilings requires a code change.
DEFAULT_MAX_PROMPT_BYTES = 32 * 1024            # 32 KiB
DEFAULT_MAX_DOC_BYTES    = 1 * 1024 * 1024      # 1 MiB
DEFAULT_MAX_DOCS         = 16
DEFAULT_PREVIEW_CHARS    = 256
# Sprint 5.29 — readers expand the default-allowed set. The
# original Sprint 5.20 set (.txt .md .json) stays valid. Operators
# can still narrow this with --allowed-ext.
DEFAULT_ALLOWED_EXTS     = (
    ".txt", ".md", ".json", ".tex", ".csv", ".pdf",
)

# Sprint 5.29 — reader enums. Anything outside these enums in the
# emitted artifact is a code regression; the schema test pins them.
READER_KINDS = (
    "text", "json", "pdf", "latex", "csv", "unsupported",
)
READER_STATUSES = (
    "ok",
    "unsupported_extension",
    "unsupported_missing_dependency",
    "parse_error",
)

# Per-CSV reader: number of preview rows to keep. Bounded so a
# multi-million-row CSV never blows up the artifact.
CSV_PREVIEW_ROWS = 5
CSV_MAX_CELL_CHARS = 256
PDF_MAX_PAGES_TO_EXTRACT = 200

_INTAKE_ID_RE = re.compile(r"^spi-[0-9a-f]{16}$")


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _make_preview(text: str, preview_chars: int) -> str:
    """Bounded preview. Non-printable chars are replaced with U+FFFD
    so the JSON is always renderable; newlines are kept as \\n
    after slicing so a multi-line document still looks like prose
    in the preview."""
    if preview_chars <= 0:
        return ""
    sliced = text[:preview_chars]
    out_chars: List[str] = []
    for ch in sliced:
        if ch == "\n" or ch == "\t":
            out_chars.append(ch)
            continue
        if 0x20 <= ord(ch) <= 0x10FFFF:
            out_chars.append(ch)
        else:
            out_chars.append("�")
    return "".join(out_chars)


# ---------------------------------------------------------------------------
# Sprint 5.29 — pluggable readers
# ---------------------------------------------------------------------------


def _decode_utf8_lossy(raw: bytes) -> str:
    """Decode bytes as UTF-8, replacing any invalid sequence with
    U+FFFD. Same behaviour as the Sprint 5.20 preview path."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-8", errors="replace")


def _read_text(raw: bytes) -> Dict[str, Any]:
    """Reader for .txt and .md. Extracted text == decoded UTF-8."""
    text = _decode_utf8_lossy(raw)
    return {
        "reader_kind": "text",
        "reader_status": "ok",
        "extracted_text": text,
        "structured_summary": {
            "line_count": text.count("\n") + (0 if text == "" else 1),
            "char_count": len(text),
        },
        "warnings": [],
    }


def _read_json(raw: bytes) -> Dict[str, Any]:
    """Reader for .json. Tolerates malformed JSON by degrading to
    parse_error (warning + extracted_text from raw decode). Stable
    extracted_text formatting via canonical_dumps so two byte-
    identical JSONs always produce the same sha."""
    text = _decode_utf8_lossy(raw)
    warnings: List[str] = []
    structured: Dict[str, Any] = {}
    try:
        obj = json.loads(text)
        canonical = canonical_dumps(obj)
        if isinstance(obj, dict):
            structured["top_level_kind"] = "object"
            structured["top_level_keys_count"] = len(obj)
        elif isinstance(obj, list):
            structured["top_level_kind"] = "array"
            structured["top_level_length"] = len(obj)
        else:
            structured["top_level_kind"] = "scalar"
        return {
            "reader_kind": "json",
            "reader_status": "ok",
            "extracted_text": canonical,
            "structured_summary": structured,
            "warnings": warnings,
        }
    except json.JSONDecodeError as exc:
        warnings.append("json parse error: " + str(exc))
        return {
            "reader_kind": "json",
            "reader_status": "parse_error",
            "extracted_text": text,
            "structured_summary": {"top_level_kind": "invalid"},
            "warnings": warnings,
        }


# A small set of LaTeX patterns we strip for a deterministic plain-
# text view. We do NOT try to render math, references, or figures —
# v0.1 is a best-effort prose extraction. The intent is to give
# downstream consumers something to hash and preview, not to ship
# a PDF-quality renderer.
_TEX_COMMENT_RE = re.compile(r"(?m)(?<!\\)%.*$")
_TEX_DOC_ENV_BEGIN_RE = re.compile(
    r"\\begin\{document\}", re.IGNORECASE,
)
_TEX_DOC_ENV_END_RE = re.compile(
    r"\\end\{document\}", re.IGNORECASE,
)
_TEX_INLINE_MATH_RE = re.compile(r"\$[^$\n]*\$")
_TEX_DISPLAY_MATH_RE = re.compile(
    r"\\\[[\s\S]*?\\\]|\\begin\{equation\}[\s\S]*?\\end\{equation\}"
    r"|\\begin\{align\}[\s\S]*?\\end\{align\}",
)
# \cmd{...} → ... (keep the brace argument when sensible)
_TEX_CMD_WITH_ARG_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|chapter|"
    r"textbf|textit|emph|underline|texttt|title|author|abstract|cite)"
    r"\*?\{([^{}]*)\}"
)
# Bare \cmd or \cmd{} → drop
_TEX_BARE_CMD_RE = re.compile(r"\\[a-zA-Z]+\*?(\{\})?")
# Collapse multiple blank lines
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _read_latex(raw: bytes) -> Dict[str, Any]:
    """Reader for .tex. Strips comments, math and most commands to
    yield a deterministic plain-text view. No pandoc, no shell."""
    text = _decode_utf8_lossy(raw)
    structured: Dict[str, Any] = {}
    # Prefer the body inside \begin{document}…\end{document} when
    # present; otherwise process the whole file.
    m_begin = _TEX_DOC_ENV_BEGIN_RE.search(text)
    m_end = _TEX_DOC_ENV_END_RE.search(text)
    if m_begin and m_end and m_end.start() > m_begin.end():
        body = text[m_begin.end():m_end.start()]
        structured["has_document_env"] = True
    else:
        body = text
        structured["has_document_env"] = False

    # Strip comments, math, then commands. Order matters: stripping
    # commands first would eat the comment-introducer escape.
    body = _TEX_COMMENT_RE.sub("", body)
    body = _TEX_DISPLAY_MATH_RE.sub(" ", body)
    body = _TEX_INLINE_MATH_RE.sub(" ", body)
    body = _TEX_CMD_WITH_ARG_RE.sub(lambda m: m.group(2), body)
    body = _TEX_BARE_CMD_RE.sub("", body)
    # Replace stray braces
    body = body.replace("{", " ").replace("}", " ")
    body = _BLANK_LINES_RE.sub("\n\n", body)
    body = body.strip()

    structured["section_count"] = len(re.findall(
        r"\\section\b", text,
    ))
    structured["char_count_raw"] = len(text)
    structured["char_count_extracted"] = len(body)
    return {
        "reader_kind": "latex",
        "reader_status": "ok",
        "extracted_text": body,
        "structured_summary": structured,
        "warnings": [],
    }


def _read_csv(raw: bytes) -> Dict[str, Any]:
    """Reader for .csv. Uses the stdlib csv module via a StringIO
    over the decoded text. Records row_count, column_count, header
    (if the first row looks like a header), plus up to
    CSV_PREVIEW_ROWS preview rows."""
    text = _decode_utf8_lossy(raw)
    warnings: List[str] = []
    try:
        reader = csv.reader(io.StringIO(text))
        rows = [row for row in reader]
    except csv.Error as exc:
        warnings.append("csv parse error: " + str(exc))
        return {
            "reader_kind": "csv",
            "reader_status": "parse_error",
            "extracted_text": text,
            "structured_summary": {},
            "warnings": warnings,
        }

    row_count = len(rows)
    column_count = max((len(r) for r in rows), default=0)
    # Heuristic header detection: only when the first row has at
    # least one cell and every cell in row 0 is non-numeric.
    header: Optional[List[str]] = None
    if rows and rows[0] and all(
        not _looks_numeric(c) for c in rows[0]
    ):
        header = [c[:CSV_MAX_CELL_CHARS] for c in rows[0]]

    preview = []
    for r in rows[:CSV_PREVIEW_ROWS]:
        preview.append([c[:CSV_MAX_CELL_CHARS] for c in r])

    # Canonical extracted text: newline-joined rows, each row a
    # tab-joined sequence of cells, cells truncated. Deterministic
    # and small.
    extracted = "\n".join(
        "\t".join(c.replace("\t", " ").replace("\n", " ")[:CSV_MAX_CELL_CHARS] for c in r)
        for r in rows
    )

    summary: Dict[str, Any] = {
        "row_count": row_count,
        "column_count": column_count,
        "preview_rows": preview,
    }
    if header is not None:
        summary["header"] = header
    return {
        "reader_kind": "csv",
        "reader_status": "ok",
        "extracted_text": extracted,
        "structured_summary": summary,
        "warnings": warnings,
    }


def _looks_numeric(cell: str) -> bool:
    if not isinstance(cell, str):
        return False
    s = cell.strip()
    if not s:
        return False
    try:
        float(s.replace(",", ""))
        return True
    except ValueError:
        return False


def _pdf_reader_module():
    """Best-effort dynamic import. Returns the imported module name
    or None when no PDF backend is available. v0.1 prefers pypdf,
    then PyPDF2 as a fallback. No subprocess fallback to pdftotext."""
    try:
        import pypdf  # type: ignore
        return ("pypdf", pypdf)
    except ImportError:
        pass
    try:
        import PyPDF2  # type: ignore
        return ("PyPDF2", PyPDF2)
    except ImportError:
        pass
    return None


def _read_pdf(raw: bytes) -> Dict[str, Any]:
    """Reader for .pdf. Graceful: no dependency ⇒
    unsupported_missing_dependency + warning, no crash."""
    backend = _pdf_reader_module()
    if backend is None:
        return {
            "reader_kind": "pdf",
            "reader_status": "unsupported_missing_dependency",
            "extracted_text": "",
            "structured_summary": {
                "pdf_backend": None,
                "page_count": 0,
            },
            "warnings": [
                "no PDF backend available (pypdf or PyPDF2 not "
                "importable); text extraction skipped"
            ],
        }
    backend_name, mod = backend
    warnings: List[str] = []
    try:
        reader = mod.PdfReader(io.BytesIO(raw))
        pages = list(reader.pages)
        page_count = len(pages)
        extracted_chunks: List[str] = []
        for i, page in enumerate(pages):
            if i >= PDF_MAX_PAGES_TO_EXTRACT:
                warnings.append(
                    "pdf truncated at " + str(PDF_MAX_PAGES_TO_EXTRACT)
                    + " of " + str(page_count) + " pages"
                )
                break
            try:
                extracted_chunks.append(page.extract_text() or "")
            except Exception as exc:  # backend can throw various
                warnings.append(
                    "pdf page " + str(i) + " extract_text failed: "
                    + str(exc)[:200]
                )
        text = "\n\n".join(extracted_chunks)
        return {
            "reader_kind": "pdf",
            "reader_status": "ok",
            "extracted_text": text,
            "structured_summary": {
                "pdf_backend": backend_name,
                "page_count": page_count,
            },
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "reader_kind": "pdf",
            "reader_status": "parse_error",
            "extracted_text": "",
            "structured_summary": {
                "pdf_backend": backend_name,
                "page_count": 0,
            },
            "warnings": [
                "pdf parse error: " + str(exc)[:200]
            ],
        }


def _read_unsupported(raw: bytes) -> Dict[str, Any]:
    """Catch-all for files whose extension is in --allowed-ext but
    not in our reader registry. The intake never crashes on these;
    it records them with status unsupported_extension so a downstream
    consumer can spot the gap."""
    return {
        "reader_kind": "unsupported",
        "reader_status": "unsupported_extension",
        "extracted_text": "",
        "structured_summary": {},
        "warnings": [
            "extension not handled by any reader in v0.1; "
            "file was hashed and recorded but not parsed"
        ],
    }


_READER_BY_EXT = {
    ".txt":  _read_text,
    ".md":   _read_text,
    ".json": _read_json,
    ".tex":  _read_latex,
    ".csv":  _read_csv,
    ".pdf":  _read_pdf,
}


def _dispatch_reader(ext: str, raw: bytes) -> Dict[str, Any]:
    reader = _READER_BY_EXT.get(ext.lower())
    if reader is None:
        return _read_unsupported(raw)
    return reader(raw)


def _read_document(
    *, path: Path, max_doc_bytes: int, allowed_exts: Tuple[str, ...],
    preview_chars: int,
) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(
            "document not found: " + str(path)
        )
    if not path.is_file():
        raise ValueError(
            "document path is not a regular file: " + str(path)
        )
    ext = path.suffix.lower()
    if ext not in allowed_exts:
        raise ValueError(
            "document extension " + repr(ext)
            + " not in allowed set " + repr(allowed_exts)
            + " (path basename: " + path.name + ")"
        )
    raw = path.read_bytes()
    if len(raw) > max_doc_bytes:
        raise ValueError(
            "document " + path.name + " is " + str(len(raw))
            + " bytes; max allowed = " + str(max_doc_bytes)
        )
    # Decode for the legacy text_preview field (Sprint 5.20 path).
    # The reader subsystem (Sprint 5.29) decodes again as needed.
    text_for_preview = _decode_utf8_lossy(raw)
    reader_out = _dispatch_reader(ext, raw)

    extracted_text = reader_out["extracted_text"]
    return {
        # Sprint 5.20 fields — unchanged.
        "path_basename": path.name,
        "sha256": _sha256_bytes(raw),
        "bytes":  len(raw),
        "text_preview": _make_preview(text_for_preview, preview_chars),
        # Sprint 5.29 — reader fields.
        "reader_kind":   reader_out["reader_kind"],
        "reader_status": reader_out["reader_status"],
        "extracted_text_sha256": _sha256_str(extracted_text),
        "extracted_text_preview": _make_preview(
            extracted_text, preview_chars,
        ),
        "structured_summary": reader_out["structured_summary"],
        "warnings": list(reader_out["warnings"]),
    }


def _validate_intake_id(intake_id: str) -> None:
    if not _INTAKE_ID_RE.match(intake_id):
        raise ValueError(
            "internally-generated intake_id failed pattern check: "
            + repr(intake_id)
        )


def run_intake(
    *,
    prompt: str,
    document_paths: List[Path],
    out_dir: Path,
    pinned_time: str,
    mode: str = "local-dry-run",
    max_prompt_bytes: int = DEFAULT_MAX_PROMPT_BYTES,
    max_doc_bytes:    int = DEFAULT_MAX_DOC_BYTES,
    max_docs:         int = DEFAULT_MAX_DOCS,
    preview_chars:    int = DEFAULT_PREVIEW_CHARS,
    allowed_exts:     Tuple[str, ...] = DEFAULT_ALLOWED_EXTS,
) -> Dict[str, Any]:
    if mode != "local-dry-run":
        raise ValueError(
            "mode must be 'local-dry-run'; got " + repr(mode)
        )
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string")
    prompt_bytes = prompt.encode("utf-8")
    if len(prompt_bytes) > max_prompt_bytes:
        raise ValueError(
            "prompt is " + str(len(prompt_bytes))
            + " bytes; max allowed = " + str(max_prompt_bytes)
        )
    if len(document_paths) > max_docs:
        raise ValueError(
            "too many documents: " + str(len(document_paths))
            + "; max allowed = " + str(max_docs)
        )

    warnings: List[str] = []

    # Read each document once. Order documents by their sha256 so
    # two runs with the same set of files (regardless of CLI order)
    # produce identical artifacts.
    raw_docs: List[Dict[str, Any]] = []
    for path in document_paths:
        raw_docs.append(_read_document(
            path=path,
            max_doc_bytes=max_doc_bytes,
            allowed_exts=allowed_exts,
            preview_chars=preview_chars,
        ))
    raw_docs.sort(key=lambda d: (d["sha256"], d["path_basename"]))

    # Detect duplicate basenames after sorting; record as warning
    # rather than refusing — the operator may legitimately want two
    # files with the same basename from different folders, and the
    # sha256 difference still makes the entries distinct.
    seen_basenames: Dict[str, int] = {}
    for d in raw_docs:
        seen_basenames[d["path_basename"]] = (
            seen_basenames.get(d["path_basename"], 0) + 1
        )
    for name, count in sorted(seen_basenames.items()):
        if count > 1:
            warnings.append(
                "multiple documents share basename "
                + repr(name) + " (" + str(count) + " entries)"
            )

    prompt_sha = _sha256_str(prompt)
    prompt_preview = _make_preview(prompt, preview_chars)

    # Sprint 5.29 — combined hash now also mixes in extracted_text_sha256
    # and reader_status per document so a change in extracted text (e.g.
    # a tex command rewrite that yields the same raw bytes but different
    # plain text — should not happen because raw bytes drive everything,
    # but the contract is auditable either way) or a change in reader
    # status (e.g. pdf dependency newly installed) is visible in the
    # top-level combined hash.
    combined_context_sha = _sha256_str(canonical_dumps({
        "prompt_sha256": prompt_sha,
        "documents": [
            {
                "sha256": d["sha256"],
                "bytes":  d["bytes"],
                "extracted_text_sha256": d["extracted_text_sha256"],
                "reader_kind":   d["reader_kind"],
                "reader_status": d["reader_status"],
            }
            for d in raw_docs
        ],
    }))

    # Lift per-document warnings to the top-level warnings list so a
    # downstream consumer that only reads "warnings" still sees them.
    for d in raw_docs:
        for w in d.get("warnings", []):
            warnings.append(
                d["path_basename"] + ": " + w
            )

    intake_id = "spi-" + _sha16(canonical_dumps({
        "mode": mode,
        "pinned_time": pinned_time,
        "prompt_sha256": prompt_sha,
        "combined_context_sha256": combined_context_sha,
    }))
    _validate_intake_id(intake_id)

    artifact: Dict[str, Any] = {
        "schema": SCHEMA_INTAKE,
        "intake_id": intake_id,
        "mode": mode,
        "pinned_time": pinned_time,
        "prompt_sha256": prompt_sha,
        "prompt_preview": prompt_preview,
        "documents_count": len(raw_docs),
        "documents": raw_docs,
        "combined_context_sha256": combined_context_sha,
        "safety_status": {
            "local_only":           True,
            "no_network":           True,
            "no_llm_call":          True,
            "no_wallet_access":     True,
            "no_broadcast":         True,
            "no_private_keys":      True,
            "deterministic_output": True,
        },
        "warnings": warnings,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (
        "TRINITY_SCIENTIFIC_PROMPT_INTAKE_" + intake_id + ".json"
    )
    out_path.write_text(
        canonical_dumps(artifact) + "\n",
        encoding="utf-8",
    )
    return artifact


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="scientific_prompt_intake",
        description=(
            "Trinity Scientific Prompt Intake v0.1. Local-only "
            "ingest of a scientific prompt + N reference documents. "
            "Hashes everything, writes a deterministic JSON artifact. "
            "Never opens a network connection, never calls an LLM, "
            "never touches a wallet, never broadcasts."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument(
        "--prompt", default="",
        help="The scientific prompt as a literal string. Use empty "
             "string when only documents are provided.",
    )
    p.add_argument(
        "--prompt-file", default=None,
        help="Read the prompt from a UTF-8 text file. Mutually "
             "exclusive with a non-empty --prompt.",
    )
    p.add_argument(
        "--document", action="append", default=None,
        help=(
            "Path to a reference document. Default allowed "
            "extensions (Sprint 5.29): .txt / .md / .json / "
            ".tex / .csv / .pdf. Repeat for multiple documents."
        ),
    )
    p.add_argument("--out-dir", required=True)
    p.add_argument(
        "--pinned-time", default="2026-05-13T00:00:00+00:00",
    )
    p.add_argument(
        "--max-prompt-bytes", type=int,
        default=DEFAULT_MAX_PROMPT_BYTES,
    )
    p.add_argument(
        "--max-doc-bytes", type=int, default=DEFAULT_MAX_DOC_BYTES,
    )
    p.add_argument(
        "--max-docs", type=int, default=DEFAULT_MAX_DOCS,
    )
    p.add_argument(
        "--preview-chars", type=int,
        default=DEFAULT_PREVIEW_CHARS,
    )
    p.add_argument(
        "--allowed-ext", action="append", default=None,
        help="Allowed document extension (with leading dot). Repeat "
             "to allow more than one; default: .txt .md .json",
    )

    # Pre-argparse rejection. The intake script must never be asked
    # to do anything more than ingest local text. These flags would
    # all be a sign of misuse.
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    rejected_flags = (
        "--broadcast",
        "--send",
        "--payout-now",
        "--auto-pay",
        "--sign-now",
        "--export-private-key",
        "--wallet",
        "--llm-call",
        "--http-call",
        "--upload",
    )
    for f in rejected_flags:
        if f in raw_argv:
            print(
                "[scientific_prompt_intake] flag " + f
                + " is rejected in v0.1",
                file=sys.stderr,
            )
            return 2

    args = p.parse_args(argv)

    # Resolve the prompt: --prompt-file overrides --prompt only when
    # --prompt is empty; supplying both with non-empty values is an
    # error so the operator never has to guess which one won.
    prompt_text: str
    if args.prompt_file is not None:
        if args.prompt:
            print(
                "[scientific_prompt_intake] --prompt and "
                "--prompt-file are mutually exclusive (use one)",
                file=sys.stderr,
            )
            return 2
        pf = Path(args.prompt_file)
        if not pf.exists():
            print(
                "[scientific_prompt_intake] --prompt-file not "
                "found: " + str(pf),
                file=sys.stderr,
            )
            return 2
        try:
            prompt_text = pf.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            print(
                "[scientific_prompt_intake] --prompt-file is not "
                "valid UTF-8: " + str(exc),
                file=sys.stderr,
            )
            return 2
    else:
        prompt_text = args.prompt or ""

    document_paths = [Path(p) for p in (args.document or [])]
    allowed_exts: Tuple[str, ...]
    if args.allowed_ext:
        allowed_exts = tuple(args.allowed_ext)
    else:
        allowed_exts = DEFAULT_ALLOWED_EXTS

    try:
        artifact = run_intake(
            prompt=prompt_text,
            document_paths=document_paths,
            out_dir=Path(args.out_dir),
            pinned_time=args.pinned_time,
            mode=args.mode,
            max_prompt_bytes=args.max_prompt_bytes,
            max_doc_bytes=args.max_doc_bytes,
            max_docs=args.max_docs,
            preview_chars=args.preview_chars,
            allowed_exts=allowed_exts,
        )
    except ValueError as exc:
        print(
            "[scientific_prompt_intake] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    print(
        "[scientific_prompt_intake] intake_id="
        + artifact["intake_id"]
        + " documents=" + str(artifact["documents_count"])
        + " combined_context_sha256="
        + artifact["combined_context_sha256"]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
