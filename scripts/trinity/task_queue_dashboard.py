#!/usr/bin/env python3
"""Trinity Task Queue Dashboard v0.1 (Sprint 5.28).

Read-only summary of a Trinity Task Queue (Sprint 5.26) plus its
runner batches (Sprint 5.27). Reads:

  queue-dir/queue.json
  queue-dir/{pending,running,completed,failed}/<id>.json
  queue-dir/reports/<id>/operator_run/operator_run.json
  queue-dir/reports/<id>/watchdog/TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json
  queue-dir/reports/_batches/TRINITY_TASK_QUEUE_RUNNER_REPORT_*.json

Writes:

  out-dir/TRINITY_TASK_QUEUE_DASHBOARD_<dashboard_id>.json
  out-dir/TRINITY_TASK_QUEUE_DASHBOARD_<dashboard_id>.html

Hard invariants v0.1 (enforced by static tests):
    - Read-only on the queue dir. Never moves items, never invokes
      operator_loop, never invokes the watchdog. No subprocess at
      all.
    - No wallet, no private-key handling, no signing, no
      broadcasting, no chain CLI, no payment / reward primitives.
    - No network. The HTML is self-contained, no external assets,
      no CDN, no JavaScript.
    - No absolute paths in the dashboard JSON or HTML — only
      basenames. The queue-dir basename is kept; the queue-dir
      absolute path is never persisted.
    - All text inserted into the HTML is escaped via html.escape;
      a static safety test asserts the raw helper is unused.

Usage:
    python3 scripts/trinity/task_queue_dashboard.py \\
        --queue-dir /var/lib/trinity/queues/main \\
        --out-dir   /var/lib/trinity/dashboards \\
        --pinned-time 2026-05-17T00:00:00+00:00

Output:
    out-dir/TRINITY_TASK_QUEUE_DASHBOARD_<id>.json
    out-dir/TRINITY_TASK_QUEUE_DASHBOARD_<id>.html
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os.path
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_DASHBOARD = "trinity-task-queue-dashboard/v0.1"
SCHEMA_QUEUE = "trinity-task-queue/v0.1"
SCHEMA_ITEM = "trinity-task-queue-item/v0.1"
SCHEMA_RUNNER_REPORT = "trinity-task-queue-runner-report/v0.1"
SCHEMA_WATCHDOG_REPORT = "trinity-governor-watchdog-report/v0.1"
SCHEMA_OPERATOR_RUN = "trinity-useful-compute-operator-run/v0.1"

DEFAULT_LATEST_LIMIT = 25
STATUSES = ("pending", "running", "completed", "failed")


class DashboardError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    """Return parsed JSON or None on any read / decode error. The
    Dashboard tolerates malformed files and records them as warnings
    rather than crashing."""
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return None
        return obj
    except (OSError, json.JSONDecodeError):
        return None


def _safe_basename(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    if not isinstance(s, str) or not s:
        return None
    name = os.path.basename(s)
    if not name:
        return None
    return name


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def _scan_queue(
    queue_dir: Path, warnings: List[str],
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Read queue.json and every per-status item file. Returns the
    queue dict (or None if missing/malformed) plus a list of
    successfully-parsed item dicts.

    Items in the queue.json index that are missing on disk, or
    files on disk not in the index, are recorded as warnings."""
    queue_json = queue_dir / "queue.json"
    if not queue_json.exists():
        warnings.append("queue.json missing at " + queue_json.name)
        return None, []
    queue = _read_json(queue_json)
    if queue is None or queue.get("schema") != SCHEMA_QUEUE:
        warnings.append("queue.json malformed or wrong schema")
        return queue, []

    items: List[Dict[str, Any]] = []
    indexed_ids = set()
    for idx in queue.get("items", []):
        item_id = idx.get("queue_item_id")
        status = idx.get("status")
        if not item_id or status not in STATUSES:
            warnings.append(
                "queue.json index entry malformed: "
                + json.dumps(idx, sort_keys=True)[:200]
            )
            continue
        indexed_ids.add(item_id)
        item_path = queue_dir / status / (item_id + ".json")
        if not item_path.exists():
            warnings.append(
                "item " + item_id + " missing on disk under "
                + status + "/"
            )
            continue
        obj = _read_json(item_path)
        if obj is None or obj.get("schema") != SCHEMA_ITEM:
            warnings.append(
                "item " + item_id + " malformed or wrong schema"
            )
            continue
        items.append(obj)

    # Reverse check: file on disk not in the index → warning.
    for s in STATUSES:
        d = queue_dir / s
        if not d.exists():
            continue
        for f in sorted(d.glob("*.json")):
            stem = f.stem
            if stem.startswith("qit-") and stem not in indexed_ids:
                warnings.append(
                    "file " + s + "/" + f.name
                    + " is not referenced in queue.json"
                )
    return queue, items


