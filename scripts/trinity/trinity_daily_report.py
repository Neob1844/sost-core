#!/usr/bin/env python3
"""Trinity Daily Report v0.1 (Sprint 5.39).

Produces a human-readable static daily report from an existing
Sprint 5.28 task-queue dashboard JSON plus the queue directory.
Emits both a JSON daily report (machine-readable) and a Markdown
daily report (human-readable). NO HTML, NO JS, NO external
assets, NO network, NO secrets.

Hard invariants v0.1 (enforced by static tests):
    - Read-only on the source dashboard + queue dir. Never moves
      items, never runs the operator loop, never invokes the
      watchdog.
    - No network. No DNS. No child process. No shell. No eval / exec.
    - No wallet, no private key, no signing, no broadcast.
    - Markdown output has NO absolute paths (only basenames) and
      NO 64-hex blobs that look like private keys (only sha256s
      bound to a label).
    - Deterministic for fixed inputs.

Usage:
    python3 scripts/trinity/trinity_daily_report.py \\
        --dashboard-json /var/lib/trinity/dashboards/TRINITY_TASK_QUEUE_DASHBOARD_dsh-<id>.json \\
        --queue-dir      /var/lib/trinity/queues/main \\
        --out-json       /var/lib/trinity/daily-reports/TRINITY_DAILY_REPORT_<id>.json \\
        --out-md         /var/lib/trinity/daily-reports/TRINITY_DAILY_REPORT_<id>.md \\
        --pinned-time 2026-05-18T00:00:00+00:00
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os.path
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_DAILY_REPORT = "trinity-daily-report/v0.1"
SCHEMA_DASHBOARD = "trinity-task-queue-dashboard/v0.1"


class DailyReportError(Exception):
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


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _safe_basename(s: Optional[str]) -> Optional[str]:
    if s is None or not isinstance(s, str) or not s:
        return None
    name = os.path.basename(s)
    return name or None


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


def build_daily_report(
    *,
    dashboard_json: Path,
    queue_dir: Optional[Path],
    pinned_time: str,
) -> Dict[str, Any]:
    dashboard = _read_json(dashboard_json)
    if dashboard is None:
        raise DailyReportError(
            "dashboard JSON not readable: " + str(dashboard_json)
        )
    if dashboard.get("schema") != SCHEMA_DASHBOARD:
        raise DailyReportError(
            "dashboard JSON wrong schema (need "
            + SCHEMA_DASHBOARD + "): " + str(dashboard.get("schema"))
        )

    counts = dashboard.get("counts", {}) or {}
    latest_items = dashboard.get("latest_items", []) or []
    latest_batches = dashboard.get("latest_batches", []) or []

    # Aggregate across latest_items.
    top_materials: List[str] = []
    cache_hits_total = 0
    cache_misses_total = 0
    workers_seen_total = 0
    worker_id_set: List[str] = []
    failed_items: List[Dict[str, Any]] = []
    completed_items: List[Dict[str, Any]] = []

    for it in latest_items:
        status = str(it.get("status", ""))
        if status == "completed":
            completed_items.append({
                "queue_item_id":
                    str(it.get("queue_item_id", ""))[:64],
                "top_material":
                    (str(it.get("materials_engine_top_material") or "")
                     or None),
                "materials_engine_known_count":
                    int(it.get("materials_engine_known_count", 0) or 0),
                "materials_engine_unknown_count":
                    int(it.get("materials_engine_unknown_count", 0) or 0),
                "materials_project_cache_hits":
                    int(it.get("materials_project_cache_hits", 0) or 0),
                "materials_project_cache_misses":
                    int(it.get("materials_project_cache_misses", 0) or 0),
                "workers_seen":
                    int(it.get("workers_seen", 0) or 0),
            })
        if status == "failed":
            failed_items.append({
                "queue_item_id":
                    str(it.get("queue_item_id", ""))[:64],
                "watchdog_safety_status":
                    it.get("watchdog_safety_status"),
            })
        tm = it.get("materials_engine_top_material")
        if isinstance(tm, str) and tm and tm not in top_materials:
            top_materials.append(tm[:64])
        cache_hits_total   += int(
            it.get("materials_project_cache_hits", 0) or 0
        )
        cache_misses_total += int(
            it.get("materials_project_cache_misses", 0) or 0
        )
        workers_seen_total += int(it.get("workers_seen", 0) or 0)
        for wid in it.get("worker_ids_truncated", []) or []:
            if isinstance(wid, str) and wid and wid not in worker_id_set:
                worker_id_set.append(wid[:32])

    top_materials_sorted = sorted(top_materials)
    worker_id_set_sorted = sorted(worker_id_set)

    # Optional: look for drafts/proposals in queue-dir.
    drafts_proposals_count = 0
    drafts_proposals_basenames: List[str] = []
    if queue_dir is not None:
        for it in latest_items:
            qid = str(it.get("queue_item_id", "") or "")
            if not qid:
                continue
            draft_dir = queue_dir / "reports" / qid / "operator_run"
            if not draft_dir.exists():
                continue
            for f in sorted(draft_dir.glob(
                "TRINITY_PAYMENT_DRAFT_*.json",
            )):
                drafts_proposals_count += 1
                drafts_proposals_basenames.append(f.name)
            for f in sorted(draft_dir.glob(
                "TRINITY_PAYMENT_PROPOSAL_*.json",
            )):
                drafts_proposals_count += 1
                drafts_proposals_basenames.append(f.name)

    safety_status = str(dashboard.get("safety_status", "ok"))

    report_id = "tdr-" + _sha16(_canonical_dumps({
        "pinned_time":            pinned_time,
        "source_dashboard_basename":
            _safe_basename(str(dashboard_json)) or "",
        "queue_dir_basename":
            (queue_dir.name if queue_dir is not None else ""),
        "dashboard_id": dashboard.get("dashboard_id", ""),
    }))

    return {
        "schema":             SCHEMA_DAILY_REPORT,
        "report_id":          report_id,
        "pinned_time":        pinned_time,
        "source_dashboard_basename":
            _safe_basename(str(dashboard_json)) or "",
        "queue_dir_basename":
            (queue_dir.name if queue_dir is not None else ""),
        "source_dashboard_id":
            str(dashboard.get("dashboard_id", "")),
        "counts": {
            "pending":   int(counts.get("pending",   0) or 0),
            "running":   int(counts.get("running",   0) or 0),
            "completed": int(counts.get("completed", 0) or 0),
            "failed":    int(counts.get("failed",    0) or 0),
            "batches":   int(counts.get("batches",   0) or 0),
        },
        "completed_items":  completed_items[:50],
        "failed_items":     failed_items[:50],
        "top_materials":    top_materials_sorted,
        "cache_hits_total": int(cache_hits_total),
        "cache_misses_total": int(cache_misses_total),
        "workers_seen_total": int(workers_seen_total),
        "worker_ids":       worker_id_set_sorted,
        "warnings":         list(dashboard.get("warnings", []) or []),
        "drafts_proposals_count": int(drafts_proposals_count),
        "drafts_proposals_basenames":
            drafts_proposals_basenames[:50],
        "safety_status":    safety_status,
        "safety_flags": {
            "no_wallet":             True,
            "no_private_key":        True,
            "no_signing":            True,
            "no_broadcast":          True,
            "no_autonomous_payment": True,
            "no_network":            True,
        },
        "latest_batches_count": len(latest_batches),
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(report: Dict[str, Any]) -> str:
    lines: List[str] = []
    a = lines.append
    a("# Trinity Daily Report")
    a("")
    a("**Report id:** `" + str(report["report_id"]) + "`  ")
    a("**Pinned time:** `" + str(report["pinned_time"]) + "`  ")
    a("**Source dashboard:** `"
      + str(report["source_dashboard_basename"]) + "`  ")
    a("**Queue dir:** `" + str(report["queue_dir_basename"]) + "`  ")
    a("**Safety status:** `" + str(report["safety_status"]) + "`")
    a("")
    a("## Counts")
    a("")
    a("| pending | running | completed | failed | batches |")
    a("|---:|---:|---:|---:|---:|")
    c = report["counts"]
    a(
        "| " + str(c["pending"]) + " | " + str(c["running"]) + " | "
        + str(c["completed"]) + " | " + str(c["failed"]) + " | "
        + str(c["batches"]) + " |"
    )
    a("")
    a("## Top materials")
    a("")
    if report["top_materials"]:
        for m in report["top_materials"]:
            a("- `" + str(m) + "`")
    else:
        a("- _none_")
    a("")
    a("## Materials cache")
    a("")
    a(
        "- cache_hits_total: **" + str(report["cache_hits_total"])
        + "**"
    )
    a(
        "- cache_misses_total: **" + str(report["cache_misses_total"])
        + "**"
    )
    a("")
    a("## Workers seen")
    a("")
    a(
        "- workers_seen_total: **" + str(report["workers_seen_total"])
        + "**"
    )
    if report["worker_ids"]:
        a("- worker_ids:")
        for w in report["worker_ids"]:
            a("    - `" + str(w) + "`")
    else:
        a("- _no worker_ids in dashboard scope_")
    a("")
    a("## Completed items")
    a("")
    if report["completed_items"]:
        a("| queue_item_id | top_material | known | unknown | "
          "cache_hits | cache_misses | workers |")
        a("|---|---|---:|---:|---:|---:|---:|")
        for it in report["completed_items"]:
            a(
                "| `" + str(it["queue_item_id"]) + "` | "
                + (("`" + str(it["top_material"]) + "`")
                   if it.get("top_material") else "_-_") + " | "
                + str(it["materials_engine_known_count"]) + " | "
                + str(it["materials_engine_unknown_count"]) + " | "
                + str(it["materials_project_cache_hits"]) + " | "
                + str(it["materials_project_cache_misses"]) + " | "
                + str(it["workers_seen"]) + " |"
            )
    else:
        a("- _none_")
    a("")
    a("## Failed items")
    a("")
    if report["failed_items"]:
        a("| queue_item_id | watchdog_safety_status |")
        a("|---|---|")
        for it in report["failed_items"]:
            a(
                "| `" + str(it["queue_item_id"]) + "` | "
                + str(it.get("watchdog_safety_status") or "_-_")
                + " |"
            )
    else:
        a("- _none_")
    a("")
    a("## Drafts / proposals")
    a("")
    a("- drafts_proposals_count: **"
      + str(report["drafts_proposals_count"]) + "**")
    if report["drafts_proposals_basenames"]:
        for n in report["drafts_proposals_basenames"]:
            a("    - `" + str(n) + "`")
    a("")
    a("## Warnings")
    a("")
    if report["warnings"]:
        for w in report["warnings"]:
            a("- " + str(w))
    else:
        a("- _none_")
    a("")
    a("## Safety flags")
    a("")
    for k, v in sorted(report["safety_flags"].items()):
        a("- `" + k + "`: **" + ("true" if v else "false") + "**")
    a("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trinity_daily_report",
        description=(
            "Trinity Daily Report v0.1. Reads a task-queue "
            "dashboard JSON and emits a JSON + Markdown daily "
            "report. NEVER touches a wallet, NEVER signs, "
            "NEVER broadcasts, NEVER opens the network."
        ),
    )
    p.add_argument("--dashboard-json", required=True)
    p.add_argument("--queue-dir", default=None)
    p.add_argument("--out-json", required=True)
    p.add_argument("--out-md", required=True)
    p.add_argument("--pinned-time", default=None)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    pinned = args.pinned_time or _utc_now()
    queue_dir = (
        Path(args.queue_dir) if args.queue_dir else None
    )
    try:
        report = build_daily_report(
            dashboard_json=Path(args.dashboard_json),
            queue_dir=queue_dir,
            pinned_time=pinned,
        )
    except DailyReportError as exc:
        print(
            "[trinity_daily_report] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    out_md.write_text(render_markdown(report), encoding="utf-8")

    print(
        "[trinity_daily_report] report_id=" + report["report_id"]
        + " completed=" + str(report["counts"]["completed"])
        + " failed=" + str(report["counts"]["failed"])
        + " top_materials=" + str(len(report["top_materials"]))
        + " workers_seen_total=" + str(report["workers_seen_total"])
        + " safety_status=" + report["safety_status"]
        + " json=" + str(out_json)
        + " md=" + str(out_md)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
