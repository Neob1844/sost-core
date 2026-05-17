#!/usr/bin/env python3
"""Trinity Task Queue v0.1 (Sprint 5.26).

A deterministic, local-only task queue for Trinity Useful Compute
requests. The queue is the first step from manual one-shot operator
runs toward autonomous operation, while staying fully dry-run,
Governor-observed (Sprint 5.24) and Watchdog-visible (Sprint 5.25).

Hard invariants v0.1 (enforced by static tests):
    - Local-dry-run only. The queue runner invokes the operator
      loop with --mode local-dry-run and the explicit confirmation
      token. Any other mode is refused at startup.
    - No wallet, no private-key handling, no signing, no
      broadcasting, no chain CLI. The queue never imports those
      modules and the static safety test grep rejects the tokens.
    - No shell. Subprocess calls always pass an explicit argv
      list and never enable shell interpretation.
    - Fail closed on Governor hard-block. If the operator loop
      exits with rc=3 (halt_file_present or
      policy_mutated_at_runtime), the queue item is marked failed
      with last_error explaining the block. No retry inside the
      same run-once call.
    - Fail closed on Watchdog critical. After a completed
      operator run, the watchdog scans the decisions dir. If the
      report's safety_status is "critical", the queue item is
      marked failed regardless of the operator loop's exit code.

Queue layout:
    queue-dir/
        queue.json                ← top-level state, schema-validated
        pending/<id>.json         ← queue items waiting to run
        running/<id>.json         ← in-flight items
        completed/<id>.json       ← completed items + audit paths
        failed/<id>.json          ← failed items + last_error
        reports/<id>/
            operator_run/         ← --out-dir of the operator loop
                operator_run.json
                governor_decisions/...
            watchdog/             ← --out-dir of the watchdog
                TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os.path
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_QUEUE = "trinity-task-queue/v0.1"
SCHEMA_ITEM = "trinity-task-queue-item/v0.1"
SCHEMA_RUNNER_REPORT = "trinity-task-queue-runner-report/v0.1"
ALLOWED_MODE = "local-dry-run"
CONFIRMATION_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP"
DEFAULT_MAX_ATTEMPTS = 3
GOVERNOR_HARD_BLOCK_RC = 3

# Sprint 5.27 — Task Queue Runner v0.1
RUNNER_MIN_BATCH = 1
RUNNER_MAX_BATCH = 50
RUNNER_MAX_SLEEP_SECONDS = 3600

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUSES = (STATUS_PENDING, STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED)


class QueueError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _ensure_local_dry_run(mode: str) -> None:
    if mode != ALLOWED_MODE:
        raise QueueError(
            "task_queue v0.1 only allows --mode " + repr(ALLOWED_MODE)
            + "; got " + repr(mode)
        )


def _atomic_write_json(path: Path, obj: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(str(tmp), str(path))


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Queue directory operations
# ---------------------------------------------------------------------------


def queue_paths(queue_dir: Path) -> Dict[str, Path]:
    queue_dir = Path(queue_dir)
    return {
        "root": queue_dir,
        "queue_json": queue_dir / "queue.json",
        STATUS_PENDING: queue_dir / "pending",
        STATUS_RUNNING: queue_dir / "running",
        STATUS_COMPLETED: queue_dir / "completed",
        STATUS_FAILED: queue_dir / "failed",
        "reports": queue_dir / "reports",
    }


def _item_path(queue_dir: Path, status: str, item_id: str) -> Path:
    paths = queue_paths(queue_dir)
    if status not in STATUSES:
        raise QueueError("unknown status: " + repr(status))
    return paths[status] / (item_id + ".json")


def init_queue(queue_dir: Path, pinned_time: str) -> Dict[str, Any]:
    """Create the queue directory and queue.json. Idempotent: a
    second init against an existing queue is refused (we never
    overwrite an existing queue.json)."""
    queue_dir = Path(queue_dir)
    paths = queue_paths(queue_dir)
    if paths["queue_json"].exists():
        raise QueueError(
            "queue.json already exists in " + str(queue_dir)
            + "; refusing to re-init. Delete the dir first if you "
            + "really mean to start over."
        )
    queue_dir.mkdir(parents=True, exist_ok=True)
    for s in STATUSES:
        paths[s].mkdir(parents=True, exist_ok=True)
    paths["reports"].mkdir(parents=True, exist_ok=True)
    queue = {
        "schema": SCHEMA_QUEUE,
        "queue_id": "tq-" + _sha16(_canonical_dumps({
            "pinned_time": pinned_time,
            "queue_dir_basename": queue_dir.name,
        })),
        "queue_dir_basename": queue_dir.name,
        "created_at": pinned_time,
        "updated_at": pinned_time,
        "items": [],
    }
    _atomic_write_json(paths["queue_json"], queue)
    return queue


def _read_queue(queue_dir: Path) -> Dict[str, Any]:
    paths = queue_paths(queue_dir)
    if not paths["queue_json"].exists():
        raise QueueError(
            "queue not initialised: " + str(paths["queue_json"])
            + " missing. Run task_queue.py init first."
        )
    return _read_json(paths["queue_json"])


def _save_queue(queue_dir: Path, queue: Dict[str, Any]) -> None:
    paths = queue_paths(queue_dir)
    queue["updated_at"] = _utc_now()
    _atomic_write_json(paths["queue_json"], queue)


def _index_update(queue: Dict[str, Any], item: Dict[str, Any]) -> None:
    """Insert or update one item's index entry inside queue["items"]."""
    found = False
    for idx in queue["items"]:
        if idx["queue_item_id"] == item["queue_item_id"]:
            idx["status"] = item["status"]
            idx["updated_at"] = item["updated_at"]
            found = True
            break
    if not found:
        queue["items"].append({
            "queue_item_id": item["queue_item_id"],
            "status": item["status"],
            "created_at": item["created_at"],
            "updated_at": item["updated_at"],
        })


