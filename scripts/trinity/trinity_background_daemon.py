#!/usr/bin/env python3
"""Trinity / Background Autonomy Daemon v0.1.

Turns Trinity from a set of "tools you run by hand" into a controlled
local loop that:

1. Runs the Trinity Autonomy Orchestrator (Sprint 5.6) to harvest
   candidates and emit useful-compute requests.
2. Drops emitted requests into an inbox folder.
3. Runs the local Useful Compute worker (Sprint 5.7 / v0.2) over
   any inbox request that does not yet have a result from this
   worker_id.
4. Runs the cross-worker replay validator (Sprint 5.8) over every
   request that has results from two or more workers.
5. Runs the governance gate (Sprint 5.9) over the accumulated
   validations + pending rewards.
6. Persists a deterministic state file, a Markdown summary, and an
   append-only events ledger.

Hard invariants
---------------
- Only ``--mode local-dry-run`` is accepted.
- No network calls, no subprocesses, no shell. All sub-tools are
  imported in-process via ``importlib``.
- No wallet, no private keys, no broadcasts, no on-chain
  registration, no automatic payment.
- ``human_review_required_before_payment`` is hard-coded as ``True``
  in every emitted state document.
- The state is byte-identical across runs that share the same seed,
  pinned_time, workspace basename and inbox contents.

Workspace layout
----------------
::

    <workspace>/
      inbox/requests/       <- TRINITY_USEFUL_COMPUTE_REQUEST_*.json
      work/results/         <- TRINITY_USEFUL_COMPUTE_RESULT_*.json
      work/rewards/         <- TRINITY_USEFUL_COMPUTE_PENDING_REWARD_*.json
      validation/           <- TRINITY_USEFUL_COMPUTE_VALIDATION_*.json
      governance/           <- TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_*.json
      summaries/            <- per-cycle MD summaries
      lessons/              <- TRINITY_AUTONOMY_ERROR_LEDGER.jsonl
      orchestrator/         <- internal: orchestrator's full output

    <workspace>/TRINITY_BACKGROUND_DAEMON_STATE.json
    <workspace>/TRINITY_BACKGROUND_DAEMON_SUMMARY.md
    <workspace>/TRINITY_BACKGROUND_EVENTS.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_STATE = "trinity-background-daemon-state/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

_DEFAULT_OBJECTIVES_DIR = (
    _REPO_ROOT / "config" / "trinity" / "objectives"
)

_DEFAULT_INTERVAL_SECONDS = 600
_MIN_INTERVAL_SECONDS = 1
_MAX_INTERVAL_SECONDS = 3600


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------


def _prepare_workspace(workspace: Path) -> Dict[str, Path]:
    """Make sure every subdir exists and return a dict of paths."""
    paths = {
        "inbox_requests": workspace / "inbox" / "requests",
        "work_results":   workspace / "work" / "results",
        "work_rewards":   workspace / "work" / "rewards",
        "validation":     workspace / "validation",
        "governance":     workspace / "governance",
        "summaries":      workspace / "summaries",
        "lessons":        workspace / "lessons",
        "orchestrator":   workspace / "orchestrator",
    }
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    return paths


def _append_event(events_path: Path, event: Dict[str, Any]) -> None:
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(canonical_dumps(event) + "\n")


# ---------------------------------------------------------------------------
# Cycle stages
# ---------------------------------------------------------------------------


def _stage_orchestrator(
    *,
    paths: Dict[str, Path],
    objectives_dir: Path,
    seed: str,
    pinned_time: str,
    count: int,
    events_path: Path,
    error_mem_mod,
    error_ledger: Path,
) -> Tuple[int, int]:
    """Run the Trinity orchestrator. Copy emitted UC request files
    into the inbox. Returns (orchestrator_errors, new_requests)."""
    orchestrator_mod = _load(
        "trinity_bg_orch", _SCRIPTS_DIR / "trinity_orchestrator.py",
    )
    new_requests = 0
    try:
        result = orchestrator_mod.run_orchestrator(
            mode="dry-run", seed=seed,
            pinned_time=pinned_time,
            objectives_dir=objectives_dir,
            out_dir=paths["orchestrator"],
            count=count,
        )
    except Exception as exc:
        error_mem_mod.record_lesson(
            ledger_path=error_ledger,
            vertical="useful_compute",
            task_inputs={"action": "orchestrator", "count": count},
            cause="compute_failed",
            detail=f"{type(exc).__name__}: {exc}",
            pinned_time=pinned_time,
        )
        _append_event(events_path, {
            "schema": "trinity-background-event/v0.1",
            "ts": pinned_time, "stage": "orchestrator",
            "kind": "exception",
            "detail": f"{type(exc).__name__}: {exc}",
        })
        return (1, 0)

    # Promote orchestrator request files into the inbox.
    src_dir = paths["orchestrator"]
    for src in sorted(
        src_dir.glob("TRINITY_USEFUL_COMPUTE_REQUEST_*.json")
    ):
        dst = paths["inbox_requests"] / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
            new_requests += 1

    err_count = int(result["summary"].get("errors_count", 0))
    _append_event(events_path, {
        "schema": "trinity-background-event/v0.1",
        "ts": pinned_time, "stage": "orchestrator",
        "kind": "ok",
        "decisions": int(result["summary"]["decisions_count"]),
        "uc_requests": int(result["summary"]["uc_requests_count"]),
        "errors": err_count,
        "geo_ran": bool(result["summary"]["geo_ran"]),
        "materials_ran": bool(result["summary"]["materials_ran"]),
    })
    return (err_count, new_requests)


_REQUEST_NAME_RE = re.compile(
    r"^TRINITY_USEFUL_COMPUTE_REQUEST_(uc-[0-9a-f]{16,64})\.json$"
)


def _stage_worker(
    *,
    paths: Dict[str, Path],
    worker_id: Optional[str],
    pinned_time: str,
    events_path: Path,
    error_mem_mod,
    error_ledger: Path,
    allow_known_failures: bool,
) -> Tuple[int, int]:
    """For each request in inbox that does NOT yet have a result for
    ``worker_id``, run the worker. Returns (errors, new_results)."""
    if worker_id is None:
        return (0, 0)

    worker_mod = _load(
        "trinity_bg_worker", _SCRIPTS_DIR / "useful_compute_worker.py",
    )

    new_results = 0
    errors = 0
    for req_path in sorted(
        paths["inbox_requests"].glob(
            "TRINITY_USEFUL_COMPUTE_REQUEST_*.json"
        )
    ):
        m = _REQUEST_NAME_RE.match(req_path.name)
        if not m:
            continue
        rid = m.group(1)

        # Skip if this worker_id already submitted a result for rid.
        already = False
        for r in paths["work_results"].glob(
            f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_*.json"
        ):
            try:
                obj = json.loads(r.read_text(encoding="utf-8"))
            except Exception:
                continue
            if obj.get("worker_id") == worker_id:
                already = True
                break
        if already:
            continue

        # Respect prior error_memory lessons unless allowed.
        if not allow_known_failures:
            prior = error_mem_mod.has_repeat_lesson(
                error_ledger, "useful_compute",
                {"request_id": rid, "worker_id": worker_id},
            )
            if prior is not None:
                _append_event(events_path, {
                    "schema": "trinity-background-event/v0.1",
                    "ts": pinned_time, "stage": "worker",
                    "kind": "skipped_known_failure",
                    "request_id": rid,
                    "lesson_cause": prior.get("cause", ""),
                })
                continue

        try:
            req_obj = json.loads(req_path.read_text(encoding="utf-8"))
            res, _pending = worker_mod.run_worker(
                request=req_obj,
                worker_id=worker_id,
                out_dir=paths["work_results"],
                pinned_time=pinned_time,
            )
        except Exception as exc:
            errors += 1
            error_mem_mod.record_lesson(
                ledger_path=error_ledger,
                vertical="useful_compute",
                task_inputs={
                    "request_id": rid, "worker_id": worker_id,
                    "action": "worker",
                },
                cause="compute_failed",
                detail=f"{type(exc).__name__}: {exc}",
                pinned_time=pinned_time,
            )
            _append_event(events_path, {
                "schema": "trinity-background-event/v0.1",
                "ts": pinned_time, "stage": "worker",
                "kind": "exception", "request_id": rid,
                "detail": f"{type(exc).__name__}: {exc}",
            })
            continue

        # Move the pending reward file from work_results to work_rewards.
        wrid = res["worker_result_id"]
        rew_name = (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.json"
        )
        rew_in_results = paths["work_results"] / rew_name
        if rew_in_results.exists():
            shutil.move(
                str(rew_in_results),
                str(paths["work_rewards"] / rew_name),
            )

        new_results += 1
        _append_event(events_path, {
            "schema": "trinity-background-event/v0.1",
            "ts": pinned_time, "stage": "worker",
            "kind": "ok", "request_id": rid,
            "worker_id": worker_id,
            "worker_result_id": wrid,
        })
    return (errors, new_results)


def _stage_validator(
    *,
    paths: Dict[str, Path],
    pinned_time: str,
    events_path: Path,
    error_mem_mod,
    error_ledger: Path,
    min_workers: int,
) -> Tuple[int, int, List[str]]:
    """Run replay validator for every request that has results from
    >= min_workers distinct worker_ids. Returns
    (errors, validations_written, accepted_validation_ids)."""
    validator_mod = _load(
        "trinity_bg_validator",
        _SCRIPTS_DIR / "useful_compute_replay_validator.py",
    )

    accepted_vids: List[str] = []
    written = 0
    errors = 0

    # Group results by request_id, count distinct worker_ids.
    request_results: Dict[str, set] = {}
    for r in paths["work_results"].glob(
        "TRINITY_USEFUL_COMPUTE_RESULT_*.json"
    ):
        try:
            obj = json.loads(r.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = obj.get("request_id")
        wid = obj.get("worker_id")
        if not isinstance(rid, str) or not isinstance(wid, str):
            continue
        request_results.setdefault(rid, set()).add(wid)

    for rid, workers in sorted(request_results.items()):
        if len(workers) < min_workers:
            continue
        req_path = (
            paths["inbox_requests"]
            / f"TRINITY_USEFUL_COMPUTE_REQUEST_{rid}.json"
        )
        if not req_path.exists():
            continue
        try:
            req_obj = json.loads(req_path.read_text(encoding="utf-8"))
            report = validator_mod.run_validation(
                request=req_obj,
                results_dir=paths["work_results"],
                out_dir=paths["validation"],
                min_workers=min_workers,
                pinned_time=pinned_time,
                error_memory_ledger=error_ledger,
            )
        except Exception as exc:
            errors += 1
            error_mem_mod.record_lesson(
                ledger_path=error_ledger,
                vertical="useful_compute",
                task_inputs={
                    "request_id": rid, "action": "validator",
                },
                cause="validation_failed",
                detail=f"{type(exc).__name__}: {exc}",
                pinned_time=pinned_time,
            )
            _append_event(events_path, {
                "schema": "trinity-background-event/v0.1",
                "ts": pinned_time, "stage": "validator",
                "kind": "exception", "request_id": rid,
                "detail": f"{type(exc).__name__}: {exc}",
            })
            continue

        written += 1
        status = report["validation_status"]
        if status == "accepted":
            accepted_vids.append(report["validation_id"])
        _append_event(events_path, {
            "schema": "trinity-background-event/v0.1",
            "ts": pinned_time, "stage": "validator",
            "kind": "ok", "request_id": rid,
            "validation_id": report["validation_id"],
            "validation_status": status,
            "unique_workers": int(report["unique_workers"]),
        })
    return (errors, written, accepted_vids)


def _stage_governance(
    *,
    paths: Dict[str, Path],
    reviewer_id: Optional[str],
    pinned_time: str,
    events_path: Path,
    error_mem_mod,
    error_ledger: Path,
) -> Tuple[int, int, List[str]]:
    """Run the governance gate. Returns (errors, batches_written,
    approved_batch_ids)."""
    if reviewer_id is None:
        return (0, 0, [])

    if not any(
        paths["validation"].glob(
            "TRINITY_USEFUL_COMPUTE_VALIDATION_*.json"
        )
    ):
        # Nothing to govern this cycle — that is not an error.
        return (0, 0, [])

    gate_mod = _load(
        "trinity_bg_gate",
        _SCRIPTS_DIR / "useful_compute_governance_gate.py",
    )
    try:
        batch = gate_mod.run_governance_gate(
            validations_dir=paths["validation"],
            rewards_dir=paths["work_rewards"],
            out_dir=paths["governance"],
            reviewer_id=reviewer_id,
            policy="conservative",
            pinned_time=pinned_time,
            error_memory_ledger=error_ledger,
        )
    except Exception as exc:
        error_mem_mod.record_lesson(
            ledger_path=error_ledger,
            vertical="useful_compute",
            task_inputs={"action": "governance"},
            cause="bad_input",
            detail=f"{type(exc).__name__}: {exc}",
            pinned_time=pinned_time,
        )
        _append_event(events_path, {
            "schema": "trinity-background-event/v0.1",
            "ts": pinned_time, "stage": "governance",
            "kind": "exception",
            "detail": f"{type(exc).__name__}: {exc}",
        })
        return (1, 0, [])

    _append_event(events_path, {
        "schema": "trinity-background-event/v0.1",
        "ts": pinned_time, "stage": "governance",
        "kind": "ok",
        "batch_id": batch["batch_id"],
        "approved_count": batch["approved_count"],
        "rejected_count": batch["rejected_count"],
        "total_approved_reward_stocks":
            batch["total_approved_reward_stocks"],
    })

    approved_ids: List[str] = []
    if batch["approved_count"] >= 1:
        approved_ids.append(batch["batch_id"])
    return (0, 1, approved_ids)


# ---------------------------------------------------------------------------
# Cycle + state
# ---------------------------------------------------------------------------


def _scan_inbox_request_ids(inbox_dir: Path) -> List[str]:
    ids: List[str] = []
    for p in sorted(inbox_dir.glob(
        "TRINITY_USEFUL_COMPUTE_REQUEST_*.json"
    )):
        m = _REQUEST_NAME_RE.match(p.name)
        if m:
            ids.append(m.group(1))
    return sorted(set(ids))


def _scan_validations(val_dir: Path) -> Tuple[int, List[str]]:
    total = 0
    accepted: List[str] = []
    for p in sorted(val_dir.glob(
        "TRINITY_USEFUL_COMPUTE_VALIDATION_*.json"
    )):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        total += 1
        if obj.get("validation_status") == "accepted":
            accepted.append(obj.get("validation_id", ""))
    return total, sorted(set(accepted))


def _scan_governance(gov_dir: Path) -> Tuple[int, List[str]]:
    total = 0
    approved_batches: List[str] = []
    for p in sorted(gov_dir.glob(
        "TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_*.json"
    )):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        total += 1
        if int(obj.get("approved_count", 0)) >= 1:
            approved_batches.append(obj.get("batch_id", ""))
    return total, sorted(set(approved_batches))


def _scan_results(results_dir: Path) -> int:
    return len(list(results_dir.glob(
        "TRINITY_USEFUL_COMPUTE_RESULT_*.json"
    )))


def run_cycle(
    *,
    workspace: Path,
    objectives_dir: Path,
    seed: str,
    pinned_time: str,
    count: int,
    worker_id: Optional[str],
    reviewer_id: Optional[str],
    min_workers: int = 2,
    allow_known_failures: bool = False,
    cycle_index: int = 1,
    started_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute one full daemon cycle and persist the state file."""
    workspace = workspace.resolve()
    paths = _prepare_workspace(workspace)
    state_path = workspace / "TRINITY_BACKGROUND_DAEMON_STATE.json"
    summary_path = workspace / "TRINITY_BACKGROUND_DAEMON_SUMMARY.md"
    events_path = workspace / "TRINITY_BACKGROUND_EVENTS.jsonl"
    error_ledger = (
        paths["lessons"] / "TRINITY_AUTONOMY_ERROR_LEDGER.jsonl"
    )

    error_mem_mod = _load(
        "trinity_bg_error_mem",
        _SCRIPTS_DIR / "trinity_error_memory.py",
    )

    errors = 0

    orch_err, _new_reqs = _stage_orchestrator(
        paths=paths, objectives_dir=objectives_dir,
        seed=seed, pinned_time=pinned_time, count=count,
        events_path=events_path,
        error_mem_mod=error_mem_mod,
        error_ledger=error_ledger,
    )
    errors += orch_err

    work_err, _new_res = _stage_worker(
        paths=paths, worker_id=worker_id,
        pinned_time=pinned_time, events_path=events_path,
        error_mem_mod=error_mem_mod,
        error_ledger=error_ledger,
        allow_known_failures=allow_known_failures,
    )
    errors += work_err

    val_err, _vw, _accepted_vids = _stage_validator(
        paths=paths, pinned_time=pinned_time,
        events_path=events_path,
        error_mem_mod=error_mem_mod,
        error_ledger=error_ledger,
        min_workers=min_workers,
    )
    errors += val_err

    gov_err, _gw, _approved_batches = _stage_governance(
        paths=paths, reviewer_id=reviewer_id,
        pinned_time=pinned_time, events_path=events_path,
        error_mem_mod=error_mem_mod,
        error_ledger=error_ledger,
    )
    errors += gov_err

    # Persistent counts (read disk; do not trust per-stage counters).
    pending_requests = _scan_inbox_request_ids(paths["inbox_requests"])
    results_seen = _scan_results(paths["work_results"])
    validations_seen, accepted_vids = _scan_validations(paths["validation"])
    governance_seen, approved_batches = _scan_governance(paths["governance"])
    lessons = error_mem_mod.read_lessons(error_ledger)
    lessons_count = len(lessons)

    state = {
        "schema": SCHEMA_STATE,
        "mode": "local-dry-run",
        "workspace": workspace.name,
        "cycle_index": int(cycle_index),
        "started_at": started_at or pinned_time,
        "last_cycle_at": pinned_time,
        "requests_seen": len(pending_requests),
        "results_seen": results_seen,
        "validations_seen": validations_seen,
        "governance_batches_seen": governance_seen,
        "pending_requests": pending_requests,
        "accepted_validations": accepted_vids,
        "approved_batches": approved_batches,
        "errors_count": errors,
        "lessons_count": lessons_count,
        "safety_status": {
            "local_dry_run_only":                    True,
            "no_wallet_access":                      True,
            "no_private_keys":                       True,
            "no_automatic_payout":                   True,
            "no_broadcast":                          True,
            "no_network_required":                   True,
            "no_consensus_changes":                  True,
            "human_review_required_before_payment":  True,
        },
    }
    state_path.write_text(canonical_dumps(state), encoding="utf-8")
    summary_path.write_text(
        _render_summary_md(state, lessons), encoding="utf-8",
    )
    return state


