#!/usr/bin/env python3
"""Trinity Scientific Task Classifier v0.1 (Sprint 5.31).

Deterministic, local-only, no-LLM classifier that reads a
Sprint 5.20+ scientific intake artifact (with Sprint 5.29 reader
metadata when present) and proposes a structured scientific task
plan for Useful Compute.

This script does NOT think the way a model would. It runs a small
set of substring + regex heuristics over the intake's prompt
preview and per-document reader previews, and emits a JSON
classification that downstream task_builder consumers can use to
shape a request.

Hard invariants v0.1 (enforced by static tests):
    - No LLM. No HTTP. No child process. No shell-out.
    - No wallet, no signing, no broadcasting.
    - Deterministic: same intake + same pinned_time always yields
      the same classification_id and the same output bytes.
    - No full extracted text reaches the classification output.
      Evidence snippets are bounded at 200 chars and are sourced
      ONLY from the intake's bounded previews (which are already
      capped at 1024 chars apiece by Sprint 5.20).
    - The classifier never reads any document file. It reads the
      intake artifact alone.

Usage:
    python3 scripts/trinity/scientific_task_classifier.py \\
        --intake-json /path/to/TRINITY_SCIENTIFIC_PROMPT_INTAKE_<id>.json \\
        --out-json /path/to/classification.json \\
        --pinned-time 2026-05-17T00:00:00+00:00
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_CLASSIFICATION = "trinity-scientific-task-classification/v0.1"
SCHEMA_INTAKE = "trinity-scientific-prompt-intake/v0.1"

TASK_KINDS = ("comparison", "extraction", "validation", "benchmark")
CONFIDENCES = ("low", "medium", "high")
PROPOSED_SOURCE_TOOLS = (
    "materials_engine", "trinity_scientific_prompt_intake",
)
DIFFICULTY_CLASSES = ("low", "medium", "high", "extreme")

EVIDENCE_SNIPPET_MAX = 200
EVIDENCE_MAX_ITEMS = 16
DEFAULT_OUTPUT_SCHEMA = "trinity-useful-compute-result/v0.4"

# Sprint 5.23 threat refs the classifier is positioned to surface:
#   T01 — bogus / poisoned input that bypasses validation
#   T04 — over-broad task scope leading to runaway compute
#   T09 — silent semantic mismatch between intake and request
THREAT_REFS = ("T01", "T04", "T09")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _truncate(s: str, n: int) -> str:
    if not isinstance(s, str):
        return ""
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# Heuristic dictionaries (intentionally small and reviewable)
# ---------------------------------------------------------------------------

# Task-kind keywords. Order is precedence: the first match wins
# from the highest-precedence bucket. Keywords are matched
# case-insensitively as whole-word fragments inside the combined
# prompt + per-doc previews.
_TASK_KEYWORDS = (
    ("benchmark",  ("benchmark", "benchmarking", "rank", "ranking",
                    "score table", "leaderboard")),
    ("validation", ("validate", "validation", "reproduce",
                    "reproduction", "double-check", "verify",
                    "verification")),
    ("comparison", ("compare", "comparison", "versus", " vs ",
                    "better than", "worse than", "trade-off",
                    "tradeoff")),
    ("extraction", ("extract", "extraction", "summarize",
                    "summarise", "list", "identify",
                    "what is", "what are")),
)

# Material name / formula table. Each entry: canonical formula →
# list of regex patterns (compiled case-insensitively). The
# canonical formula is what lands in candidate_materials.
_MATERIAL_PATTERNS = (
    ("CeO2",  (r"\bceria\b", r"\bcerium oxide\b",
               r"\bCe[Oo]2\b", r"\bcericoxide\b",
               r"\bcerium[\-\s]?dioxide\b")),
    ("PrOx",  (r"\bpraseodymia\b", r"\bpraseodymium oxide\b",
               r"\bPr[Oo][Xx]\b", r"\bPr6O11\b",
               r"\bPr2O3\b", r"\bPrO2\b")),
    ("Sm2O3", (r"\bsamaria\b", r"\bsamarium oxide\b",
               r"\bSm2O3\b")),
    ("Y2O3",  (r"\byttria\b", r"\bY2O3\b")),
    ("ZrO2",  (r"\bzirconia\b", r"\bZr[Oo]2\b")),
    ("TiO2",  (r"\btitania\b", r"\bTi[Oo]2\b",
               r"\btitanium dioxide\b")),
    ("MgO",   (r"\bmagnesia\b", r"\bMgO\b")),
    ("Al2O3", (r"\balumina\b", r"\bAl2O3\b")),
    ("Fe2O3", (r"\bhematite\b", r"\bFe2O3\b")),
    ("SiO2",  (r"\bsilica\b", r"\bSiO2\b")),
    ("La2O3", (r"\blanthana\b", r"\bLa2O3\b")),
)
_MATERIAL_REGEX = [
    (canonical, [re.compile(p, re.IGNORECASE) for p in patterns])
    for canonical, patterns in _MATERIAL_PATTERNS
]

# Metric name table. Each entry: canonical metric → list of
# substring matches (case-insensitive). CSV headers are checked
# separately and added too.
_METRIC_PATTERNS = (
    ("oxygen_storage_capacity",
        ("oxygen storage", "osc", "oxygen mobility",
         "oxygen_storage_mmol")),
    ("temperature",
        ("temperature", "temperature_c", "kelvin", " k ",
         "°c", "deg c")),
    ("conductivity",
        ("conductivity", "electrical conductivity",
         "ionic conductivity")),
    ("stability",
        ("stability", "thermal stability", "long-term",
         "durability")),
    ("redox_potential",
        ("redox", "ce3+/ce4+", "reduction potential")),
    ("surface_area",
        ("surface area", "bet area", "specific surface")),
)


# ---------------------------------------------------------------------------
# Intake loader
# ---------------------------------------------------------------------------


class ClassifierError(Exception):
    pass


def _load_intake(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.exists():
        raise ClassifierError("intake-json not found: " + str(path))
    raw = path.read_bytes()
    sha = _sha256_hex(raw)
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ClassifierError(
            "intake-json not valid UTF-8 JSON: " + str(exc)
        )
    if not isinstance(obj, dict):
        raise ClassifierError("intake-json must be a JSON object")
    if obj.get("schema") != SCHEMA_INTAKE:
        raise ClassifierError(
            "intake-json schema mismatch: " + repr(obj.get("schema"))
        )
    if not re.match(r"^spi-[0-9a-f]{16}$", obj.get("intake_id", "")):
        raise ClassifierError(
            "intake-json intake_id wrong format"
        )
    return obj, sha


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------


def _gather_corpus(intake: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Concatenate bounded previews from the intake into one
    searchable string. Returns (combined_corpus, evidence_pool).

    The classifier NEVER reads any document file from disk. It
    only reads the intake's own bounded preview fields, which
    Sprint 5.20 capped at 1024 chars apiece. This is the privacy
    contract: full extracted text never reaches the classifier
    output."""
    pieces: List[str] = []
    evidence_pool: List[str] = []

    prompt = intake.get("prompt_preview")
    if isinstance(prompt, str) and prompt:
        pieces.append(prompt)
        evidence_pool.append(
            "prompt: " + _truncate(prompt, EVIDENCE_SNIPPET_MAX)
        )

    for doc in intake.get("documents", []) or []:
        if not isinstance(doc, dict):
            continue
        name = str(doc.get("path_basename", ""))[:64]
        for key in ("text_preview", "extracted_text_preview"):
            preview = doc.get(key)
            if isinstance(preview, str) and preview:
                pieces.append(preview)
                evidence_pool.append(
                    name + " (" + key + "): "
                    + _truncate(preview, EVIDENCE_SNIPPET_MAX)
                )
        summary = doc.get("structured_summary")
        if isinstance(summary, dict):
            header = summary.get("header")
            if isinstance(header, list):
                joined = " ".join(
                    h for h in header if isinstance(h, str)
                )
                if joined:
                    pieces.append(joined)
                    evidence_pool.append(
                        name + " (csv header): "
                        + _truncate(joined, EVIDENCE_SNIPPET_MAX)
                    )

    corpus = "\n".join(pieces)
    return corpus, evidence_pool[:EVIDENCE_MAX_ITEMS]


