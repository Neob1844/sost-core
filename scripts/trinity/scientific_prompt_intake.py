#!/usr/bin/env python3
"""Trinity / Scientific Prompt Intake v0.1 (Sprint 5.20).

Local-only ingest of a scientific prompt plus any number of
reference documents (.txt / .md / .json). Hashes every input,
records bounded previews, and writes a deterministic audit
artifact at:

    TRINITY_SCIENTIFIC_PROMPT_INTAKE_<intake_id>.json

What this layer DOES:
    - read the prompt string and each --document file from disk
    - sha256 each input
    - record only basename (no absolute paths) + size + preview
    - canonical-JSON the result and write it once

What this layer does NOT do (and cannot do):
    - call any LLM or remote API
    - open a socket / make an HTTP request
    - read a wallet, sign anything, broadcast anything
    - touch sost-cli in any way
    - rewrite the document on disk

The script bounds every input by size and count; an out-of-range
input is refused BEFORE the artifact is written so there is no
half-finished output on disk.
"""

from __future__ import annotations

import argparse
import hashlib
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
DEFAULT_ALLOWED_EXTS     = (".txt", ".md", ".json")

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
    # Decode for the preview; fall back to a replace strategy so a
    # binary chunk in a .txt does not abort the intake.
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    return {
        "path_basename": path.name,
        "sha256": _sha256_bytes(raw),
        "bytes":  len(raw),
        "text_preview": _make_preview(text, preview_chars),
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

    combined_context_sha = _sha256_str(canonical_dumps({
        "prompt_sha256": prompt_sha,
        "documents": [
            {"sha256": d["sha256"], "bytes": d["bytes"]}
            for d in raw_docs
        ],
    }))

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
        help="Path to a reference document (.txt / .md / .json). "
             "Repeat for multiple documents.",
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