def enqueue_item(
    queue_dir: Path,
    request_json: Path,
    worker_address_map: Path,
    governor_policy: Path,
    pinned_time: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Dict[str, Any]:
    """Add one item to the queue. Returns the created item dict."""
    queue_dir = Path(queue_dir)
    request_json = Path(request_json).resolve()
    worker_address_map = Path(worker_address_map).resolve()
    governor_policy = Path(governor_policy).resolve()

    for label, p in (
        ("request-json", request_json),
        ("worker-address-map", worker_address_map),
        ("governor-policy", governor_policy),
    ):
        if not p.exists():
            raise QueueError(
                label + " not found: " + str(p)
            )

    request_sha = _sha256_file(request_json)
    policy_sha = _sha256_file(governor_policy)
    queue_item_id = "qit-" + _sha16(_canonical_dumps({
        "pinned_time": pinned_time,
        "request_sha256": request_sha,
        "policy_sha256": policy_sha,
        "worker_address_map_basename": worker_address_map.name,
    }))

    queue = _read_queue(queue_dir)
    # Refuse duplicate enqueue of the same id.
    for idx in queue["items"]:
        if idx["queue_item_id"] == queue_item_id:
            raise QueueError(
                "queue item " + queue_item_id + " already exists "
                + "(status=" + idx["status"] + "). Refusing to "
                + "enqueue a duplicate."
            )

    item: Dict[str, Any] = {
        "schema": SCHEMA_ITEM,
        "queue_item_id": queue_item_id,
        "request_json_path": str(request_json),
        "worker_address_map_path": str(worker_address_map),
        "governor_policy_path": str(governor_policy),
        "request_json_path_basename": request_json.name,
        "worker_address_map_path_basename": worker_address_map.name,
        "governor_policy_path_basename": governor_policy.name,
        "status": STATUS_PENDING,
        "created_at": pinned_time,
        "updated_at": pinned_time,
        "pinned_time": pinned_time,
        "attempt_count": 0,
        "max_attempts": int(max_attempts),
        "last_error": None,
        "operator_run_path": None,
        "watchdog_report_path": None,
        "policy_sha256": policy_sha,
        "request_sha256": request_sha,
        "threat_refs": [],
        "governor_decisions_count": 0,
        "watchdog_safety_status": None,
    }
    _atomic_write_json(
        _item_path(queue_dir, STATUS_PENDING, queue_item_id), item,
    )
    _index_update(queue, item)
    _save_queue(queue_dir, queue)
    return item


def list_items(queue_dir: Path) -> Dict[str, Any]:
    queue = _read_queue(queue_dir)
    counts = {s: 0 for s in STATUSES}
    for idx in queue["items"]:
        counts[idx["status"]] = counts.get(idx["status"], 0) + 1
    return {
        "queue_id": queue["queue_id"],
        "queue_dir_basename": queue["queue_dir_basename"],
        "counts": counts,
        "items": queue["items"],
    }


def inspect_item(queue_dir: Path, item_id: str) -> Dict[str, Any]:
    for s in STATUSES:
        p = _item_path(queue_dir, s, item_id)
        if p.exists():
            return _read_json(p)
    raise QueueError(
        "queue item not found in any status dir: " + item_id
    )


def _move_item(
    queue_dir: Path, item: Dict[str, Any],
    from_status: str, to_status: str,
) -> None:
    """Move a queue item file from one status dir to another and
    update its status field on disk. Atomic at the rename step."""
    item_id = item["queue_item_id"]
    item["status"] = to_status
    item["updated_at"] = _utc_now()
    new_path = _item_path(queue_dir, to_status, item_id)
    # Write the new file first, then unlink the old. Two reads will
    # briefly see the item in both dirs — that is acceptable because
    # the queue.json index is the authoritative status, not the
    # filesystem layout.
    _atomic_write_json(new_path, item)
    old_path = _item_path(queue_dir, from_status, item_id)
    if old_path.exists() and old_path != new_path:
        os.remove(str(old_path))


# ---------------------------------------------------------------------------
# Subprocess wrappers (explicit argv, shell never invoked)
# ---------------------------------------------------------------------------


def _run_operator_loop(
    item: Dict[str, Any], operator_out_dir: Path,
) -> Tuple[int, str]:
    """Invoke useful_compute_operator_loop.py via subprocess with
    an explicit argv list. Returns (rc, combined_output)."""
    scripts_dir = Path(__file__).resolve().parent
    operator_loop = scripts_dir / "useful_compute_operator_loop.py"
    if not operator_loop.exists():
        raise QueueError(
            "operator_loop script missing: " + str(operator_loop)
        )
    argv = [
        sys.executable,
        str(operator_loop),
        "--mode", ALLOWED_MODE,
        "--require-confirmation-token", CONFIRMATION_TOKEN,
        "--out-dir", str(operator_out_dir),
        "--pinned-time", item["pinned_time"],
        "--request-json", item["request_json_path"],
        "--worker-address-map", item["worker_address_map_path"],
        "--governor-policy", item["governor_policy_path"],
    ]
    proc = subprocess.run(
        argv, capture_output=True, text=True, check=False,
    )
    return proc.returncode, (proc.stdout + proc.stderr)


def _run_watchdog(
    item: Dict[str, Any],
    decisions_dir: Path,
    watchdog_out_dir: Path,
) -> Tuple[int, Optional[Path], str]:
    """Invoke governor_watchdog.py via subprocess. Returns
    (rc, report_path_or_None, combined_output)."""
    scripts_dir = Path(__file__).resolve().parent
    watchdog = scripts_dir / "governor_watchdog.py"
    if not watchdog.exists():
        raise QueueError(
            "watchdog script missing: " + str(watchdog)
        )
    argv = [
        sys.executable,
        str(watchdog),
        "--decisions-dir", str(decisions_dir),
        "--out-dir", str(watchdog_out_dir),
        "--pinned-time", item["pinned_time"],
    ]
    proc = subprocess.run(
        argv, capture_output=True, text=True, check=False,
    )
    report = None
    if proc.returncode == 0:
        reports = sorted(
            watchdog_out_dir.glob(
                "TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json",
            )
        )
        if reports:
            report = reports[-1]
    return proc.returncode, report, (proc.stdout + proc.stderr)


# ---------------------------------------------------------------------------
# run-once
# ---------------------------------------------------------------------------


def run_once(queue_dir: Path) -> Optional[Dict[str, Any]]:
    """Pick the oldest pending item, run the operator loop +
    watchdog under it, and move it to completed or failed.
    Returns the resulting item dict, or None when the queue has
    no pending items."""
    queue = _read_queue(queue_dir)
    pending_ids = [
        idx["queue_item_id"]
        for idx in queue["items"]
        if idx["status"] == STATUS_PENDING
    ]
    if not pending_ids:
        return None

    # Oldest first by created_at; the index is already created in
    # enqueue order so a stable sort by created_at is enough.
    pending_ids.sort(
        key=lambda i: next(
            x["created_at"]
            for x in queue["items"]
            if x["queue_item_id"] == i
        )
    )
    item_id = pending_ids[0]
    item = _read_json(_item_path(queue_dir, STATUS_PENDING, item_id))
    _ensure_local_dry_run(ALLOWED_MODE)

    item["attempt_count"] = int(item.get("attempt_count", 0)) + 1
    _move_item(queue_dir, item, STATUS_PENDING, STATUS_RUNNING)
    _index_update(queue, item)
    _save_queue(queue_dir, queue)

    report_dir = queue_paths(queue_dir)["reports"] / item_id
    operator_out_dir = report_dir / "operator_run"
    watchdog_out_dir = report_dir / "watchdog"
    operator_out_dir.mkdir(parents=True, exist_ok=True)
    watchdog_out_dir.mkdir(parents=True, exist_ok=True)

    rc, op_output = _run_operator_loop(item, operator_out_dir)

    if rc == GOVERNOR_HARD_BLOCK_RC:
        item["last_error"] = (
            "governor_hard_block: operator_loop exited rc=3 "
            "(halt_file_present or policy_mutated_at_runtime). "
            "Refusing to continue. See operator_run output: "
            + op_output[-400:]
        )
        _move_item(queue_dir, item, STATUS_RUNNING, STATUS_FAILED)
        _index_update(queue, item)
        _save_queue(queue_dir, queue)
        return item

    if rc != 0:
        item["last_error"] = (
            "operator_loop exited rc=" + str(rc)
            + ". Output tail: " + op_output[-400:]
        )
        _move_item(queue_dir, item, STATUS_RUNNING, STATUS_FAILED)
        _index_update(queue, item)
        _save_queue(queue_dir, queue)
        return item

    # Operator loop succeeded — read its state to harvest the
    # governor stats. The schema invariants are already enforced by
    # the operator loop tests; we just lift the relevant fields.
    op_state_path = operator_out_dir / "operator_run.json"
    if not op_state_path.exists():
        item["last_error"] = (
            "operator_loop exited 0 but operator_run.json is "
            "missing at " + str(op_state_path)
        )
        _move_item(queue_dir, item, STATUS_RUNNING, STATUS_FAILED)
        _index_update(queue, item)
        _save_queue(queue_dir, queue)
        return item
    op_state = _read_json(op_state_path)
    item["operator_run_path"] = str(op_state_path)
    item["governor_decisions_count"] = int(
        op_state.get("governor_decisions_count", 0)
    )

    # Run the watchdog over the decisions dir the operator loop
    # produced. The decisions live at operator_out_dir/governor_decisions
    # by operator_loop default.
    decisions_dir = operator_out_dir / "governor_decisions"
    if not decisions_dir.exists():
        item["last_error"] = (
            "operator_loop completed but governor_decisions/ "
            "missing — governor hook was not enabled. Did the "
            "policy file get stripped between enqueue and run?"
        )
        _move_item(queue_dir, item, STATUS_RUNNING, STATUS_FAILED)
        _index_update(queue, item)
        _save_queue(queue_dir, queue)
        return item

    wd_rc, wd_report, wd_output = _run_watchdog(
        item, decisions_dir, watchdog_out_dir,
    )
    if wd_rc != 0 or wd_report is None:
        item["last_error"] = (
            "watchdog exited rc=" + str(wd_rc)
            + " or wrote no report. Output tail: "
            + wd_output[-400:]
        )
        _move_item(queue_dir, item, STATUS_RUNNING, STATUS_FAILED)
        _index_update(queue, item)
        _save_queue(queue_dir, queue)
        return item

    report = _read_json(wd_report)
    item["watchdog_report_path"] = str(wd_report)
    item["watchdog_safety_status"] = report.get("safety_status")
    item["threat_refs"] = sorted(report.get("threat_refs_seen", []))

    if report.get("safety_status") == "critical":
        item["last_error"] = (
            "watchdog reported safety_status=critical: "
            "halt_detected_count="
            + str(report.get("halt_detected_count", 0))
            + " policy_mutation_detected_count="
            + str(report.get("policy_mutation_detected_count", 0))
            + ". Fail-closed per task_queue v0.1 contract."
        )
        _move_item(queue_dir, item, STATUS_RUNNING, STATUS_FAILED)
        _index_update(queue, item)
        _save_queue(queue_dir, queue)
        return item

    # All clear.
    item["last_error"] = None
    _move_item(queue_dir, item, STATUS_RUNNING, STATUS_COMPLETED)
    _index_update(queue, item)
    _save_queue(queue_dir, queue)
    return item


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _schema_path() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "schemas" / "trinity"
        / "task_queue.schema.json"
    )