def _detect_task_kind(corpus: str) -> Tuple[str, bool]:
    """Return (task_kind, explicit) where `explicit` is True iff
    at least one task-keyword fired. When no keyword matched, the
    default is 'extraction' (the most generic intake)."""
    lc = corpus.lower()
    for kind, words in _TASK_KEYWORDS:
        for w in words:
            if w.lower() in lc:
                return kind, True
    return "extraction", False


def _detect_materials(corpus: str) -> List[str]:
    found: List[str] = []
    for canonical, patterns in _MATERIAL_REGEX:
        for r in patterns:
            if r.search(corpus):
                if canonical not in found:
                    found.append(canonical)
                break
    found.sort()
    return found


def _detect_metrics(
    corpus: str, intake: Dict[str, Any],
) -> List[str]:
    lc = corpus.lower()
    found: List[str] = []
    for canonical, substrings in _METRIC_PATTERNS:
        for s in substrings:
            if s in lc:
                if canonical not in found:
                    found.append(canonical)
                break
    # CSV headers are an authoritative metric source. Lift any
    # header cell into candidate_metrics as a free-form string.
    for doc in intake.get("documents", []) or []:
        if not isinstance(doc, dict):
            continue
        if doc.get("reader_kind") != "csv":
            continue
        summary = doc.get("structured_summary")
        if not isinstance(summary, dict):
            continue
        header = summary.get("header")
        if not isinstance(header, list):
            continue
        for h in header:
            if not isinstance(h, str):
                continue
            cleaned = h.strip().lower().replace(" ", "_")[:64]
            if cleaned and cleaned not in found:
                found.append(cleaned)
    found.sort()
    return found


