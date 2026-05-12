#!/usr/bin/env python3
"""Trinity / Error Memory v0.1.

A deterministic, append-only ledger of lessons learned from previous
Trinity Autonomous Orchestrator runs.

Goals
-----
- Never repeat the *same* failed task twice without an explicit retry
  budget being honoured.
- Classify each failure into a closed cause taxonomy so the planner
  can take guardrail decisions (skip, downgrade, manual_review).
- Produce a human-auditable Markdown summary
  (``TRINITY_AUTONOMY_LESSONS.md``) that lists each lesson exactly
  once with its cause, frequency, and recommended response.

This is *not* opaque ML training. It is a small, hand-readable table
that the orchestrator queries by ``(vertical, task_signature)``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA = "trinity-error-memory/v0.1"

CAUSES = (
    "bad_input",
    "insufficient_evidence",
    "compute_failed",
    "validation_failed",
    "duplicate_candidate",
    "overclaim_risk",
)

_RECOMMENDED_RESPONSES: Dict[str, str] = {
    "bad_input":              "reject; do not retry with same input",
    "insufficient_evidence":  "downgrade priority; require more inputs",
    "compute_failed":         "retry once with backoff; then manual_review",
    "validation_failed":      "reject; require manual_review",
    "duplicate_candidate":    "skip; merge into earlier accepted candidate",
    "overclaim_risk":         "block; require council quorum to override",
}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def task_signature(vertical: str, task_inputs: Dict[str, Any]) -> str:
    """Deterministic short signature for a task (used to detect
    repeats). NOT a security-grade id; just a planner key."""
    payload = canonical_dumps({"v": vertical, "t": task_inputs})
    return _sha16(payload)


def record_lesson(
    *,
    ledger_path: Path,
    vertical: str,
    task_inputs: Dict[str, Any],
    cause: str,
    detail: str,
    pinned_time: str,
) -> Dict[str, Any]:
    if cause not in CAUSES:
        raise ValueError(f"cause must be one of {CAUSES}, got {cause!r}")
    sig = task_signature(vertical, task_inputs)
    lesson = {
        "schema": SCHEMA,
        "ts": pinned_time,
        "vertical": vertical,
        "task_signature": sig,
        "cause": cause,
        "detail": detail,
        "recommended_response": _RECOMMENDED_RESPONSES[cause],
    }
    line = canonical_dumps(lesson) + "\n"
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
    return lesson


def read_lessons(ledger_path: Path) -> List[Dict[str, Any]]:
    if not ledger_path.exists():
        return []
    out: List[Dict[str, Any]] = []
    for raw in ledger_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and d.get("schema") == SCHEMA:
            out.append(d)
    return out


def has_repeat_lesson(
    ledger_path: Path,
    vertical: str,
    task_inputs: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return the *first* lesson with the same task_signature, or None.

    The orchestrator uses this to refuse to re-run a task that has
    already failed in an identical configuration without an explicit
    retry decision.
    """
    sig = task_signature(vertical, task_inputs)
    for entry in read_lessons(ledger_path):
        if entry.get("vertical") == vertical and \
           entry.get("task_signature") == sig:
            return entry
    return None


def render_lessons_md(lessons: List[Dict[str, Any]]) -> str:
    if not lessons:
        return (
            "# TRINITY AUTONOMY LESSONS\n\n"
            "_No lessons recorded yet._\n"
        )

    # Aggregate by (vertical, cause) for the summary header, but keep
    # the full table for full audit detail.
    counts: Dict[str, int] = {}
    for ls in lessons:
        key = f"{ls.get('vertical', '?')}::{ls.get('cause', '?')}"
        counts[key] = counts.get(key, 0) + 1

    out = ["# TRINITY AUTONOMY LESSONS", ""]
    out.append("## Aggregated failures (vertical :: cause)")
    out.append("")
    for key in sorted(counts):
        out.append(f"- `{key}` x{counts[key]}")
    out.append("")
    out.append("## Lesson ledger (chronological)")
    out.append("")
    out.append("| ts | vertical | cause | task_sig | recommended response |")
    out.append("|---|---|---|---|---|")
    for ls in lessons:
        out.append(
            f"| {ls.get('ts','')} | {ls.get('vertical','')} | "
            f"{ls.get('cause','')} | {ls.get('task_signature','')} | "
            f"{ls.get('recommended_response','')} |"
        )
    out.append("")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="trinity_error_memory")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="append a lesson")
    p_rec.add_argument("--ledger", required=True)
    p_rec.add_argument("--vertical", required=True)
    p_rec.add_argument("--task-inputs-json", required=True,
                       help="JSON string of task inputs")
    p_rec.add_argument("--cause", required=True, choices=CAUSES)
    p_rec.add_argument("--detail", required=True)
    p_rec.add_argument("--pinned-time", required=True)

    p_sum = sub.add_parser("summary", help="render Markdown summary")
    p_sum.add_argument("--ledger", required=True)
    p_sum.add_argument("--out-md", required=True)

    args = p.parse_args(argv)

    if args.cmd == "record":
        task_inputs = json.loads(args.task_inputs_json)
        lesson = record_lesson(
            ledger_path=Path(args.ledger),
            vertical=args.vertical,
            task_inputs=task_inputs,
            cause=args.cause,
            detail=args.detail,
            pinned_time=args.pinned_time,
        )
        print(canonical_dumps(lesson))
        return 0

    if args.cmd == "summary":
        lessons = read_lessons(Path(args.ledger))
        Path(args.out_md).write_text(
            render_lessons_md(lessons), encoding="utf-8",
        )
        print(f"[trinity_error_memory] wrote {args.out_md} "
              f"({len(lessons)} lessons)")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