def _validate_with_schema(obj: Dict[str, Any], schema: Dict[str, Any]) -> None:
    try:
        import jsonschema  # local import keeps stdlib-only path possible
    except ImportError as exc:
        raise QueueError(
            "jsonschema not available: " + str(exc)
        )
    jsonschema.validate(obj, schema)


def validate_queue_tree(queue_dir: Path) -> Dict[str, Any]:
    """Validate queue.json and every per-status item file against
    the v0.1 schema. Returns a small summary; raises QueueError on
    the first failure."""
    queue = _read_queue(queue_dir)
    schema = _read_json(_schema_path())
    item_schema = schema["$defs"]["queue_item"]
    _validate_with_schema(queue, schema)
    items_checked = 0
    for s in STATUSES:
        d = queue_paths(queue_dir)[s]
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            obj = _read_json(f)
            _validate_with_schema(obj, item_schema)
            items_checked += 1
    return {
        "queue_id": queue["queue_id"],
        "items_in_index": len(queue["items"]),
        "items_on_disk_validated": items_checked,
    }


# ---------------------------------------------------------------------------
# Sprint 5.27 — Task Queue Runner v0.1 (bounded wrapper over run_once)
# ---------------------------------------------------------------------------


def _runner_report_default_path(queue_dir: Path, batch_id: str) -> Path:
    return (
        queue_paths(queue_dir)["reports"] / "_batches"
        / ("TRINITY_TASK_QUEUE_RUNNER_REPORT_" + batch_id + ".json")
    )