def _propose_difficulty(
    task_kind: str,
    documents_count: int,
    materials_count: int,
) -> str:
    """Tiny size-based heuristic. v0.1 stays conservative: the
    most expensive bucket only kicks in when the task is a
    benchmark with many documents."""
    if task_kind == "benchmark" and documents_count >= 8:
        return "high"
    if task_kind in ("comparison", "benchmark") and materials_count >= 2:
        return "medium"
    return "low"


def _propose_source_tool(
    task_kind: str, materials: List[str],
) -> str:
    """Conservative routing rule. Materials_engine is proposed
    only when the task is comparative / benchmarking AND at least
    one known material formula was detected. Everything else stays
    on trinity_scientific_prompt_intake (the safest path that
    already exists in production)."""
    if task_kind in ("comparison", "benchmark") and materials:
        return "materials_engine"
    return "trinity_scientific_prompt_intake"


def _make_public_description(
    intake_id: str,
    task_kind: str,
    materials: List[str],
    metrics: List[str],
) -> str:
    parts = [
        "Trinity scientific task classification from intake " + intake_id,
        " (task_kind=" + task_kind + ")",
    ]
    if materials:
        parts.append(" materials=" + ",".join(materials))
    if metrics:
        parts.append(" metrics=" + ",".join(metrics))
    desc = "".join(parts)
    return desc[:512]


def _expected_output_schema(task_kind: str) -> str:
    # v0.1: all task kinds funnel into the existing v0.4 result
    # schema. Future sprints may diverge by task_kind.
    return DEFAULT_OUTPUT_SCHEMA


def _kind_and_status_counts(intake: Dict[str, Any]) -> Tuple[
    Dict[str, int], Dict[str, int],
]:
    kind_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for doc in intake.get("documents", []) or []:
        if not isinstance(doc, dict):
            continue
        k = doc.get("reader_kind", "text")
        s = doc.get("reader_status", "ok")
        if not isinstance(k, str):
            k = "text"
        if not isinstance(s, str):
            s = "ok"
        kind_counts[k] = kind_counts.get(k, 0) + 1
        status_counts[s] = status_counts.get(s, 0) + 1
    return (
        dict(sorted(kind_counts.items())),
        dict(sorted(status_counts.items())),
    )


# ---------------------------------------------------------------------------
# Build the classification dict
# ---------------------------------------------------------------------------