def _render_summary_md(
    state: Dict[str, Any], lessons: List[Dict[str, Any]],
) -> str:
    lines = [
        "# TRINITY BACKGROUND AUTONOMY DAEMON — SUMMARY",
        "",
        f"- schema: `{state['schema']}`",
        f"- workspace: `{state['workspace']}`",
        f"- mode: `{state['mode']}`",
        f"- cycle_index: **{state['cycle_index']}**",
        f"- started_at: `{state['started_at']}`",
        f"- last_cycle_at: `{state['last_cycle_at']}`",
        "",
        "## Counts",
        "",
        f"- requests_seen: {state['requests_seen']}",
        f"- results_seen: {state['results_seen']}",
        f"- validations_seen: {state['validations_seen']}",
        f"- governance_batches_seen: {state['governance_batches_seen']}",
        f"- errors_count: {state['errors_count']}",
        f"- lessons_count: {state['lessons_count']}",
        "",
        "## Pending requests",
        "",
    ]
    if state["pending_requests"]:
        for r in state["pending_requests"]:
            lines.append(f"- `{r}`")
    else:
        lines.append("_none_")
    lines.extend(["", "## Accepted validations", ""])
    if state["accepted_validations"]:
        for v in state["accepted_validations"]:
            lines.append(f"- `{v}`")
    else:
        lines.append("_none_")
    lines.extend(["", "## Approved governance batches", ""])
    if state["approved_batches"]:
        for b in state["approved_batches"]:
            lines.append(f"- `{b}`")
    else:
        lines.append("_none_")
    lines.extend(["", "## Top lessons learned", ""])
    if lessons:
        agg: Dict[str, int] = {}
        for ls in lessons:
            key = (f"{ls.get('vertical','?')}::"
                   f"{ls.get('cause','?')}")
            agg[key] = agg.get(key, 0) + 1
        for key in sorted(agg, key=lambda k: -agg[k])[:8]:
            lines.append(f"- `{key}` x{agg[key]}")
    else:
        lines.append("_none_")
    lines.extend([
        "",
        "## Safety",
        "",
        "- `local_dry_run_only`",
        "- `no_wallet_access`, `no_private_keys`",
        "- `no_automatic_payout`, `no_broadcast`",
        "- `no_network_required`, `no_consensus_changes`",
        "- `human_review_required_before_payment`",
        "",
        "This daemon NEVER pays. A separate, governance-signed",
        "payment sprint is required before any stocks move.",
    ])
    return "\n".join(lines)


