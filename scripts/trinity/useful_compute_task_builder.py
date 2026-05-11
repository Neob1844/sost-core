#!/usr/bin/env python3
"""Trinity / Useful Compute — Task Builder v0.1.

Builds a ``trinity-useful-compute-request/v0.1`` manifest from a
high-scoring candidate emitted by ``geo_dossier`` or
``materials_dossier``. v0.1 dry-run only: the manifest is written to
disk but never broadcast to miners. The ``--emit`` flag is reserved
for a future sprint and is rejected today.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA = "trinity-useful-compute-request/v0.1"

_DIFFICULTY_TO_SECONDS = {
    "low":     60,
    "medium":  300,
    "high":    1800,
    "extreme": 3600,
}

_SOURCE_TO_TASK_TYPE = {
    "materials_engine": "structure_relaxation",
    "geaspirit":        "scoring",
    "trinity_orchestrator": "other",
}

_SOURCE_TO_VALIDATION = {
    "materials_engine": "redundant_replay",
    "geaspirit":        "cross_worker_consensus",
    "trinity_orchestrator": "deterministic_hash_check",
}

_DIFFICULTY_TIER = {
    "low":     "low",
    "medium":  "medium",
    "high":    "high",
    "extreme": "extreme",
}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def build_request(
    *,
    source_tool: str,
    candidate_id: str,
    input_bundle_bytes: bytes,
    expected_output_schema: str,
    difficulty_class: str,
    max_reward_stocks: int,
    deadline: str,
    public_description: str,
    manual_review_required: bool = False,
    private_notes: Optional[str] = None,
    task_type_override: Optional[str] = None,
    validation_method_override: Optional[str] = None,
) -> Dict[str, Any]:
    if source_tool not in _SOURCE_TO_TASK_TYPE:
        raise ValueError(
            f"source_tool must be one of {sorted(_SOURCE_TO_TASK_TYPE)}"
        )
    if difficulty_class not in _DIFFICULTY_TO_SECONDS:
        raise ValueError(
            f"difficulty_class must be one of {sorted(_DIFFICULTY_TO_SECONDS)}"
        )

    task_type = task_type_override or _SOURCE_TO_TASK_TYPE[source_tool]
    validation_method = (
        validation_method_override or _SOURCE_TO_VALIDATION[source_tool]
    )
    seconds = _DIFFICULTY_TO_SECONDS[difficulty_class]
    tier = _DIFFICULTY_TIER[difficulty_class]
    input_sha = _sha256_hex(input_bundle_bytes)

    skeleton = {
        "schema": SCHEMA,
        "source_tool": source_tool,
        "candidate_id": candidate_id,
        "task_type": task_type,
        "input_bundle_sha256": input_sha,
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
            "Build a v0.1 useful compute request manifest from a "
            "single candidate. Dry-run only; --emit is rejected."
        ),
    )
    p.add_argument("--source-tool", required=True,
                   choices=sorted(_SOURCE_TO_TASK_TYPE))
    p.add_argument("--candidate-id", required=True)
    p.add_argument("--input-bundle", required=True,
                   help="Path to the deterministic input bundle file")
    p.add_argument("--expected-output-schema", required=True)
    p.add_argument("--difficulty-class", required=True,
                   choices=sorted(_DIFFICULTY_TO_SECONDS))
    p.add_argument("--max-reward-stocks", type=int, default=100000)
    p.add_argument("--deadline", required=True,
                   help="ISO-8601 timestamp")
    p.add_argument("--public-description", required=True)
    p.add_argument("--manual-review-required", action="store_true")
    p.add_argument("--out-json", required=True)
    p.add_argument(
        "--emit", action="store_true",
        help=(
            "RESERVED for a future sprint. v0.1 rejects this flag "
            "because manifests are dry-run only."
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

    bundle_bytes = Path(args.input_bundle).read_bytes()
    req = build_request(
        source_tool=args.source_tool,
        candidate_id=args.candidate_id,
        input_bundle_bytes=bundle_bytes,
        expected_output_schema=args.expected_output_schema,
        difficulty_class=args.difficulty_class,
        max_reward_stocks=args.max_reward_stocks,
        deadline=args.deadline,
        public_description=args.public_description,
        manual_review_required=args.manual_review_required,
    )
    Path(args.out_json).write_text(canonical_dumps(req), encoding="utf-8")
    print(f"[useful_compute_task_builder] wrote {args.out_json} "
          f"request_id={req['request_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