def classify(
    *,
    intake: Dict[str, Any],
    source_intake_sha256: str,
    pinned_time: str,
) -> Dict[str, Any]:
    intake_id = intake.get("intake_id", "spi-0000000000000000")
    combined_ctx = intake.get(
        "combined_context_sha256", "0" * 64,
    )
    documents_count = int(intake.get("documents_count", 0))

    corpus, evidence_pool = _gather_corpus(intake)
    task_kind, task_explicit = _detect_task_kind(corpus)
    materials = _detect_materials(corpus)
    metrics = _detect_metrics(corpus, intake)
    kind_counts, status_counts = _kind_and_status_counts(intake)

    # Confidence: number of independent signals that fired.
    signals = (
        (1 if task_explicit else 0)
        + (1 if materials else 0)
        + (1 if metrics else 0)
    )
    if signals >= 3:
        confidence = "high"
    elif signals == 2:
        confidence = "medium"
    else:
        confidence = "low"

    proposed_source_tool = _propose_source_tool(task_kind, materials)
    proposed_difficulty = _propose_difficulty(
        task_kind, documents_count, len(materials),
    )

    warnings: List[str] = []
    # Surface intake warnings so a downstream consumer that reads
    # only the classification still sees them.
    for w in (intake.get("warnings") or []):
        if isinstance(w, str):
            warnings.append("intake: " + _truncate(w, 400))
    # Reader-status flags: anything non-ok in the intake bubbles
    # up as a classifier-level warning.
    for status, count in status_counts.items():
        if status != "ok":
            warnings.append(
                "reader_status=" + status + " on "
                + str(count) + " document(s)"
            )
    # If we ended up at low confidence, flag it.
    if confidence == "low":
        warnings.append(
            "low-confidence classification: only "
            + str(signals) + " of 3 signals fired (task_kw="
            + str(task_explicit) + ", materials="
            + str(bool(materials)) + ", metrics="
            + str(bool(metrics)) + ")"
        )

    classification_id = "scl-" + _sha16(canonical_dumps({
        "intake_id": intake_id,
        "pinned_time": pinned_time,
        "task_kind": task_kind,
        "materials": materials,
        "metrics": metrics,
    }))

    return {
        "schema": SCHEMA_CLASSIFICATION,
        "classification_id": classification_id,
        "source_intake_id": intake_id,
        "source_intake_sha256": source_intake_sha256,
        "combined_context_sha256": combined_ctx,
        "documents_count": documents_count,
        "reader_kind_counts": kind_counts,
        "reader_status_counts": status_counts,
        "task_kind": task_kind,
        "confidence": confidence,
        "candidate_materials": materials,
        "candidate_metrics": metrics,
        "proposed_source_tool": proposed_source_tool,
        "proposed_difficulty_class": proposed_difficulty,
        "expected_output_schema": _expected_output_schema(task_kind),
        "public_description": _make_public_description(
            intake_id, task_kind, materials, metrics,
        ),
        "warnings": warnings,
        "evidence": evidence_pool,
        "threat_refs": list(THREAT_REFS),
        "pinned_time": pinned_time,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scientific_task_classifier",
        description=(
            "Trinity Scientific Task Classifier v0.1. Deterministic, "
            "local-only, no-LLM classifier that proposes a structured "
            "scientific task plan from a Sprint 5.20+ intake artifact. "
            "NEVER opens the network, NEVER touches a wallet, NEVER "
            "signs, NEVER broadcasts."
        ),
    )
    p.add_argument("--intake-json", required=True)
    p.add_argument("--out-json", required=True)
    p.add_argument("--pinned-time", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()
    intake_path = Path(args.intake_json)
    try:
        intake, sha = _load_intake(intake_path)
        classification = classify(
            intake=intake,
            source_intake_sha256=sha,
            pinned_time=pinned,
        )
    except ClassifierError as exc:
        print(
            "[scientific_task_classifier] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        canonical_dumps(classification) + "\n",
        encoding="utf-8",
    )
    print(
        "[scientific_task_classifier] classification_id="
        + classification["classification_id"]
        + " task_kind=" + classification["task_kind"]
        + " confidence=" + classification["confidence"]
        + " materials=" + ",".join(
            classification["candidate_materials"]
        )
        + " metrics=" + ",".join(
            classification["candidate_metrics"][:6]
        )
        + " proposed_source_tool="
        + classification["proposed_source_tool"]
        + " out=" + str(out_path)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