def _per_item_audit(
    queue_dir: Path, item: Dict[str, Any], warnings: List[str],
) -> Dict[str, Any]:
    """Extract dashboard-relevant fields from one queue item. Pulls
    governor_decisions_count from the item itself when present, or
    from the operator_run.json fallback. Reads the watchdog report's
    safety_status when the path is set."""
    item_id = item.get("queue_item_id", "")
    operator_run_basename = _safe_basename(item.get("operator_run_path"))
    watchdog_report_basename = _safe_basename(
        item.get("watchdog_report_path")
    )

    governor_decisions_count = int(item.get("governor_decisions_count", 0))
    # Cross-check against operator_run.json when accessible — but
    # the operator_run_path may be an absolute path the dashboard
    # cannot read (different host, moved tree). Use the queue's
    # canonical location instead.
    op_state_path = (
        queue_dir / "reports" / item_id / "operator_run"
        / "operator_run.json"
    )
    if op_state_path.exists():
        op_state = _read_json(op_state_path)
        if op_state is not None:
            count_from_state = op_state.get("governor_decisions_count")
            if isinstance(count_from_state, int):
                governor_decisions_count = count_from_state

    watchdog_safety_status = item.get("watchdog_safety_status")
    wd_dir = queue_dir / "reports" / item_id / "watchdog"
    if wd_dir.exists():
        reports = sorted(wd_dir.glob(
            "TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json"
        ))
        if reports:
            wd = _read_json(reports[-1])
            if wd is None:
                warnings.append(
                    "watchdog report for " + item_id + " malformed"
                )
            elif wd.get("schema") != SCHEMA_WATCHDOG_REPORT:
                warnings.append(
                    "watchdog report for " + item_id
                    + " wrong schema"
                )
            else:
                status = wd.get("safety_status")
                if status in ("ok", "warning", "stale", "critical"):
                    watchdog_safety_status = status

    if watchdog_safety_status not in (
        None, "ok", "warning", "stale", "critical",
    ):
        warnings.append(
            "watchdog_safety_status for " + item_id
            + " has unexpected value; treating as null"
        )
        watchdog_safety_status = None

    # Sprint 5.33 — materials_engine surfacing per item. Reads the
    # operator_run.json roll-up (added by the Sprint 5.33 operator
    # loop change) when present; otherwise falls back to walking
    # worker result files directly. Either path produces:
    #   materials_engine_summary_count    int   (0 when absent)
    #   materials_engine_top_material     str|None (highest-ranked
    #                                              material across
    #                                              this item's
    #                                              materials_engine
    #                                              worker results)
    #   materials_engine_known_count      int
    #   materials_engine_unknown_count    int
    #   materials_engine_warnings_count   int
    materials_engine_summary_count = 0
    materials_engine_top_material = None
    materials_engine_known_count = 0
    materials_engine_unknown_count = 0
    materials_engine_warnings_count = 0
    if op_state_path.exists():
        op_state = _read_json(op_state_path)
        if op_state is not None:
            mec = op_state.get("materials_engine_summary_count")
            if isinstance(mec, int):
                materials_engine_summary_count = mec
            mtop = op_state.get("materials_engine_top_materials")
            if isinstance(mtop, list) and mtop:
                # The op_state stores the de-dup sorted list; we pick
                # the first one as the displayed top. When the run
                # had multiple materials_engine workers all agreeing
                # on PrOx > CeO2, the list is just ["PrOx"]; when it
                # had two workers disagreeing it's ["CeO2", "PrOx"]
                # and we surface the alphabetically-first one (which
                # also happens to be deterministic).
                materials_engine_top_material = str(mtop[0])[:64]

    # Sprint 5.34 - additional per-item surfacing:
    # materials_project_cache_hits / misses (Sprint 5.34 backend)
    # plus workers_seen + worker_ids_truncated (always available
    # from the worker_out walk).
    materials_project_cache_hits  = 0
    materials_project_cache_misses = 0
    workers_seen = 0
    worker_ids_truncated: List[str] = []

    # Cross-check + fall-back: walk per-worker result files to
    # populate the per-item known / unknown / warnings counts
    # which are NOT in the operator_run roll-up.
    worker_out_dir = (
        queue_dir / "reports" / item_id / "operator_run" / "worker_out"
    )
    if worker_out_dir.exists():
        for wp in sorted(worker_out_dir.glob(
            "TRINITY_USEFUL_COMPUTE_RESULT_*.json",
        )):
            w_obj = _read_json(wp)
            if w_obj is None:
                continue
            workers_seen += 1
            wid = w_obj.get("worker_id")
            if isinstance(wid, str) and wid:
                truncated = wid[:32]
                if truncated not in worker_ids_truncated:
                    worker_ids_truncated.append(truncated)
            s = w_obj.get("materials_engine_summary")
            if not isinstance(s, dict):
                continue
            # Fallback for ops with no op_state roll-up.
            if materials_engine_top_material is None:
                tm = s.get("top_ranked_material")
                if isinstance(tm, str) and tm:
                    materials_engine_top_material = tm[:64]
            kn = s.get("known_materials")
            un = s.get("unknown_materials")
            wn = s.get("warnings")
            if isinstance(kn, list):
                materials_engine_known_count = max(
                    materials_engine_known_count, len(kn),
                )
            if isinstance(un, list):
                materials_engine_unknown_count = max(
                    materials_engine_unknown_count, len(un),
                )
            if isinstance(wn, list):
                materials_engine_warnings_count = max(
                    materials_engine_warnings_count, len(wn),
                )
            if materials_engine_summary_count == 0:
                materials_engine_summary_count += 1
            # Sprint 5.34 - cache hit/miss counts. Use max() so two
            # workers reporting identical hit counts converge to
            # the same number; if they ever disagreed (shouldn't,
            # cache is deterministic) we surface the larger
            # because that's the floor of work that was done.
            mphc = s.get("materials_project_cache_hit_count")
            mpmc = s.get("materials_project_cache_miss_count")
            if isinstance(mphc, int) and mphc > materials_project_cache_hits:
                materials_project_cache_hits = mphc
            if isinstance(mpmc, int) and mpmc > materials_project_cache_misses:
                materials_project_cache_misses = mpmc

    return {
        "queue_item_id": item_id,
        "status": item.get("status", ""),
        "updated_at": item.get("updated_at", ""),
        "attempt_count": int(item.get("attempt_count", 0)),
        "operator_run_path_basename": operator_run_basename,
        "watchdog_report_path_basename": watchdog_report_basename,
        "governor_decisions_count": governor_decisions_count,
        "watchdog_safety_status": watchdog_safety_status,
        "materials_engine_summary_count": materials_engine_summary_count,
        "materials_engine_top_material": materials_engine_top_material,
        "materials_engine_known_count": materials_engine_known_count,
        "materials_engine_unknown_count": materials_engine_unknown_count,
        "materials_engine_warnings_count": materials_engine_warnings_count,
        # Sprint 5.34 fields
        "materials_project_cache_hits":   materials_project_cache_hits,
        "materials_project_cache_misses": materials_project_cache_misses,
        "workers_seen":                   workers_seen,
        "worker_ids_truncated":           worker_ids_truncated,
    }


