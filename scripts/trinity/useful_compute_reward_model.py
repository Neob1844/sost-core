#!/usr/bin/env python3
"""Trinity / Useful Compute — Pending Reward Model v0.1.

Computes a deterministic ``pending_reward_stocks`` figure for a single
worker's claimed contribution against a Trinity useful-compute task.

Hard invariants
---------------
- v0.1 NEVER pays. The function returns a *pending* reward report.
- An invalid result earns 0.
- A duplicate result earns 0 by default (``duplicate_reward_factor``).
- ``max_reward_stocks`` is an absolute cap.
- A normalised "useful second" floor and ceiling protect against
  obvious gaming (zero-work and DoS).
- Output is deterministic: given identical inputs, identical output.
- ``requires_manual_review`` is set whenever the worker's normalised
  benchmark looks suspicious (e.g. 100x cluster mean) or when validation
  was not strictly automatic.

The model is intentionally simple in v0.1 so reviewers can audit the
arithmetic by hand. Real production tuning happens later (separate
sprint) and MUST go through governance.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA = "trinity-useful-compute-reward/v0.1"

_DEFAULT_STOCKS_PER_NORMALISED_SECOND = 100
_DEFAULT_DUPLICATE_REWARD_FACTOR = 0.0
_DEFAULT_MANUAL_REVIEW_SCORE_FLOOR = 0.40
_DEFAULT_MAX_NORMALISED_BENCHMARK = 10.0
_DEFAULT_MIN_NORMALISED_BENCHMARK = 0.1
_DEFAULT_MAX_COMPUTE_SECONDS = 3600


_DIFFICULTY_MULTIPLIER = {
    "low":     1.0,
    "medium":  1.5,
    "high":    2.0,
    "extreme": 3.0,
}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def compute_pending_reward(
    *,
    task_id: str,
    worker_id: str,
    benchmark_score: float,
    verified_compute_seconds: float,
    difficulty_class: str,
    result_validated: bool,
    duplicate_result: bool,
    max_reward_stocks: int,
    stocks_per_normalised_second: int = _DEFAULT_STOCKS_PER_NORMALISED_SECOND,
    duplicate_reward_factor: float = _DEFAULT_DUPLICATE_REWARD_FACTOR,
    manual_review_score_floor: float = _DEFAULT_MANUAL_REVIEW_SCORE_FLOOR,
    max_compute_seconds: int = _DEFAULT_MAX_COMPUTE_SECONDS,
) -> Dict[str, Any]:
    """Compute the pending reward for ONE worker on ONE task.

    Returns a deterministic dict with:
      - ``pending_reward_stocks`` (int, >= 0)
      - ``reason`` (string explaining the result)
      - ``requires_manual_review`` (bool)
      - ``schema`` (constant)
      - ``deterministic_id`` (sha16 of canonical inputs, for ledger)
    """
    reasons: List[str] = []
    manual = False

    if not isinstance(task_id, str) or not task_id:
        raise ValueError("task_id must be a non-empty string")
    if not isinstance(worker_id, str) or not worker_id:
        raise ValueError("worker_id must be a non-empty string")
    if difficulty_class not in _DIFFICULTY_MULTIPLIER:
        raise ValueError(
            f"difficulty_class must be one of "
            f"{sorted(_DIFFICULTY_MULTIPLIER)}, got {difficulty_class!r}"
        )
    if max_reward_stocks < 0:
        raise ValueError("max_reward_stocks must be >= 0")
    if max_compute_seconds < 1:
        raise ValueError("max_compute_seconds must be >= 1")

    canonical_inputs = {
        "task_id": task_id,
        "worker_id": worker_id,
        "benchmark_score": float(benchmark_score),
        "verified_compute_seconds": float(verified_compute_seconds),
        "difficulty_class": difficulty_class,
        "result_validated": bool(result_validated),
        "duplicate_result": bool(duplicate_result),
        "max_reward_stocks": int(max_reward_stocks),
        "stocks_per_normalised_second": int(stocks_per_normalised_second),
        "duplicate_reward_factor": float(duplicate_reward_factor),
        "manual_review_score_floor": float(manual_review_score_floor),
        "max_compute_seconds": int(max_compute_seconds),
    }
    det_id = _sha16(canonical_dumps(canonical_inputs))

    if not result_validated:
        return {
            "schema": SCHEMA,
            "deterministic_id": det_id,
            "pending_reward_stocks": 0,
            "reason": "result not validated",
            "requires_manual_review": False,
        }

    if verified_compute_seconds <= 0:
        return {
            "schema": SCHEMA,
            "deterministic_id": det_id,
            "pending_reward_stocks": 0,
            "reason": "zero useful compute seconds",
            "requires_manual_review": False,
        }
    if verified_compute_seconds > max_compute_seconds:
        verified_compute_seconds = float(max_compute_seconds)
        reasons.append("compute seconds capped at max_compute_seconds")
        manual = True

    if benchmark_score <= 0:
        return {
            "schema": SCHEMA,
            "deterministic_id": det_id,
            "pending_reward_stocks": 0,
            "reason": "non-positive benchmark score",
            "requires_manual_review": True,
        }
    if benchmark_score < _DEFAULT_MIN_NORMALISED_BENCHMARK:
        manual = True
        reasons.append("benchmark below minimum normalised floor")
        benchmark_score = _DEFAULT_MIN_NORMALISED_BENCHMARK
    if benchmark_score > _DEFAULT_MAX_NORMALISED_BENCHMARK:
        manual = True
        reasons.append("benchmark above maximum normalised ceiling")
        benchmark_score = _DEFAULT_MAX_NORMALISED_BENCHMARK
    if benchmark_score < manual_review_score_floor:
        manual = True
        reasons.append("benchmark below manual review floor")

    normalised_seconds = verified_compute_seconds * benchmark_score
    difficulty_mul = _DIFFICULTY_MULTIPLIER[difficulty_class]
    raw_reward = normalised_seconds * difficulty_mul * stocks_per_normalised_second

    if duplicate_result:
        raw_reward = raw_reward * duplicate_reward_factor
        reasons.append(
            f"duplicate result; factor={duplicate_reward_factor}"
        )

    capped = min(int(raw_reward), int(max_reward_stocks))
    if capped < int(raw_reward):
        reasons.append("reward hit max_reward_stocks cap")

    if not reasons:
        reasons.append("standard reward")

    return {
        "schema": SCHEMA,
        "deterministic_id": det_id,
        "pending_reward_stocks": capped,
        "reason": "; ".join(reasons),
        "requires_manual_review": bool(manual),
    }


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_reward_model",
        description=(
            "Compute a pending reward in stocks for one worker's "
            "contribution to one task. v0.1: dry-run, never pays."
        ),
    )
    p.add_argument("--task-id", required=True)
    p.add_argument("--worker-id", required=True)
    p.add_argument("--benchmark-score", type=float, required=True)
    p.add_argument("--verified-compute-seconds", type=float, required=True)
    p.add_argument(
        "--difficulty-class", required=True,
        choices=sorted(_DIFFICULTY_MULTIPLIER),
    )
    p.add_argument("--result-validated", action="store_true")
    p.add_argument("--duplicate-result", action="store_true")
    p.add_argument("--max-reward-stocks", type=int, default=1000000)
    p.add_argument("--out-json", type=str, default=None)
    args = p.parse_args(argv)

    out = compute_pending_reward(
        task_id=args.task_id,
        worker_id=args.worker_id,
        benchmark_score=args.benchmark_score,
        verified_compute_seconds=args.verified_compute_seconds,
        difficulty_class=args.difficulty_class,
        result_validated=args.result_validated,
        duplicate_result=args.duplicate_result,
        max_reward_stocks=args.max_reward_stocks,
    )

    blob = canonical_dumps(out)
    if args.out_json:
        Path(args.out_json).write_text(blob, encoding="utf-8")
    print(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())
