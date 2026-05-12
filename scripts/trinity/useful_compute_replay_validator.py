#!/usr/bin/env python3
"""Trinity / Useful Compute — Cross-Worker Replay Validator v0.1.

Compares the results of two or more independent workers that ran the
same Useful Compute request, and decides whether they technically
agree. v0.1 is dry-run only: it emits a validation report and writes
lessons to the error memory; it never pays, never broadcasts, never
touches a wallet, never registers anything on-chain.

Decision matrix
---------------
- ``accepted``              — at least ``--min-workers`` independent
                              workers agree on the same
                              ``compute_output_sha256``.
- ``mismatch``              — workers disagree (more than one
                              compute_output_sha256 seen).
- ``insufficient_workers``  — fewer unique workers than ``--min-workers``.
- ``rejected``              — every loaded result was structurally
                              invalid (wrong schema, wrong request_id,
                              missing fields).
- ``manual_review``         — anomalies (duplicate worker_ids,
                              suspicious result_validated=false) that
                              warrant human inspection.

The validator never decides on its own to issue stocks. Even an
``accepted`` outcome only flips ``manual_review_required=false``;
governance still owns the payment gate.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_VALIDATION = "trinity-useful-compute-validation/v0.1"
SCHEMA_RESULT = "trinity-useful-compute-result/v0.2"
SCHEMA_REQUEST = "trinity-useful-compute-request/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

_RESULT_REQUIRED = {
    "schema", "request_id", "worker_id", "task_type",
    "input_bundle_sha256", "compute_output_sha256",
    "worker_result_id", "started_at", "finished_at",
    "elapsed_seconds", "result_validated", "duplicate_result",
    "public_summary", "safety_status",
}


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
# Result validation (minimal, hand-rolled to avoid jsonschema dependency)
# ---------------------------------------------------------------------------


def _structural_problem(result: Dict[str, Any]) -> Optional[str]:
    if not isinstance(result, dict):
        return "not an object"
    missing = _RESULT_REQUIRED - set(result.keys())
    if missing:
        return f"missing fields: {sorted(missing)}"
    if result.get("schema") != SCHEMA_RESULT:
        return f"wrong schema: {result.get('schema')!r}"
    rid = result.get("request_id", "")
    if not re.match(r"^uc-[0-9a-f]{16,64}$", rid):
        return f"bad request_id: {rid!r}"
    wrid = result.get("worker_result_id", "")
    if not re.match(r"^[0-9a-f]{16}$", wrid):
        return f"bad worker_result_id: {wrid!r}"
    cos = result.get("compute_output_sha256", "")
    if not re.match(r"^[0-9a-f]{64}$", cos):
        return f"bad compute_output_sha256: {cos!r}"
    return None


# ---------------------------------------------------------------------------
# Core: validate replay
# ---------------------------------------------------------------------------


def _load_results_from_dir(
    results_dir: Path,
    request_id: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Return (matching_results, structural_rejections).

    ``matching_results`` is the list of results whose request_id
    matches and that survived structural validation.
    ``structural_rejections`` is a list of
    ``{worker_result_id?, reason}`` records for everything else.
    """
    matching: List[Dict[str, Any]] = []
    rejections: List[Dict[str, str]] = []
    if not results_dir.exists():
        return matching, rejections

    files = sorted(
        results_dir.glob(f"TRINITY_USEFUL_COMPUTE_RESULT_{request_id}_*.json")
    )
    for p in files:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rejections.append({
                "worker_result_id": "0" * 16,
                "reason": f"file {p.name}: invalid JSON",
            })
            continue
        prob = _structural_problem(obj)
        if prob is not None:
            wrid = obj.get("worker_result_id", "0" * 16) \
                if isinstance(obj, dict) else "0" * 16
            if not re.match(r"^[0-9a-f]{16}$", wrid or ""):
                wrid = "0" * 16
            rejections.append({
                "worker_result_id": wrid,
                "reason": f"file {p.name}: {prob}",
            })
            continue
        if obj.get("request_id") != request_id:
            rejections.append({
                "worker_result_id": obj.get(
                    "worker_result_id", "0" * 16,
                ),
                "reason": (
                    f"file {p.name}: request_id "
                    f"{obj.get('request_id')!r} != {request_id!r}"
                ),
            })
            continue
        matching.append(obj)
    return matching, rejections