def _scan_batches(
    queue_dir: Path, warnings: List[str],
) -> List[Dict[str, Any]]:
    """Read every batch report under queue-dir/reports/_batches/.
    Malformed reports add a warning and are skipped."""
    batches_dir = queue_dir / "reports" / "_batches"
    out: List[Dict[str, Any]] = []
    if not batches_dir.exists():
        return out
    for f in sorted(batches_dir.glob(
        "TRINITY_TASK_QUEUE_RUNNER_REPORT_*.json"
    )):
        obj = _read_json(f)
        if obj is None or obj.get("schema") != SCHEMA_RUNNER_REPORT:
            warnings.append(
                "batch report " + f.name + " malformed or wrong schema"
            )
            continue
        status = obj.get("safety_status")
        if status not in ("ok", "warning", "failed"):
            warnings.append(
                "batch report " + f.name
                + " has unexpected safety_status"
            )
            continue
        out.append({
            "batch_id": obj.get("batch_id", ""),
            "attempted_count": int(obj.get("attempted_count", 0)),
            "completed_count": int(obj.get("completed_count", 0)),
            "failed_count": int(obj.get("failed_count", 0)),
            "safety_status": status,
        })
    return out


# ---------------------------------------------------------------------------
# safety_status rollup
# ---------------------------------------------------------------------------