def run_batch(
    queue_dir: Path,
    max_items: int,
    pinned_time: str,
    stop_on_failure: bool = False,
    sleep_seconds: int = 0,
    report_path: Optional[Path] = None,
    _sleep_hook=None,
) -> Dict[str, Any]:
    """Bounded wrapper over run_once(). Processes up to ``max_items``
    pending items (oldest first via the existing run_once selection),
    records each outcome, and writes a deterministic batch report
    JSON. Never duplicates the operator_loop / watchdog logic — it
    just calls run_once() in a bounded loop.

    Args:
        queue_dir: queue directory created by init_queue.
        max_items: 1 .. 50.  Hard-bounded.
        pinned_time: ISO string. Goes into batch_id and the report.
        stop_on_failure: when True, halt at the first failed item.
            safety_status becomes "failed" if any item failed under
            this flag.
        sleep_seconds: 0 .. 3600. Optional inter-item delay. 0 by
            default; the runner is not a daemon.
        report_path: optional explicit output path for the JSON
            report. Default: queue_dir/reports/_batches/
            TRINITY_TASK_QUEUE_RUNNER_REPORT_<batch_id>.json.
        _sleep_hook: test-only hook that replaces time.sleep with
            a callable so tests can assert sleep was called without
            actually sleeping. Internal; not exposed via CLI.

    Returns:
        the batch report dict (also written to disk).
    """
    queue_dir = Path(queue_dir)
    if not isinstance(max_items, int) or not (
        RUNNER_MIN_BATCH <= max_items <= RUNNER_MAX_BATCH
    ):
        raise QueueError(
            "max-items must be an integer in ["
            + str(RUNNER_MIN_BATCH) + ", " + str(RUNNER_MAX_BATCH)
            + "]; got " + repr(max_items)
        )
    if not isinstance(sleep_seconds, int) or not (
        0 <= sleep_seconds <= RUNNER_MAX_SLEEP_SECONDS
    ):
        raise QueueError(
            "sleep-seconds must be an integer in [0, "
            + str(RUNNER_MAX_SLEEP_SECONDS) + "]; got "
            + repr(sleep_seconds)
        )
    # Mode lock — same check that fires inside run_once. We re-assert
    # here so the runner refuses to even start if a future caller
    # tries to fan in a non-local-dry-run mode override.
    _ensure_local_dry_run(ALLOWED_MODE)

    # Ensure the queue exists and is readable before we record the
    # batch (a missing queue should not produce a half-written
    # report under the default path).
    _read_queue(queue_dir)

    item_ids: List[str] = []
    completed_item_ids: List[str] = []
    failed_item_ids: List[str] = []
    warnings: List[str] = []
    attempted = 0
    stopped_early = False

    for i in range(int(max_items)):
        result = run_once(queue_dir)
        if result is None:
            # No more pending items. attempted_count tracks what we
            # actually tried; skipped_count below is computed from
            # the difference.
            break
        attempted += 1
        item_ids.append(result["queue_item_id"])
        if result["status"] == STATUS_COMPLETED:
            completed_item_ids.append(result["queue_item_id"])
        elif result["status"] == STATUS_FAILED:
            failed_item_ids.append(result["queue_item_id"])
            err = result.get("last_error") or "(no last_error)"
            warnings.append(
                "item " + result["queue_item_id"]
                + " failed: " + err[:300]
            )
            if stop_on_failure:
                stopped_early = True
                break
        else:
            warnings.append(
                "item " + result["queue_item_id"]
                + " ended in unexpected status: "
                + str(result.get("status"))
            )

        if sleep_seconds > 0 and (i + 1) < int(max_items):
            if _sleep_hook is not None:
                _sleep_hook(sleep_seconds)
            else:
                import time as _time
                _time.sleep(sleep_seconds)

    skipped_count = int(max_items) - attempted
    if skipped_count < 0:
        skipped_count = 0

    if stopped_early:
        safety_status = "failed"
    elif failed_item_ids:
        safety_status = "warning"
    else:
        safety_status = "ok"

    batch_id = "tqr-" + _sha16(_canonical_dumps({
        "pinned_time": pinned_time,
        "queue_dir_basename": queue_dir.name,
        "max_items": int(max_items),
        "stop_on_failure": bool(stop_on_failure),
        "item_ids": item_ids,
    }))

    report: Dict[str, Any] = {
        "schema": SCHEMA_RUNNER_REPORT,
        "batch_id": batch_id,
        "pinned_time": pinned_time,
        "queue_dir_basename": queue_dir.name,
        "max_items": int(max_items),
        "attempted_count": attempted,
        "completed_count": len(completed_item_ids),
        "failed_count": len(failed_item_ids),
        "skipped_count": skipped_count,
        "stop_on_failure": bool(stop_on_failure),
        "sleep_seconds": int(sleep_seconds),
        "item_ids": item_ids,
        "completed_item_ids": completed_item_ids,
        "failed_item_ids": failed_item_ids,
        "safety_status": safety_status,
        "warnings": warnings,
    }

    if report_path is None:
        report_path = _runner_report_default_path(queue_dir, batch_id)
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(report_path, report)
    report["_report_path"] = str(report_path)
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="task_queue",
        description=(
            "Trinity Task Queue v0.1. Local-dry-run only. NEVER "
            "touches a wallet, NEVER signs, NEVER broadcasts."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new queue.")
    p_init.add_argument("--queue-dir", required=True)
    p_init.add_argument("--pinned-time", default=None)

    p_enq = sub.add_parser("enqueue", help="Add one item to the queue.")
    p_enq.add_argument("--queue-dir", required=True)
    p_enq.add_argument("--request-json", required=True)
    p_enq.add_argument("--worker-address-map", required=True)
    p_enq.add_argument("--governor-policy", required=True)
    p_enq.add_argument("--pinned-time", required=True)
    p_enq.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)

    p_list = sub.add_parser("list", help="Print queue state.")
    p_list.add_argument("--queue-dir", required=True)

    p_run = sub.add_parser(
        "run-once",
        help="Run the oldest pending item through operator_loop + watchdog.",
    )
    p_run.add_argument("--queue-dir", required=True)

    p_ins = sub.add_parser("inspect", help="Print one queue item JSON.")
    p_ins.add_argument("--queue-dir", required=True)
    p_ins.add_argument("--queue-item-id", required=True)

    p_val = sub.add_parser(
        "validate", help="Validate queue.json + items against the schema.",
    )
    p_val.add_argument("--queue-dir", required=True)

    p_batch = sub.add_parser(
        "run-batch",
        help=(
            "Run up to --max-items pending items through "
            "operator_loop + watchdog and write a batch report."
        ),
    )
    p_batch.add_argument("--queue-dir", required=True)
    p_batch.add_argument(
        "--max-items", type=int, required=True,
        help="1..50. Hard bound; the runner is not a daemon.",
    )
    p_batch.add_argument("--pinned-time", required=True)
    p_batch.add_argument(
        "--stop-on-failure", action="store_true",
        help=(
            "Halt at the first failed item. safety_status becomes "
            "'failed' when any item failed under this flag."
        ),
    )
    p_batch.add_argument(
        "--sleep-seconds", type=int, default=0,
        help="0..3600. Inter-item delay. Default 0 (no sleep).",
    )
    p_batch.add_argument(
        "--report-path", default=None,
        help=(
            "Optional explicit output path for the batch report "
            "JSON. Default: <queue-dir>/reports/_batches/"
            "TRINITY_TASK_QUEUE_RUNNER_REPORT_<batch_id>.json."
        ),
    )

    return p