def run_validation(
    *,
    request: Dict[str, Any],
    results_dir: Path,
    out_dir: Path,
    min_workers: int,
    pinned_time: str,
    error_memory_ledger: Optional[Path] = None,
) -> Dict[str, Any]:
    if min_workers < 2:
        raise ValueError("min_workers must be >= 2")

    rid = request.get("request_id")
    if not (isinstance(rid, str) and re.match(r"^uc-[0-9a-f]{16,64}$", rid)):
        raise ValueError(f"invalid request_id in manifest: {rid!r}")

    out_dir.mkdir(parents=True, exist_ok=True)
    matching, rejections = _load_results_from_dir(results_dir, rid)

    # Detect duplicate worker_ids — only the first submission counts;
    # the rest are rejected as duplicate_worker_result.
    seen_workers: Dict[str, str] = {}
    deduped: List[Dict[str, Any]] = []
    for r in matching:
        wid = r.get("worker_id", "")
        if wid in seen_workers:
            rejections.append({
                "worker_result_id": r.get(
                    "worker_result_id", "0" * 16,
                ),
                "reason": (
                    f"duplicate_worker_result: worker_id {wid!r} "
                    f"already submitted "
                    f"{seen_workers[wid]}"
                ),
            })
            continue
        seen_workers[wid] = r.get("worker_result_id", "")
        deduped.append(r)

    workers_seen = len(matching) + sum(
        1 for r in rejections if "duplicate_worker_result" in r["reason"]
    )
    unique_workers = len(deduped)

    # Group by compute_output_sha256.
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in deduped:
        cos = r["compute_output_sha256"]
        groups.setdefault(cos, []).append(r)

    accepted_cos: Optional[str] = None
    matching_result_ids: List[str] = []
    mismatch_groups: List[Dict[str, Any]] = []
    manual_review = False
    status = "rejected"

    if unique_workers == 0:
        status = "rejected" if rejections else "insufficient_workers"
        manual_review = bool(rejections)
    elif unique_workers < min_workers:
        status = "insufficient_workers"
        manual_review = False
    else:
        # Find the largest agreeing group.
        ordered = sorted(
            groups.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        )
        biggest_cos, biggest_group = ordered[0]
        if len(biggest_group) >= min_workers and len(groups) == 1:
            status = "accepted"
            accepted_cos = biggest_cos
            matching_result_ids = sorted(
                r["worker_result_id"] for r in biggest_group
            )
            manual_review = False
        elif len(biggest_group) >= min_workers and len(groups) > 1:
            status = "mismatch"
            accepted_cos = None
            manual_review = True
            for cos, members in ordered:
                mismatch_groups.append({
                    "compute_output_sha256": cos,
                    "worker_result_ids": sorted(
                        m["worker_result_id"] for m in members
                    ),
                })
        else:
            status = "mismatch"
            accepted_cos = None
            manual_review = True
            for cos, members in ordered:
                mismatch_groups.append({
                    "compute_output_sha256": cos,
                    "worker_result_ids": sorted(
                        m["worker_result_id"] for m in members
                    ),
                })

    # If any result self-reported result_validated=false, flag manual.
    for r in deduped:
        if r.get("result_validated") is False:
            manual_review = True

    validation_id = "val-" + _sha16(canonical_dumps({
        "rid": rid, "status": status,
        "accepted_cos": accepted_cos,
        "matching": matching_result_ids,
        "rejected": sorted(
            r["worker_result_id"] for r in rejections
        ),
        "mismatch": [
            {
                "cos": g["compute_output_sha256"],
                "ids": g["worker_result_ids"],
            }
            for g in mismatch_groups
        ],
        "min_workers": min_workers,
    }))

    report = {
        "schema": SCHEMA_VALIDATION,
        "validation_id": validation_id,
        "request_id": rid,
        "mode": "local-dry-run",
        "min_workers": min_workers,
        "workers_seen": workers_seen,
        "unique_workers": unique_workers,
        "accepted_compute_output_sha256": accepted_cos,
        "validation_status": status,
        "matching_result_ids": matching_result_ids,
        "rejected_result_ids": sorted(
            rejections, key=lambda r: r["worker_result_id"],
        ),
        "mismatch_groups": mismatch_groups,
        "manual_review_required": bool(manual_review),
        "safety_status": {
            "no_wallet_access":                   True,
            "no_private_keys":                    True,
            "no_automatic_payout":                True,
            "no_network_required":                True,
            "no_onchain_registration":            True,
            "governance_required_before_payment": True,
        },
    }

    # Persist.
    report_path = (
        out_dir / f"TRINITY_USEFUL_COMPUTE_VALIDATION_{rid}.json"
    )
    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_VALIDATION_SUMMARY.md"
    )
    report_path.write_text(canonical_dumps(report), encoding="utf-8")
    summary_path.write_text(
        _render_summary_md(report, request), encoding="utf-8",
    )

    # Record lessons in the error memory ledger.
    if error_memory_ledger is not None:
        em_mod = _load(
            "ucv_error_mem",
            _SCRIPTS_DIR / "trinity_error_memory.py",
        )
        if status == "mismatch":
            em_mod.record_lesson(
                ledger_path=error_memory_ledger,
                vertical="useful_compute",
                task_inputs={
                    "request_id": rid,
                    "groups": [g["compute_output_sha256"]
                               for g in mismatch_groups],
                },
                cause="overclaim_risk",
                detail=(
                    f"cross_worker_mismatch: {len(mismatch_groups)} "
                    f"distinct compute_output_sha256 groups across "
                    f"{unique_workers} workers"
                ),
                pinned_time=pinned_time,
            )
        elif status == "insufficient_workers":
            em_mod.record_lesson(
                ledger_path=error_memory_ledger,
                vertical="useful_compute",
                task_inputs={"request_id": rid},
                cause="insufficient_evidence",
                detail=(
                    f"insufficient_replay_workers: "
                    f"{unique_workers}/{min_workers}"
                ),
                pinned_time=pinned_time,
            )
        # Duplicate-worker rejections also worth recording.
        for rej in rejections:
            if "duplicate_worker_result" in rej["reason"]:
                em_mod.record_lesson(
                    ledger_path=error_memory_ledger,
                    vertical="useful_compute",
                    task_inputs={
                        "request_id": rid,
                        "worker_result_id": rej["worker_result_id"],
                    },
                    cause="duplicate_candidate",
                    detail="duplicate_worker_result: " + rej["reason"],
                    pinned_time=pinned_time,
                )

    return report