def _rollup_safety_status(
    items_view: List[Dict[str, Any]],
    batches_view: List[Dict[str, Any]],
    warnings: List[str],
) -> str:
    """Dashboard-wide rollup with strict precedence:
        failed  > warning > ok
    """
    failed = False
    warning = False

    for it in items_view:
        if it["watchdog_safety_status"] == "critical":
            failed = True
        if it["status"] == "failed":
            warning = True
        if it["watchdog_safety_status"] in ("warning", "stale"):
            warning = True

    for b in batches_view:
        if b["safety_status"] == "failed":
            failed = True
        elif b["safety_status"] == "warning":
            warning = True

    if warnings:
        warning = True

    if failed:
        return "failed"
    if warning:
        return "warning"
    return "ok"


# ---------------------------------------------------------------------------
# Build the dashboard dict
# ---------------------------------------------------------------------------


def build_dashboard(
    queue_dir: Path,
    pinned_time: str,
    latest_limit: int = DEFAULT_LATEST_LIMIT,
) -> Dict[str, Any]:
    queue_dir = Path(queue_dir)
    if not queue_dir.exists() or not queue_dir.is_dir():
        raise DashboardError(
            "queue-dir does not exist or is not a directory: "
            + str(queue_dir)
        )
    warnings: List[str] = []
    queue, items = _scan_queue(queue_dir, warnings)
    if queue is None:
        raise DashboardError(
            "queue-dir has no readable queue.json: " + str(queue_dir)
        )

    items_view = [
        _per_item_audit(queue_dir, it, warnings) for it in items
    ]
    # Sort by updated_at descending; take the latest N for the view.
    items_view.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    latest_items = items_view[:int(latest_limit)]

    batches_view = _scan_batches(queue_dir, warnings)
    # Most recent batches first by batch_id (deterministic since the
    # batch reports are sorted by filename above, which encodes the
    # batch_id deterministically).
    batches_view_sorted = list(reversed(batches_view))
    latest_batches = batches_view_sorted[:int(latest_limit)]

    counts = {
        "pending":   sum(1 for x in items if x.get("status") == "pending"),
        "running":   sum(1 for x in items if x.get("status") == "running"),
        "completed": sum(1 for x in items if x.get("status") == "completed"),
        "failed":    sum(1 for x in items if x.get("status") == "failed"),
        "batches":   len(batches_view),
    }

    safety_status = _rollup_safety_status(
        items_view, batches_view, warnings,
    )

    dashboard_id = "dsh-" + _sha16(_canonical_dumps({
        "pinned_time": pinned_time,
        "queue_dir_basename": queue_dir.name,
        "queue_id": queue.get("queue_id", ""),
        "item_ids": sorted([x.get("queue_item_id", "") for x in items]),
        "batch_ids": sorted([b["batch_id"] for b in batches_view]),
    }))

    return {
        "schema": SCHEMA_DASHBOARD,
        "dashboard_id": dashboard_id,
        "pinned_time": pinned_time,
        "queue_dir_basename": queue_dir.name,
        "queue_id": queue.get("queue_id", ""),
        "counts": counts,
        "latest_items": latest_items,
        "latest_batches": latest_batches,
        "warnings": warnings,
        "safety_status": safety_status,
    }