def _cmd_init(args) -> int:
    pinned = args.pinned_time or _utc_now()
    try:
        q = init_queue(Path(args.queue_dir), pinned)
    except QueueError as exc:
        print("[task_queue] error: " + str(exc), file=sys.stderr)
        return 2
    print(
        "[task_queue] init queue_id=" + q["queue_id"]
        + " queue_dir=" + q["queue_dir_basename"]
    )
    return 0


def _cmd_enqueue(args) -> int:
    try:
        item = enqueue_item(
            queue_dir=Path(args.queue_dir),
            request_json=Path(args.request_json),
            worker_address_map=Path(args.worker_address_map),
            governor_policy=Path(args.governor_policy),
            pinned_time=args.pinned_time,
            max_attempts=int(args.max_attempts),
        )
    except QueueError as exc:
        print("[task_queue] error: " + str(exc), file=sys.stderr)
        return 2
    print(
        "[task_queue] enqueued queue_item_id=" + item["queue_item_id"]
        + " request_sha256=" + item["request_sha256"][:16]
        + " policy_sha256=" + item["policy_sha256"][:16]
        + " status=" + item["status"]
    )
    return 0


def _cmd_list(args) -> int:
    try:
        view = list_items(Path(args.queue_dir))
    except QueueError as exc:
        print("[task_queue] error: " + str(exc), file=sys.stderr)
        return 2
    counts = view["counts"]
    print(
        "[task_queue] queue_id=" + view["queue_id"]
        + " pending=" + str(counts.get(STATUS_PENDING, 0))
        + " running=" + str(counts.get(STATUS_RUNNING, 0))
        + " completed=" + str(counts.get(STATUS_COMPLETED, 0))
        + " failed=" + str(counts.get(STATUS_FAILED, 0))
    )
    for idx in view["items"]:
        print(
            "  " + idx["queue_item_id"]
            + " status=" + idx["status"]
            + " updated_at=" + idx["updated_at"]
        )
    return 0


