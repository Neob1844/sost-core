#!/usr/bin/env python3
"""Trinity / Useful Compute — Task Builder v0.1.

Builds a ``trinity-useful-compute-request/v0.1`` manifest from a
high-scoring candidate emitted by ``geo_dossier`` or
``materials_dossier``. v0.1 dry-run only: the manifest is written to
disk but never broadcast to miners. The ``--emit`` flag is reserved
for a future sprint and is rejected today.

Sprint 5.21 — `--from-scientific-intake <path>` extends the task
builder so it can consume a
``TRINITY_SCIENTIFIC_PROMPT_INTAKE_<id>.json`` artifact produced by
Sprint 5.20. In that mode the request inherits the intake's
``combined_context_sha256`` as its ``input_bundle_sha256`` and
records the intake's identifiers under
``metadata.scientific_intake``. No document content is copied; no
absolute paths are stored.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA = "trinity-useful-compute-request/v0.1"
SCHEMA_INTAKE = "trinity-scientific-prompt-intake/v0.1"

_DIFFICULTY_TO_SECONDS = {
    "low":     60,
    "medium":  300,
    "high":    1800,
    "extreme": 3600,
}

_SOURCE_TO_TASK_TYPE = {
    "materials_engine":                "structure_relaxation",
    "geaspirit":                       "scoring",
    "trinity_orchestrator":            "other",
    "trinity_scientific_prompt_intake": "scientific_intake",
}

_SOURCE_TO_VALIDATION = {
    "materials_engine":                "redundant_replay",
    "geaspirit":                       "cross_worker_consensus",
    "trinity_orchestrator":            "deterministic_hash_check",
    "trinity_scientific_prompt_intake": "deterministic_hash_check",
}

_DIFFICULTY_TIER = {
    "low":     "low",
    "medium":  "medium",
    "high":    "high",
    "extreme": "extreme",
}

_INTAKE_TASK_KINDS = (
    "benchmark", "comparison", "extraction", "validation",
)

_INTAKE_ID_RE = re.compile(r"^spi-[0-9a-f]{16}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# =============================================================================
# Scientific intake loader (Sprint 5.21)
# =============================================================================

# Safety flags the intake MUST advertise as True. The task builder
# refuses to derive a request from an intake that does not lock all
# of them — a downstream pipeline must not be allowed to inherit
# context from a non-local / non-deterministic / LLM-flavoured intake.
_REQUIRED_INTAKE_SAFETY = (
    "local_only",
    "no_network",
    "no_llm_call",
    "deterministic_output",
)


def _load_scientific_intake(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(
            "--from-scientific-intake file not found: " + str(path)
        )
    raw = path.read_bytes()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "--from-scientific-intake is not valid UTF-8 JSON: "
            + str(exc)
        )
    if not isinstance(obj, dict):
        raise ValueError(
            "scientific intake must be a JSON object"
        )
    if obj.get("schema") != SCHEMA_INTAKE:
        raise ValueError(
            "scientific intake wrong schema: "
            + repr(obj.get("schema")) + " (expected " + SCHEMA_INTAKE + ")"
        )
    iid = obj.get("intake_id", "")
    if not (isinstance(iid, str) and _INTAKE_ID_RE.match(iid)):
        raise ValueError(
            "scientific intake intake_id wrong format: " + repr(iid)
        )
    ccs = obj.get("combined_context_sha256", "")
    if not (isinstance(ccs, str) and _SHA256_RE.match(ccs)):
        raise ValueError(
            "scientific intake combined_context_sha256 wrong format"
        )
    ps = obj.get("prompt_sha256", "")
    if not (isinstance(ps, str) and _SHA256_RE.match(ps)):
        raise ValueError(
            "scientific intake prompt_sha256 wrong format"
        )
    dc = obj.get("documents_count")
    if not (isinstance(dc, int) and dc >= 0 and not isinstance(dc, bool)):
        raise ValueError(
            "scientific intake documents_count must be non-negative int"
        )
    ss = obj.get("safety_status")
    if not isinstance(ss, dict):
        raise ValueError(
            "scientific intake safety_status missing or wrong type"
        )
    for flag in _REQUIRED_INTAKE_SAFETY:
        if ss.get(flag) is not True:
            raise ValueError(
                "scientific intake safety_status." + flag
                + " must be true; got " + repr(ss.get(flag))
            )
    return obj


def _make_intake_public_description(intake: Dict[str, Any]) -> str:
    """Auto-generated public_description for an intake-driven task.
    Uses a bounded snippet of prompt_preview so the request stays
    audit-friendly and well below the schema's 512-char ceiling."""
    raw_preview = intake.get("prompt_preview", "") or ""
    # Collapse internal newlines / tabs to keep the line compact.
    flat = " ".join(raw_preview.split())
    snippet = flat[:200]
    if len(flat) > 200:
        snippet = snippet[:197] + "..."
    iid = intake.get("intake_id", "spi-unknown")
    dc = intake.get("documents_count", 0)
    desc = (
        "Trinity Useful Compute task derived from scientific intake "
        + iid + " (" + str(dc) + " documents); prompt preview: "
        + snippet
    )
    return desc[:512]