# ---------------------------------------------------------------------------
# Static HTML rendering (no JS, no external assets)
# ---------------------------------------------------------------------------


_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, sans-serif;
       margin: 24px; color: #1a1a1a; max-width: 1100px; }
h1 { margin: 0 0 6px 0; }
h2 { margin: 28px 0 10px 0; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { border: 1px solid #ddd; padding: 6px 10px; text-align: left;
         vertical-align: top; }
th { background: #f4f4f4; }
.safety-ok      { color: #186a3b; font-weight: 600; }
.safety-warning { color: #b9770e; font-weight: 600; }
.safety-failed  { color: #922b21; font-weight: 700; }
.safety-critical{ color: #922b21; font-weight: 700; }
.safety-stale   { color: #707b7c; font-weight: 600; }
.meta { color: #555; font-size: 13px; }
ul.warnings li { color: #5d4037; }
.id { font-family: ui-monospace, monospace; font-size: 12px; }
"""


def _e(s: Any) -> str:
    """HTML-escape any value into a string. Never passes raw text
    through to the HTML; this helper is the only legitimate text
    insertion point. A static safety test asserts no other
    insertion path exists."""
    if s is None:
        return ""
    return html.escape(str(s), quote=True)


def _safety_class(status: str) -> str:
    return "safety-" + _e(status)


def render_html(dashboard: Dict[str, Any]) -> str:
    counts = dashboard["counts"]
    title = "Trinity Task Queue Dashboard"
    lines: List[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append('<html lang="en">')
    lines.append("<head>")
    lines.append('<meta charset="utf-8">')
    lines.append(
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
    )
    lines.append('<meta name="robots" content="noindex,nofollow">')
    lines.append("<title>" + _e(title) + "</title>")
    lines.append("<style>" + _CSS + "</style>")
    lines.append("</head>")
    lines.append("<body>")
    lines.append("<h1>" + _e(title) + "</h1>")
    lines.append(
        "<p class='meta'>queue: <span class='id'>"
        + _e(dashboard["queue_dir_basename"])
        + "</span> (<span class='id'>"
        + _e(dashboard["queue_id"])
        + "</span>)</p>"
    )
    lines.append(
        "<p class='meta'>dashboard_id: <span class='id'>"
        + _e(dashboard["dashboard_id"])
        + "</span> · pinned_time: " + _e(dashboard["pinned_time"])
        + "</p>"
    )
    lines.append(
        "<p>safety_status: <span class='"
        + _safety_class(dashboard["safety_status"]) + "'>"
        + _e(dashboard["safety_status"]) + "</span></p>"
    )

    lines.append("<h2>Counts</h2>")
    lines.append("<table>")
    lines.append(
        "<thead><tr><th>pending</th><th>running</th>"
        "<th>completed</th><th>failed</th><th>batches</th></tr></thead>"
    )
    lines.append("<tbody><tr>")
    for k in ("pending", "running", "completed", "failed", "batches"):
        lines.append("<td>" + _e(counts[k]) + "</td>")
    lines.append("</tr></tbody></table>")

    lines.append("<h2>Latest items</h2>")
    if not dashboard["latest_items"]:
        lines.append("<p class='meta'>no items in queue.</p>")
    else:
        lines.append("<table>")
        lines.append(
            "<thead><tr>"
            "<th>queue_item_id</th><th>status</th>"
            "<th>updated_at</th><th>attempts</th>"
            "<th>governor_decisions</th>"
            "<th>watchdog</th>"
            "<th>materials_engine</th>"
            "<th>materials_cache</th>"
            "<th>workers</th>"
            "<th>operator_run</th>"
            "<th>watchdog_report</th>"
            "</tr></thead>"
        )
        lines.append("<tbody>")
        for it in dashboard["latest_items"]:
            wd_status = it["watchdog_safety_status"]
            wd_cell = (
                "<span class='" + _safety_class(wd_status) + "'>"
                + _e(wd_status) + "</span>"
            ) if wd_status else _e("-")
            # Sprint 5.33 — materials_engine cell. When the item ran
            # the materials_engine backend, show the top-ranked
            # material + known/unknown counts. When not, render "-".
            me_count = it.get("materials_engine_summary_count", 0) or 0
            me_top   = it.get("materials_engine_top_material")
            me_known = it.get("materials_engine_known_count", 0) or 0
            me_unk   = it.get("materials_engine_unknown_count", 0) or 0
            me_warns = it.get("materials_engine_warnings_count", 0) or 0
            if me_count > 0 and me_top:
                me_inner = (
                    "<span style='color:#a78bfa;font-weight:600'>"
                    + _e(me_top) + "</span>"
                    + " <span class='meta'>"
                    + "(known " + _e(me_known)
                    + ", unknown " + _e(me_unk)
                    + (", warn " + _e(me_warns) if me_warns > 0 else "")
                    + ")</span>"
                )
            else:
                me_inner = _e("-")
            # Sprint 5.34 cells.
            mp_hits   = it.get("materials_project_cache_hits", 0) or 0
            mp_misses = it.get("materials_project_cache_misses", 0) or 0
            if mp_hits > 0 or mp_misses > 0:
                mp_inner = (
                    "<span style='color:#7dd3fc;font-weight:600'>"
                    + _e(mp_hits) + " hit"
                    + ("s" if mp_hits != 1 else "")
                    + "</span>"
                    + " <span class='meta'>"
                    + "(" + _e(mp_misses) + " miss"
                    + ("es" if mp_misses != 1 else "")
                    + ")</span>"
                )
            else:
                mp_inner = _e("-")
            wkn = it.get("workers_seen", 0) or 0
            wks = it.get("worker_ids_truncated") or []
            if wkn > 0:
                wkr_inner = (
                    "<span style='font-weight:600'>"
                    + _e(wkn) + "</span>"
                    + " <span class='meta'>("
                    + _e(", ".join(wks))
                    + ")</span>"
                )
            else:
                wkr_inner = _e("-")
            lines.append("<tr>")
            lines.append(
                "<td class='id'>" + _e(it["queue_item_id"]) + "</td>"
            )
            lines.append("<td>" + _e(it["status"]) + "</td>")
            lines.append("<td>" + _e(it["updated_at"]) + "</td>")
            lines.append("<td>" + _e(it["attempt_count"]) + "</td>")
            lines.append(
                "<td>" + _e(it["governor_decisions_count"]) + "</td>"
            )
            lines.append("<td>" + wd_cell + "</td>")
            lines.append("<td>" + me_inner + "</td>")
            lines.append("<td>" + mp_inner + "</td>")
            lines.append("<td>" + wkr_inner + "</td>")
            lines.append(
                "<td class='id'>"
                + _e(it["operator_run_path_basename"] or "-")
                + "</td>"
            )
            lines.append(
                "<td class='id'>"
                + _e(it["watchdog_report_path_basename"] or "-")
                + "</td>"
            )
            lines.append("</tr>")
        lines.append("</tbody></table>")

    lines.append("<h2>Latest batches</h2>")
    if not dashboard["latest_batches"]:
        lines.append("<p class='meta'>no batches recorded yet.</p>")
    else:
        lines.append("<table>")
        lines.append(
            "<thead><tr>"
            "<th>batch_id</th><th>attempted</th>"
            "<th>completed</th><th>failed</th><th>safety_status</th>"
            "</tr></thead>"
        )
        lines.append("<tbody>")
        for b in dashboard["latest_batches"]:
            lines.append("<tr>")
            lines.append(
                "<td class='id'>" + _e(b["batch_id"]) + "</td>"
            )
            lines.append("<td>" + _e(b["attempted_count"]) + "</td>")
            lines.append("<td>" + _e(b["completed_count"]) + "</td>")
            lines.append("<td>" + _e(b["failed_count"]) + "</td>")
            lines.append(
                "<td><span class='"
                + _safety_class(b["safety_status"]) + "'>"
                + _e(b["safety_status"]) + "</span></td>"
            )
            lines.append("</tr>")
        lines.append("</tbody></table>")

    lines.append("<h2>Warnings</h2>")
    if not dashboard["warnings"]:
        lines.append("<p class='meta'>none.</p>")
    else:
        lines.append("<ul class='warnings'>")
        for w in dashboard["warnings"]:
            lines.append("<li>" + _e(w) + "</li>")
        lines.append("</ul>")

    lines.append("</body></html>")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Write outputs
# ---------------------------------------------------------------------------


def write_dashboard(
    dashboard: Dict[str, Any], out_dir: Path,
) -> Tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / (
        "TRINITY_TASK_QUEUE_DASHBOARD_"
        + dashboard["dashboard_id"] + ".json"
    )
    html_path = out_dir / (
        "TRINITY_TASK_QUEUE_DASHBOARD_"
        + dashboard["dashboard_id"] + ".html"
    )
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, indent=2, sort_keys=True)
        f.write("\n")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(render_html(dashboard))
    return json_path, html_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="task_queue_dashboard",
        description=(
            "Trinity Task Queue Dashboard v0.1. Read-only summary "
            "of a queue + its batches. NEVER touches a wallet, "
            "NEVER signs, NEVER broadcasts, NEVER opens the network."
        ),
    )
    p.add_argument("--queue-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--pinned-time", default=None)
    p.add_argument(
        "--latest-limit", type=int, default=DEFAULT_LATEST_LIMIT,
        help=(
            "Cap on the latest_items + latest_batches arrays. "
            "Default " + str(DEFAULT_LATEST_LIMIT) + "."
        ),
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()
    try:
        dash = build_dashboard(
            queue_dir=Path(args.queue_dir),
            pinned_time=pinned,
            latest_limit=int(args.latest_limit),
        )
        json_path, html_path = write_dashboard(dash, Path(args.out_dir))
    except DashboardError as exc:
        print(
            "[task_queue_dashboard] error: " + str(exc),
            file=sys.stderr,
        )
        return 2
    print(
        "[task_queue_dashboard] dashboard_id=" + dash["dashboard_id"]
        + " safety_status=" + dash["safety_status"]
        + " pending=" + str(dash["counts"]["pending"])
        + " running=" + str(dash["counts"]["running"])
        + " completed=" + str(dash["counts"]["completed"])
        + " failed=" + str(dash["counts"]["failed"])
        + " batches=" + str(dash["counts"]["batches"])
        + " json=" + str(json_path)
        + " html=" + str(html_path)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