def _cmd_run_once(args) -> int:
    try:
        item = run_once(Path(args.queue_dir))
    except QueueError as exc:
        print("[task_queue] error: " + str(exc), file=sys.stderr)
        return 2
    if item is None:
        print("[task_queue] run-once: no pending items.")
        return 0
    print(
        "[task_queue] run-once queue_item_id=" + item["queue_item_id"]
        + " status=" + item["status"]
        + " governor_decisions_count="
        + str(item["governor_decisions_count"])
        + " watchdog_safety_status="
        + str(item["watchdog_safety_status"])
    )
    if item["status"] == STATUS_FAILED:
        print(
            "[task_queue] last_error: " + (item.get("last_error") or ""),
            file=sys.stderr,
        )
    return 0


def _cmd_inspect(args) -> int:
    try:
        item = inspect_item(Path(args.queue_dir), args.queue_item_id)
    except QueueError as exc:
        print("[task_queue] error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(item, indent=2, sort_keys=True))
    return 0


def _cmd_validate(args) -> int:
    try:
        summary = validate_queue_tree(Path(args.queue_dir))
    except QueueError as exc:
        print("[task_queue] error: " + str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        # jsonschema.ValidationError or similar — keep the failure
        # surface narrow but informative.
        print(
            "[task_queue] validation failed: " + type(exc).__name__
            + ": " + str(exc),
            file=sys.stderr,
        )
        return 2
    print(
        "[task_queue] validate OK queue_id=" + summary["queue_id"]
        + " items_in_index=" + str(summary["items_in_index"])
        + " items_on_disk_validated=" + str(summary["items_on_disk_validated"])
    )
    return 0


def _cmd_run_batch(args) -> int:
    try:
        report = run_batch(
            queue_dir=Path(args.queue_dir),
            max_items=int(args.max_items),
            pinned_time=args.pinned_time,
            stop_on_failure=bool(args.stop_on_failure),
            sleep_seconds=int(args.sleep_seconds),
            report_path=(
                Path(args.report_path) if args.report_path else None
            ),
        )
    except QueueError as exc:
        print("[task_queue] error: " + str(exc), file=sys.stderr)
        return 2
    print(
        "[task_queue] run-batch batch_id=" + report["batch_id"]
        + " attempted=" + str(report["attempted_count"])
        + " completed=" + str(report["completed_count"])
        + " failed=" + str(report["failed_count"])
        + " skipped=" + str(report["skipped_count"])
        + " safety_status=" + report["safety_status"]
        + " report=" + str(report.get("_report_path") or "")
    )
    if report["safety_status"] == "failed":
        # Stop-on-failure path: surface the warnings so the operator
        # sees them without having to grep the report.
        for w in report["warnings"]:
            print("[task_queue]   warn: " + w, file=sys.stderr)
    return 0


COMMANDS = {
    "init": _cmd_init,
    "enqueue": _cmd_enqueue,
    "list": _cmd_list,
    "run-once": _cmd_run_once,
    "inspect": _cmd_inspect,
    "validate": _cmd_validate,
    "run-batch": _cmd_run_batch,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler = COMMANDS.get(args.command)
    if handler is None:
        parser.error("unknown command: " + repr(args.command))
        return 2
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