# ---------------------------------------------------------------------------
# Sprint 5.30 — reader manifest bridge
# ---------------------------------------------------------------------------

_EMPTY_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)


def _per_doc_reader_record(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Project a Sprint 5.29 intake document down to the subset of
    fields downstream consumers (workers, operators, dashboards)
    actually need. Tolerates pre-5.29 intakes by defaulting the
    reader fields to "text" / "ok" / empty hash so the request
    schema still validates."""
    summary = doc.get("structured_summary")
    if not isinstance(summary, dict):
        summary = {}
    warnings = doc.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    extracted = doc.get("extracted_text_sha256")
    if not (isinstance(extracted, str) and len(extracted) == 64):
        extracted = _EMPTY_SHA256
    return {
        "path_basename": doc.get("path_basename", ""),
        "sha256":        doc.get("sha256", ""),
        "reader_kind":   doc.get("reader_kind", "text"),
        "reader_status": doc.get("reader_status", "ok"),
        "extracted_text_sha256": extracted,
        "structured_summary": summary,
        "warnings": [
            str(w)[:512] for w in warnings if isinstance(w, str)
        ],
    }


# ---------------------------------------------------------------------------
# Sprint 5.31 — scientific classification loader
# ---------------------------------------------------------------------------

SCHEMA_CLASSIFICATION = "trinity-scientific-task-classification/v0.1"
_CLASSIFICATION_ID_RE = re.compile(r"^scl-[0-9a-f]{16}$")
_CLF_DIFFICULTIES = ("low", "medium", "high", "extreme")
_CLF_SOURCE_TOOLS = (
    "materials_engine", "trinity_scientific_prompt_intake",
)
# Map classifier task_kind → builder intake_task_kind. v0.1 keeps
# this 1:1; both vocabularies happen to share the same labels.
_CLF_KIND_TO_INTAKE_KIND = {
    "comparison":  "comparison",
    "extraction":  "extraction",
    "validation":  "validation",
    "benchmark":   "benchmark",
}


def _load_classification(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(
            "--from-scientific-classification file not found: "
            + str(path)
        )
    raw = path.read_bytes()
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(
            "--from-scientific-classification is not valid UTF-8 "
            "JSON: " + str(exc)
        )
    if not isinstance(obj, dict):
        raise ValueError(
            "scientific classification must be a JSON object"
        )
    if obj.get("schema") != SCHEMA_CLASSIFICATION:
        raise ValueError(
            "scientific classification wrong schema: "
            + repr(obj.get("schema"))
        )
    cid = obj.get("classification_id", "")
    if not _CLASSIFICATION_ID_RE.match(cid):
        raise ValueError(
            "classification_id wrong format: " + repr(cid)
        )
    sid = obj.get("source_intake_id", "")
    if not _INTAKE_ID_RE.match(sid):
        raise ValueError(
            "classification source_intake_id wrong format: "
            + repr(sid)
        )
    s_sha = obj.get("source_intake_sha256", "")
    if not _SHA256_RE.match(s_sha):
        raise ValueError(
            "classification source_intake_sha256 wrong format"
        )
    if obj.get("task_kind") not in _CLF_KIND_TO_INTAKE_KIND:
        raise ValueError(
            "classification task_kind invalid: "
            + repr(obj.get("task_kind"))
        )
    if obj.get("proposed_source_tool") not in _CLF_SOURCE_TOOLS:
        raise ValueError(
            "classification proposed_source_tool invalid: "
            + repr(obj.get("proposed_source_tool"))
        )
    if obj.get("proposed_difficulty_class") not in _CLF_DIFFICULTIES:
        raise ValueError(
            "classification proposed_difficulty_class invalid"
        )
    return obj


def _classification_audit_subset(
    classification: Dict[str, Any],
) -> Dict[str, Any]:
    """Project the classification down to the subset that lands in
    metadata.scientific_task_classification. We deliberately drop
    the bulky evidence array (it stays in the classification file
    on disk; the request stays small)."""
    return {
        "classification_id": classification["classification_id"],
        "source_intake_id": classification["source_intake_id"],
        "source_intake_sha256": classification["source_intake_sha256"],
        "task_kind": classification["task_kind"],
        "confidence": classification["confidence"],
        "candidate_materials": list(
            classification.get("candidate_materials", [])
        ),
        "candidate_metrics": list(
            classification.get("candidate_metrics", [])
        ),
        "proposed_source_tool":
            classification["proposed_source_tool"],
        "proposed_difficulty_class":
            classification["proposed_difficulty_class"],
        "threat_refs": list(classification.get("threat_refs", [])),
    }


def _build_reader_manifest(intake: Dict[str, Any]) -> Dict[str, Any]:
    """Build the Sprint 5.30 scientific_reader_manifest block from a
    Sprint 5.29 (or pre-5.29) intake artifact. Records:
      - documents_count + combined_context_sha256 (mirrored from
        the intake so consumers can cross-check without loading
        the intake JSON);
      - per-document basename + raw sha + reader_kind +
        reader_status + extracted_text_sha256 +
        structured_summary + per-document warnings;
      - reader_kind_counts and reader_status_counts roll-ups.
    Never includes the raw extracted text. Never includes any
    absolute path. Deterministic: documents preserve the intake's
    order (the intake itself sorts them by sha256)."""
    raw_docs = intake.get("documents") or []
    docs = [_per_doc_reader_record(d) for d in raw_docs]
    kind_counts: Dict[str, int] = {}
    status_counts: Dict[str, int] = {}
    for d in docs:
        kind_counts[d["reader_kind"]] = (
            kind_counts.get(d["reader_kind"], 0) + 1
        )
        status_counts[d["reader_status"]] = (
            status_counts.get(d["reader_status"], 0) + 1
        )
    intake_warnings = intake.get("warnings")
    if not isinstance(intake_warnings, list):
        intake_warnings = []
    return {
        "documents_count": int(intake.get("documents_count", len(docs))),
        "combined_context_sha256": intake.get(
            "combined_context_sha256", _EMPTY_SHA256,
        ),
        "reader_kind_counts": dict(sorted(kind_counts.items())),
        "reader_status_counts": dict(sorted(status_counts.items())),
        "documents": docs,
        "intake_warnings": [
            str(w)[:512] for w in intake_warnings if isinstance(w, str)
        ],
    }


def build_request(
    *,
    source_tool: str,
    candidate_id: str,
    input_bundle_bytes: Optional[bytes] = None,
    input_bundle_sha256: Optional[str] = None,
    expected_output_schema: str,
    difficulty_class: str,
    max_reward_stocks: int,
    deadline: str,
    public_description: str,
    manual_review_required: bool = False,
    private_notes: Optional[str] = None,
    task_type_override: Optional[str] = None,
    validation_method_override: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if source_tool not in _SOURCE_TO_TASK_TYPE:
        raise ValueError(
            "source_tool must be one of "
            + repr(sorted(_SOURCE_TO_TASK_TYPE))
        )
    if difficulty_class not in _DIFFICULTY_TO_SECONDS:
        raise ValueError(
            "difficulty_class must be one of "
            + repr(sorted(_DIFFICULTY_TO_SECONDS))
        )
    # Accept either the raw bytes (legacy callers) or a pre-computed
    # sha256 (intake-bridge callers). Exactly one of the two must be
    # supplied.
    if (input_bundle_bytes is None) == (input_bundle_sha256 is None):
        raise ValueError(
            "build_request requires exactly one of input_bundle_bytes "
            "or input_bundle_sha256"
        )
    if input_bundle_sha256 is None:
        input_bundle_sha256 = _sha256_hex(input_bundle_bytes)
    if not _SHA256_RE.match(input_bundle_sha256):
        raise ValueError(
            "input_bundle_sha256 must be 64 lowercase hex chars"
        )

    task_type = task_type_override or _SOURCE_TO_TASK_TYPE[source_tool]
    validation_method = (
        validation_method_override or _SOURCE_TO_VALIDATION[source_tool]
    )
    seconds = _DIFFICULTY_TO_SECONDS[difficulty_class]
    tier = _DIFFICULTY_TIER[difficulty_class]

    skeleton: Dict[str, Any] = {
        "schema": SCHEMA,
        "source_tool": source_tool,
        "candidate_id": candidate_id,
        "task_type": task_type,
        "input_bundle_sha256": input_bundle_sha256,
        "expected_output_schema": expected_output_schema,
        "validation_method": validation_method,
        "estimated_compute_cost": {
            "seconds": seconds,
            "tier": tier,
        },
        "max_reward_stocks": int(max_reward_stocks),
        "deadline": deadline,
        "manual_review_required": bool(manual_review_required),
        "public_description": public_description,
    }
    if private_notes is not None:
        skeleton["private_notes"] = private_notes
    if metadata is not None:
        skeleton["metadata"] = metadata

    req_id = "uc-" + _sha16(canonical_dumps(skeleton))
    skeleton["request_id"] = req_id

    ordered = {
        k: skeleton[k] for k in sorted(skeleton.keys())
    }
    return ordered


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_task_builder",
        description=(
            "Build a v0.1 useful compute request manifest. Dry-run "
            "only; --emit is rejected. Sprint 5.21 adds "
            "--from-scientific-intake to consume a Sprint 5.20 "
            "intake artifact and produce a request that references "
            "the intake by hash without copying document content."
        ),
    )
    # Existing legacy path: every flag is operator-supplied.
    p.add_argument(
        "--source-tool", required=False,
        choices=sorted(_SOURCE_TO_TASK_TYPE),
        help="Source tool. Required unless --from-scientific-intake "
             "is given (in which case it is forced to "
             "'trinity_scientific_prompt_intake').",
    )
    p.add_argument(
        "--candidate-id", required=False,
        help="Operator-chosen candidate id. When "
             "--from-scientific-intake is given and no "
             "--candidate-id is passed, the candidate id is derived "
             "from the intake_id.",
    )
    p.add_argument(
        "--input-bundle", required=False,
        help="Path to the deterministic input bundle file. Required "
             "unless --from-scientific-intake supplies the hash.",
    )
    p.add_argument(
        "--expected-output-schema", required=False,
        help="Required unless --from-scientific-intake (then use "
             "--intake-output-schema).",
    )
    p.add_argument(
        "--difficulty-class", required=False, default=None,
        choices=sorted(_DIFFICULTY_TO_SECONDS),
        help=(
            "Required UNLESS --from-scientific-classification is "
            "given (the classification supplies "
            "proposed_difficulty_class). The legacy + scientific-"
            "intake paths validate that this is set post-parse."
        ),
    )
    p.add_argument(
        "--max-reward-stocks", type=int, default=100000,
    )
    p.add_argument("--deadline", required=True,
                   help="ISO-8601 timestamp")
    p.add_argument(
        "--public-description", required=False,
        help="Required unless --from-scientific-intake is given "
             "(then auto-generated from prompt_preview + "
             "documents_count + intake_id).",
    )
    p.add_argument("--manual-review-required", action="store_true")
    p.add_argument("--out-json", required=True)
    p.add_argument(
        "--emit", action="store_true",
        help=(
            "RESERVED for a future sprint. v0.1 rejects this flag "
            "because manifests are dry-run only."
        ),
    )

    # Sprint 5.21 — scientific intake bridge.
    p.add_argument(
        "--from-scientific-intake", default=None,
        help="Path to a TRINITY_SCIENTIFIC_PROMPT_INTAKE_<id>.json "
             "artifact (Sprint 5.20). When supplied, the request's "
             "input_bundle_sha256 is set to the intake's "
             "combined_context_sha256 and metadata.scientific_intake "
             "records the intake_id / prompt_sha256 / "
             "documents_count / intake_task_kind / "
             "intake_artifact_sha256.",
    )
    p.add_argument(
        "--intake-task-kind", default=None,
        choices=list(_INTAKE_TASK_KINDS),
        help="Required with --from-scientific-intake.",
    )
    p.add_argument(
        "--intake-output-schema", default=None,
        help="expected_output_schema for the request when "
             "--from-scientific-intake is given.",
    )

    # Sprint 5.31 — scientific task classification bridge.
    p.add_argument(
        "--from-scientific-classification", default=None,
        help=(
            "Path to a TRINITY_SCIENTIFIC_TASK_CLASSIFICATION JSON "
            "(Sprint 5.31). When supplied, the request's "
            "source_tool / difficulty / expected_output_schema / "
            "public_description / metadata.scientific_intake / "
            "metadata.scientific_reader_manifest are derived from "
            "the classification and the cross-referenced intake "
            "artifact. Requires --intake-json so the per-document "
            "reader manifest can be carried into the request."
        ),
    )
    p.add_argument(
        "--intake-json", default=None,
        help=(
            "Path to the intake JSON the classification was built "
            "from. Required when --from-scientific-classification "
            "is given; the task builder cross-checks that the "
            "intake_id and sha256 match the classification."
        ),
    )

    args = p.parse_args(argv)

    if args.emit:
        print(
            "[useful_compute_task_builder] --emit is not supported in "
            "v0.1; manifests are dry-run only.",
            file=sys.stderr,
        )
        return 2

    # Sprint 5.31 — --difficulty-class is optional ONLY when
    # --from-scientific-classification is used. All other branches
    # still require it.
    if (args.from_scientific_classification is None
            and not args.difficulty_class):
        print(
            "[useful_compute_task_builder] --difficulty-class is "
            "required unless --from-scientific-classification is "
            "given",
            file=sys.stderr,
        )
        return 2

    # Branch: scientific intake bridge.
    if args.from_scientific_intake is not None:
        for forbidden_flag, value in (
            ("--source-tool", args.source_tool),
            ("--input-bundle", args.input_bundle),
            ("--expected-output-schema", args.expected_output_schema),
            ("--public-description", args.public_description),
        ):
            if value not in (None, ""):
                print(
                    "[useful_compute_task_builder] " + forbidden_flag
                    + " must NOT be combined with "
                    "--from-scientific-intake (the intake mode "
                    "derives that value from the intake artifact)",
                    file=sys.stderr,
                )
                return 2
        if args.intake_task_kind is None:
            print(
                "[useful_compute_task_builder] "
                "--intake-task-kind is required with "
                "--from-scientific-intake",
                file=sys.stderr,
            )
            return 2
        if not args.intake_output_schema:
            print(
                "[useful_compute_task_builder] "
                "--intake-output-schema is required with "
                "--from-scientific-intake",
                file=sys.stderr,
            )
            return 2
        intake_path = Path(args.from_scientific_intake)
        try:
            intake = _load_scientific_intake(intake_path)
        except ValueError as exc:
            print(
                "[useful_compute_task_builder] error: " + str(exc),
                file=sys.stderr,
            )
            return 2
        intake_artifact_sha = _sha256_hex(intake_path.read_bytes())
        candidate_id = args.candidate_id or (
            "candidate-" + intake["intake_id"]
        )
        public_description = _make_intake_public_description(intake)
        metadata = {
            "scientific_intake": {
                "intake_id":              intake["intake_id"],
                "combined_context_sha256": intake["combined_context_sha256"],
                "prompt_sha256":          intake["prompt_sha256"],
                "documents_count":        int(intake["documents_count"]),
                "intake_task_kind":       args.intake_task_kind,
                "intake_artifact_sha256": intake_artifact_sha,
            },
            # Sprint 5.30 — reader metadata bridge. The intake script
            # (Sprint 5.29) records reader_kind / reader_status /
            # extracted_text_sha256 / structured_summary per document.
            # We mirror that here, augmented with two roll-up
            # counters, so workers and operators can audit reader
            # coverage without re-reading the intake artifact.
            # NO full extracted text is copied; only basenames,
            # hashes, summaries and per-doc warnings.
            "scientific_reader_manifest": _build_reader_manifest(intake),
        }
        try:
            req = build_request(
                source_tool="trinity_scientific_prompt_intake",
                candidate_id=candidate_id,
                input_bundle_sha256=intake["combined_context_sha256"],
                expected_output_schema=args.intake_output_schema,
                difficulty_class=args.difficulty_class,
                max_reward_stocks=args.max_reward_stocks,
                deadline=args.deadline,
                public_description=public_description,
                manual_review_required=args.manual_review_required,
                metadata=metadata,
            )
        except ValueError as exc:
            print(
                "[useful_compute_task_builder] error: " + str(exc),
                file=sys.stderr,
            )
            return 2
        Path(args.out_json).write_text(
            canonical_dumps(req), encoding="utf-8",
        )
        print(
            "[useful_compute_task_builder] wrote " + args.out_json
            + " request_id=" + req["request_id"]
            + " intake_id=" + intake["intake_id"]
            + " intake_task_kind=" + args.intake_task_kind
        )
        return 0

    # Sprint 5.31 — scientific classification bridge.
    if args.from_scientific_classification is not None:
        for forbidden_flag, value in (
            ("--source-tool", args.source_tool),
            ("--input-bundle", args.input_bundle),
            ("--expected-output-schema", args.expected_output_schema),
            ("--public-description", args.public_description),
            ("--difficulty-class", args.difficulty_class),
            ("--from-scientific-intake",
             args.from_scientific_intake),
        ):
            if value not in (None, ""):
                print(
                    "[useful_compute_task_builder] " + forbidden_flag
                    + " must NOT be combined with "
                    "--from-scientific-classification (the "
                    "classification supplies that value)",
                    file=sys.stderr,
                )
                return 2
        if not args.intake_json:
            print(
                "[useful_compute_task_builder] "
                "--intake-json is required with "
                "--from-scientific-classification (so the per-"
                "document reader manifest can be carried into "
                "the request)",
                file=sys.stderr,
            )
            return 2
        try:
            classification = _load_classification(
                Path(args.from_scientific_classification),
            )
            intake = _load_scientific_intake(Path(args.intake_json))
        except ValueError as exc:
            print(
                "[useful_compute_task_builder] error: " + str(exc),
                file=sys.stderr,
            )
            return 2

        # Cross-check the classification was built from THIS intake.
        if classification["source_intake_id"] != intake["intake_id"]:
            print(
                "[useful_compute_task_builder] error: "
                "classification source_intake_id "
                + classification["source_intake_id"]
                + " != intake intake_id " + intake["intake_id"],
                file=sys.stderr,
            )
            return 2
        intake_artifact_sha = _sha256_hex(
            Path(args.intake_json).read_bytes(),
        )
        if classification["source_intake_sha256"] != intake_artifact_sha:
            print(
                "[useful_compute_task_builder] error: "
                "classification source_intake_sha256 does not "
                "match the supplied --intake-json file's sha256 "
                "(classification was built from a different "
                "intake artifact)",
                file=sys.stderr,
            )
            return 2

        intake_task_kind = _CLF_KIND_TO_INTAKE_KIND[
            classification["task_kind"]
        ]
        candidate_id = args.candidate_id or (
            "candidate-" + classification["classification_id"]
        )
        metadata = {
            "scientific_intake": {
                "intake_id":              intake["intake_id"],
                "combined_context_sha256": intake["combined_context_sha256"],
                "prompt_sha256":          intake["prompt_sha256"],
                "documents_count":        int(intake["documents_count"]),
                "intake_task_kind":       intake_task_kind,
                "intake_artifact_sha256": intake_artifact_sha,
            },
            "scientific_reader_manifest": _build_reader_manifest(intake),
            # Sprint 5.31 — classification audit subset. Bulky
            # fields like `evidence` stay in the classification
            # file on disk; only the decision-shape lands in the
            # request to keep it small.
            "scientific_task_classification":
                _classification_audit_subset(classification),
        }
        try:
            req = build_request(
                source_tool=classification["proposed_source_tool"],
                candidate_id=candidate_id,
                input_bundle_sha256=intake["combined_context_sha256"],
                expected_output_schema=
                    classification["expected_output_schema"],
                difficulty_class=
                    classification["proposed_difficulty_class"],
                max_reward_stocks=int(args.max_reward_stocks)
                    if args.max_reward_stocks else 100000,
                deadline=args.deadline,
                public_description=classification["public_description"],
                manual_review_required=bool(args.manual_review_required),
                metadata=metadata,
                # Force task_type to scientific_intake regardless
                # of proposed_source_tool. v0.1 keeps the worker
                # contract stable: the classifier-derived request
                # is still validated as a scientific_intake task,
                # only the source_tool tag changes for routing.
                task_type_override="scientific_intake",
                validation_method_override="deterministic_hash_check",
            )
        except ValueError as exc:
            print(
                "[useful_compute_task_builder] error: " + str(exc),
                file=sys.stderr,
            )
            return 2
        Path(args.out_json).write_text(
            canonical_dumps(req), encoding="utf-8",
        )
        print(
            "[useful_compute_task_builder] wrote " + args.out_json
            + " request_id=" + req["request_id"]
            + " classification_id="
            + classification["classification_id"]
            + " task_kind=" + classification["task_kind"]
            + " proposed_source_tool="
            + classification["proposed_source_tool"]
            + " proposed_difficulty_class="
            + classification["proposed_difficulty_class"]
        )
        return 0

    # Legacy path: operator supplies every value.
    missing = []
    if not args.source_tool:
        missing.append("--source-tool")
    if not args.candidate_id:
        missing.append("--candidate-id")
    if not args.input_bundle:
        missing.append("--input-bundle")
    if not args.expected_output_schema:
        missing.append("--expected-output-schema")
    if not args.public_description:
        missing.append("--public-description")
    if missing:
        print(
            "[useful_compute_task_builder] missing required: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    bundle_bytes = Path(args.input_bundle).read_bytes()
    try:
        req = build_request(
            source_tool=args.source_tool,
            candidate_id=args.candidate_id,
            input_bundle_sha256=_sha256_hex(bundle_bytes),
            expected_output_schema=args.expected_output_schema,
            difficulty_class=args.difficulty_class,
            max_reward_stocks=args.max_reward_stocks,
            deadline=args.deadline,
            public_description=args.public_description,
            manual_review_required=args.manual_review_required,
        )
    except ValueError as exc:
        print(
            "[useful_compute_task_builder] error: " + str(exc),
            file=sys.stderr,
        )
        return 2
    Path(args.out_json).write_text(canonical_dumps(req), encoding="utf-8")
    print(
        "[useful_compute_task_builder] wrote " + args.out_json
        + " request_id=" + req["request_id"]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
