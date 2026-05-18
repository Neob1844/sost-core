#!/usr/bin/env python3
"""Trinity Task Queue Autopilot v0.1 (Sprint 5.38).

Bounded orchestrator that repeatedly drives the existing Sprint
5.27 ``task_queue.run_batch`` and the Sprint 5.28
``task_queue_dashboard.build_dashboard`` until the queue is
drained, a failure trips the stop, or the bounded batch budget is
reached. The autopilot is the friendly semi-autonomous driver
that lets a single operator stand up a workday's worth of Trinity
Useful Compute work without hand-cranking each batch + dashboard.

Hard invariants v0.1 (enforced by static tests):
    - No infinite loop. ``--max-batches`` is mandatory and capped
      at 24; anything higher is refused at argv parse time.
    - No network. No DNS. No child process.
    - No wallet, no private key, no signing, no broadcast.
    - No autonomous payment. No reward primitive.
    - Local-dry-run only. The autopilot calls ``run_batch`` which
      itself re-asserts the dry-run lock.
    - Stops early when the queue has zero pending items.

Usage:
    python3 scripts/trinity/task_queue_autopilot.py run-autopilot \\
        --queue-dir /var/lib/trinity/queues/main \\
        --max-batches 4 \\
        --max-items-per-batch 8 \\
        --pinned-time 2026-05-18T00:00:00+00:00 \\
        --dashboard-out-dir /var/lib/trinity/dashboards \\
        [--stop-on-failure]

Output:
    JSON report at
    <queue-dir>/reports/_autopilot/
        TRINITY_TASK_QUEUE_AUTOPILOT_REPORT_<autopilot_id>.json
    schema: ``trinity-task-queue-autopilot-report/v0.1``
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_AUTOPILOT_REPORT = "trinity-task-queue-autopilot-report/v0.1"

# Hard caps. Refuse anything higher at argv parse time.
AUTOPILOT_MAX_BATCHES_CAP = 24
AUTOPILOT_MAX_ITEMS_PER_BATCH_CAP = 50  # mirrors task_queue.RUNNER_MAX_BATCH


class AutopilotError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(path))


# ---------------------------------------------------------------------------
# Sibling-module access (deliberate, narrow)
# ---------------------------------------------------------------------------


def _import_task_queue():
    """Import task_queue module (already in this repo)."""
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import task_queue as _tq  # type: ignore
    return _tq


def _import_dashboard():
    """Import task_queue_dashboard module."""
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    import task_queue_dashboard as _dash  # type: ignore
    return _dash


# ---------------------------------------------------------------------------
# Queue counts helper (read-only)
# ---------------------------------------------------------------------------


def _read_queue_counts(queue_dir: Path) -> Dict[str, int]:
    """Read queue.json + count items per status without touching
    the runner. Returns a {pending, running, completed, failed} dict
    (zeros when queue.json is missing or malformed)."""
    counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
    queue_json = queue_dir / "queue.json"
    if not queue_json.exists():
        return counts
    try:
        with open(queue_json, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return counts
    for it in data.get("items", []) or []:
        s = it.get("status")
        if isinstance(s, str) and s in counts:
            counts[s] += 1
    return counts


# ---------------------------------------------------------------------------
# Autopilot core
# ---------------------------------------------------------------------------


def run_autopilot(
    *,
    queue_dir: Path,
    max_batches: int,
    max_items_per_batch: int,
    pinned_time: str,
    dashboard_out_dir: Path,
    stop_on_failure: bool = False,
) -> Dict[str, Any]:
    """Drive run_batch + dashboard up to ``max_batches`` times.

    Stops early when:
        - the queue has zero pending items (after a batch attempt
          returned attempted_count == 0), OR
        - stop_on_failure is True and a batch ends with safety_status
          == "failed", OR
        - the bounded batch budget is exhausted.

    Returns the autopilot report dict (also written to disk under
    ``<queue-dir>/reports/_autopilot/``).
    """
    queue_dir = Path(queue_dir)
    dashboard_out_dir = Path(dashboard_out_dir)

    if not isinstance(max_batches, int) or not (
        1 <= max_batches <= AUTOPILOT_MAX_BATCHES_CAP
    ):
        raise AutopilotError(
            "max-batches must be int in [1, "
            + str(AUTOPILOT_MAX_BATCHES_CAP)
            + "]; got " + repr(max_batches)
        )
    if not isinstance(max_items_per_batch, int) or not (
        1 <= max_items_per_batch <= AUTOPILOT_MAX_ITEMS_PER_BATCH_CAP
    ):
        raise AutopilotError(
            "max-items-per-batch must be int in [1, "
            + str(AUTOPILOT_MAX_ITEMS_PER_BATCH_CAP)
            + "]; got " + repr(max_items_per_batch)
        )

    if not queue_dir.is_dir():
        raise AutopilotError(
            "queue-dir does not exist: " + str(queue_dir)
        )
    dashboard_out_dir.mkdir(parents=True, exist_ok=True)

    tq = _import_task_queue()
    dash = _import_dashboard()

    warnings: List[str] = []
    per_batch: List[Dict[str, Any]] = []
    dashboard_basenames: List[str] = []
    batches_attempted = 0
    batches_succeeded = 0
    batches_failed = 0
    items_completed = 0
    items_failed = 0
    stopped_reason = "max_batches_reached"

    for batch_idx in range(max_batches):
        batches_attempted += 1
        per_batch_pinned = pinned_time  # bounded — operator-supplied
        try:
            batch_report = tq.run_batch(
                queue_dir=queue_dir,
                max_items=max_items_per_batch,
                pinned_time=per_batch_pinned,
                stop_on_failure=stop_on_failure,
            )
        except tq.QueueError as exc:
            warnings.append(
                "batch " + str(batch_idx) + " refused by task_queue: "
                + str(exc)
            )
            batches_failed += 1
            stopped_reason = "task_queue_error"
            break

        batch_safety = str(batch_report.get("safety_status", "warning"))
        batch_summary = {
            "batch_index":     batch_idx,
            "batch_id":        str(batch_report.get("batch_id", "")),
            "attempted_count": int(batch_report.get("attempted_count", 0)),
            "completed_count": int(batch_report.get("completed_count", 0)),
            "failed_count":    int(batch_report.get("failed_count", 0)),
            "safety_status":   batch_safety,
        }
        per_batch.append(batch_summary)
        items_completed += batch_summary["completed_count"]
        items_failed    += batch_summary["failed_count"]
        if batch_safety == "ok":
            batches_succeeded += 1
        elif batch_safety in ("warning", "failed"):
            batches_failed += 1
            if batch_safety != "ok":
                warnings.append(
                    "batch " + batch_summary["batch_id"]
                    + " safety_status=" + batch_safety
                )

        # Build a fresh dashboard after every batch.
        try:
            dash_obj = dash.build_dashboard(
                queue_dir=queue_dir,
                pinned_time=per_batch_pinned,
            )
            dash_path = (
                dashboard_out_dir / (
                    "TRINITY_TASK_QUEUE_DASHBOARD_"
                    + dash_obj["dashboard_id"] + ".json"
                )
            )
            _atomic_write_json(dash_path, dash_obj)
            dash_html = dash.render_html(dash_obj)
            (dash_path.with_suffix(".html")).write_text(
                dash_html, encoding="utf-8",
            )
            dashboard_basenames.append(dash_path.name)
        except Exception as exc:  # pragma: no cover - defensive
            warnings.append(
                "dashboard build failed after batch "
                + batch_summary["batch_id"] + ": " + repr(exc)
            )

        if stop_on_failure and batch_safety == "failed":
            stopped_reason = "stop_on_failure"
            break

        # Early exit: queue drained.
        if batch_summary["attempted_count"] == 0:
            stopped_reason = "queue_empty"
            break

    final_counts = _read_queue_counts(queue_dir)
    final_counts_total = (
        final_counts["pending"]
        + final_counts["running"]
        + final_counts["completed"]
        + final_counts["failed"]
    )

    if items_failed > 0 or batches_failed > 0:
        safety_status = "warning"
    else:
        safety_status = "ok"
    if any(b["safety_status"] == "failed" for b in per_batch):
        safety_status = "failed"

    autopilot_id = "tap-" + _sha16(_canonical_dumps({
        "pinned_time":         pinned_time,
        "queue_dir_basename":  queue_dir.name,
        "max_batches":         max_batches,
        "max_items_per_batch": max_items_per_batch,
        "stop_on_failure":     bool(stop_on_failure),
        "batches":             [b["batch_id"] for b in per_batch],
    }))

    report: Dict[str, Any] = {
        "schema": SCHEMA_AUTOPILOT_REPORT,
        "autopilot_id": autopilot_id,
        "pinned_time": pinned_time,
        "queue_dir_basename": queue_dir.name,
        "max_batches": int(max_batches),
        "max_items_per_batch": int(max_items_per_batch),
        "stop_on_failure": bool(stop_on_failure),
        "batches_attempted": int(batches_attempted),
        "batches_succeeded": int(batches_succeeded),
        "batches_failed":    int(batches_failed),
        "items_completed":   int(items_completed),
        "items_failed":      int(items_failed),
        "final_queue_counts": {
            "pending":   int(final_counts["pending"]),
            "running":   int(final_counts["running"]),
            "completed": int(final_counts["completed"]),
            "failed":    int(final_counts["failed"]),
            "total":     int(final_counts_total),
        },
        "per_batch": per_batch,
        "dashboard_paths": dashboard_basenames,
        "latest_dashboard_basename": (
            dashboard_basenames[-1] if dashboard_basenames else ""
        ),
        "stopped_reason": stopped_reason,
        "safety_status": safety_status,
        "warnings": warnings,
        "safety_flags": {
            "no_wallet":               True,
            "no_private_key":          True,
            "no_signing":              True,
            "no_broadcast":            True,
            "no_autonomous_payment":   True,
            "no_network":              True,
            "local_dry_run_only":      True,
        },
    }

    report_dir = queue_dir / "reports" / "_autopilot"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / (
        "TRINITY_TASK_QUEUE_AUTOPILOT_REPORT_" + autopilot_id + ".json"
    )
    _atomic_write_json(report_path, report)
    report["_report_path"] = str(report_path)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="task_queue_autopilot",
        description=(
            "Trinity Task Queue Autopilot v0.1. Bounded driver "
            "over run_batch + dashboard. NEVER touches a wallet, "
            "NEVER signs, NEVER broadcasts, NEVER pays autonomously."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)
    p_run = sub.add_parser(
        "run-autopilot",
        help="Run up to --max-batches bounded batches then stop.",
    )
    p_run.add_argument("--queue-dir", required=True)
    p_run.add_argument("--max-batches", type=int, required=True)
    p_run.add_argument("--max-items-per-batch", type=int, required=True)
    p_run.add_argument("--pinned-time", required=True)
    p_run.add_argument("--dashboard-out-dir", required=True)
    p_run.add_argument(
        "--stop-on-failure", action="store_true",
        help="Stop at the first batch with safety_status=failed.",
    )
    return p


def _cmd_run_autopilot(args) -> int:
    try:
        report = run_autopilot(
            queue_dir=Path(args.queue_dir),
            max_batches=args.max_batches,
            max_items_per_batch=args.max_items_per_batch,
            pinned_time=args.pinned_time,
            dashboard_out_dir=Path(args.dashboard_out_dir),
            stop_on_failure=bool(args.stop_on_failure),
        )
    except AutopilotError as exc:
        print(
            "[task_queue_autopilot] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    print(
        "[task_queue_autopilot] autopilot_id=" + report["autopilot_id"]
        + " batches_attempted=" + str(report["batches_attempted"])
        + " items_completed=" + str(report["items_completed"])
        + " items_failed=" + str(report["items_failed"])
        + " safety_status=" + report["safety_status"]
        + " stopped_reason=" + report["stopped_reason"]
        + " report=" + str(report.get("_report_path", ""))
    )
    return 0


COMMANDS = {
    "run-autopilot": _cmd_run_autopilot,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
