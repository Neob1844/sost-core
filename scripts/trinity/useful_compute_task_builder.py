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
        "--difficulty-class", required=True,
        choices=sorted(_DIFFICULTY_TO_SECONDS),
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

    args = p.parse_args(argv)

    if args.emit:
        print(
            "[useful_compute_task_builder] --emit is not supported in "
            "v0.1; manifests are dry-run only.",
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
            }
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