def run_watch(
    *,
    workspace: Path,
    objectives_dir: Path,
    seed: str,
    pinned_time: Optional[str],
    count: int,
    worker_id: Optional[str],
    reviewer_id: Optional[str],
    interval_seconds: int,
    max_cycles: Optional[int],
    min_workers: int,
    allow_known_failures: bool,
) -> List[Dict[str, Any]]:
    """Run cycles in a loop. Each cycle resolves its own pinned_time
    (now()) if not explicitly supplied. Returns the list of state
    snapshots, one per cycle."""
    interval = max(_MIN_INTERVAL_SECONDS,
                   min(_MAX_INTERVAL_SECONDS, int(interval_seconds)))
    states: List[Dict[str, Any]] = []
    started_at = pinned_time
    cycles = 0
    while True:
        cycles += 1
        from datetime import datetime, timezone
        this_time = pinned_time or datetime.now(
            tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        if started_at is None:
            started_at = this_time
        state = run_cycle(
            workspace=workspace, objectives_dir=objectives_dir,
            seed=seed, pinned_time=this_time, count=count,
            worker_id=worker_id, reviewer_id=reviewer_id,
            min_workers=min_workers,
            allow_known_failures=allow_known_failures,
            cycle_index=cycles,
            started_at=started_at,
        )
        states.append(state)
        if max_cycles is not None and cycles >= max_cycles:
            break
        time.sleep(interval)
    return states


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="trinity_background_daemon",
        description=(
            "Trinity background autonomy daemon v0.1. Runs Trinity "
            "as a controlled local-dry-run loop. NEVER pays, NEVER "
            "touches a wallet, NEVER broadcasts."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument("--workspace", required=True)
    p.add_argument(
        "--objectives", default=str(_DEFAULT_OBJECTIVES_DIR),
    )
    p.add_argument("--seed", default="trinity-autonomy-v0.1")
    p.add_argument(
        "--pinned-time", default=None,
        help=(
            "Optional ISO-8601 timestamp. When supplied, the cycle is "
            "deterministic. When omitted, wall-clock is used."
        ),
    )
    p.add_argument("--count", type=int, default=25)
    p.add_argument("--worker-id", default=None)
    p.add_argument("--reviewer-id", default=None)
    p.add_argument("--min-workers", type=int, default=2)
    p.add_argument(
        "--allow-known-failures", action="store_true",
        help=(
            "If set, the daemon will re-attempt a request that has a "
            "recorded lesson. Default: refuse."
        ),
    )
    mode_grp = p.add_mutually_exclusive_group(required=True)
    mode_grp.add_argument("--run-once", action="store_true")
    mode_grp.add_argument("--watch",    action="store_true")
    p.add_argument(
        "--interval-seconds", type=int,
        default=_DEFAULT_INTERVAL_SECONDS,
    )
    p.add_argument("--max-cycles", type=int, default=None)

    # Hard-rejection guards.
    p.add_argument("--broadcast", action="store_true", help="REJECTED")
    p.add_argument("--payout",    action="store_true", help="REJECTED")
    p.add_argument("--send",      action="store_true", help="REJECTED")
    p.add_argument("--wallet",    type=str, default=None, help="REJECTED")
    p.add_argument("--network",   action="store_true", help="REJECTED")
    args = p.parse_args(argv)

    if args.mode != "local-dry-run":
        print(
            "[trinity_background_daemon] only local-dry-run is "
            "supported in v0.1",
            file=sys.stderr,
        )
        return 2
    for flag_value, flag_name in (
        (args.broadcast, "--broadcast"),
        (args.payout,    "--payout"),
        (args.send,      "--send"),
        (args.network,   "--network"),
    ):
        if flag_value:
            print(
                f"[trinity_background_daemon] flag {flag_name} is "
                "rejected in v0.1",
                file=sys.stderr,
            )
            return 2
    if args.wallet is not None:
        print(
            "[trinity_background_daemon] --wallet is rejected in v0.1",
            file=sys.stderr,
        )
        return 2

    workspace = Path(args.workspace)
    objectives_dir = Path(args.objectives)

    if args.run_once:
        from datetime import datetime, timezone
        pinned_time = args.pinned_time or datetime.now(
            tz=timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        state = run_cycle(
            workspace=workspace,
            objectives_dir=objectives_dir,
            seed=args.seed,
            pinned_time=pinned_time,
            count=args.count,
            worker_id=args.worker_id,
            reviewer_id=args.reviewer_id,
            min_workers=args.min_workers,
            allow_known_failures=args.allow_known_failures,
            cycle_index=1,
        )
        print(
            f"[trinity_background_daemon] run_once cycle="
            f"{state['cycle_index']} "
            f"requests={state['requests_seen']} "
            f"results={state['results_seen']} "
            f"validations={state['validations_seen']} "
            f"batches={state['governance_batches_seen']} "
            f"errors={state['errors_count']} "
            f"lessons={state['lessons_count']}"
        )
        return 0

    # watch
    states = run_watch(
        workspace=workspace, objectives_dir=objectives_dir,
        seed=args.seed, pinned_time=args.pinned_time,
        count=args.count, worker_id=args.worker_id,
        reviewer_id=args.reviewer_id,
        interval_seconds=args.interval_seconds,
        max_cycles=args.max_cycles,
        min_workers=args.min_workers,
        allow_known_failures=args.allow_known_failures,
    )
    last = states[-1]
    print(
        f"[trinity_background_daemon] watch cycles={len(states)} "
        f"last_state: requests={last['requests_seen']} "
        f"results={last['results_seen']} "
        f"validations={last['validations_seen']} "
        f"batches={last['governance_batches_seen']} "
        f"errors={last['errors_count']} "
        f"lessons={last['lessons_count']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