def _render_summary_md(
    report: Dict[str, Any], request: Dict[str, Any],
) -> str:
    lines = [
        "# TRINITY USEFUL COMPUTE — VALIDATION SUMMARY",
        "",
        f"- schema: `{report['schema']}`",
        f"- validation_id: `{report['validation_id']}`",
        f"- request_id: `{report['request_id']}`",
        f"- task_type: `{request.get('task_type', '?')}`",
        f"- mode: `{report['mode']}`",
        "",
        "## Result",
        "",
        f"- validation_status: **{report['validation_status']}**",
        f"- workers_seen: {report['workers_seen']}",
        f"- unique_workers: {report['unique_workers']}",
        f"- min_workers required: {report['min_workers']}",
        f"- accepted_compute_output_sha256: "
        f"`{report['accepted_compute_output_sha256']}`",
        f"- manual_review_required: "
        f"**{report['manual_review_required']}**",
        "",
        "## Matching worker_result_ids",
        "",
    ]
    if report["matching_result_ids"]:
        for w in report["matching_result_ids"]:
            lines.append(f"- `{w}`")
    else:
        lines.append("_none_")
    lines.extend(["", "## Rejected results", ""])
    if report["rejected_result_ids"]:
        for r in report["rejected_result_ids"]:
            lines.append(
                f"- `{r['worker_result_id']}` — {r['reason']}"
            )
    else:
        lines.append("_none_")
    lines.extend(["", "## Mismatch groups", ""])
    if report["mismatch_groups"]:
        for g in report["mismatch_groups"]:
            lines.append(
                f"- `{g['compute_output_sha256']}` x"
                f"{len(g['worker_result_ids'])} workers"
            )
    else:
        lines.append("_none_")
    lines.extend([
        "",
        "## Safety",
        "",
        "- no automatic payout",
        "- no on-chain registration",
        "- governance required before any payment",
        "- this report is a dry-run technical agreement check, not a",
        "  scientific validation; human review is still required.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_replay_validator",
        description=(
            "Cross-worker replay validator for Trinity Useful Compute "
            "requests. Compares two or more worker results, emits a "
            "validation report. Never pays."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument("--request", required=True)
    p.add_argument("--results-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--min-workers", type=int, default=2)
    p.add_argument(
        "--pinned-time",
        default="2026-05-12T00:00:00+00:00",
    )
    p.add_argument(
        "--error-memory-ledger", default=None,
        help=(
            "Optional path to a Trinity error memory JSONL ledger. "
            "If supplied, the validator records lessons for "
            "mismatch / insufficient / duplicate outcomes."
        ),
    )
    # Hard-rejection guards.
    p.add_argument("--broadcast", action="store_true", help="REJECTED")
    p.add_argument("--payout",    action="store_true", help="REJECTED")
    p.add_argument("--send",      action="store_true", help="REJECTED")
    p.add_argument("--wallet",    type=str, default=None, help="REJECTED")
    p.add_argument("--network",   action="store_true", help="REJECTED")
    args = p.parse_args(argv)

    if args.mode != "local-dry-run":
        print(
            "[useful_compute_replay_validator] only local-dry-run "
            "is supported in v0.1",
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
                f"[useful_compute_replay_validator] flag {flag_name} "
                "is rejected in v0.1",
                file=sys.stderr,
            )
            return 2
    if args.wallet is not None:
        print(
            "[useful_compute_replay_validator] --wallet is rejected "
            "in v0.1; this validator NEVER touches wallets or keys",
            file=sys.stderr,
        )
        return 2

    request_path = Path(args.request)
    if not request_path.exists():
        print(
            f"[useful_compute_replay_validator] request not found: "
            f"{request_path}",
            file=sys.stderr,
        )
        return 2

    request = json.loads(request_path.read_text(encoding="utf-8"))
    report = run_validation(
        request=request,
        results_dir=Path(args.results_dir),
        out_dir=Path(args.out_dir),
        min_workers=args.min_workers,
        pinned_time=args.pinned_time,
        error_memory_ledger=(
            Path(args.error_memory_ledger)
            if args.error_memory_ledger else None
        ),
    )

    print(
        f"[useful_compute_replay_validator] request_id="
        f"{report['request_id']} status={report['validation_status']}"
    )
    print(
        f"[useful_compute_replay_validator] workers_seen="
        f"{report['workers_seen']}, "
        f"unique_workers={report['unique_workers']}, "
        f"min_workers={report['min_workers']}"
    )
    print(
        f"[useful_compute_replay_validator] accepted_cos="
        f"{report['accepted_compute_output_sha256']}"
    )
    print(
        f"[useful_compute_replay_validator] manual_review_required="
        f"{report['manual_review_required']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
