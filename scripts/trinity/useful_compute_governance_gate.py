#!/usr/bin/env python3
"""Trinity / Useful Compute — Governance Gate v0.1.

Takes a directory of replay-validation reports (Sprint 5.8) plus a
directory of pending reward reports (Sprint 5.7) and produces a
deterministic, review-only governance batch:

- Approves only validations whose status is ``accepted``, whose
  ``manual_review_required`` is false, whose ``safety_status`` is
  fully checked, and whose matching worker_result_ids have matching,
  non-duplicate pending reward reports for the SAME request_id.
- Computes ``approved_pending_reward_stocks`` under the
  ``conservative`` policy: ``min(pending_reward_stocks across the
  matching workers)``. The intuition: until governance signs off,
  promise no worker more than the floor agreed by the cheapest
  honest replicator.
- v0.1 NEVER pays, NEVER touches a wallet, NEVER broadcasts,
  NEVER registers on-chain. The output is a review packet for the
  next sprint to act on.

Rejection causes (closed taxonomy, also logged into
``trinity_error_memory`` when an error_memory ledger path is
supplied):

- ``governance_rejected_mismatch``
- ``governance_rejected_insufficient_workers``
- ``governance_rejected_manual_review``
- ``governance_rejected_missing_reward``
- ``governance_rejected_duplicate_reward``
- ``governance_rejected_unsafe_status``
- ``governance_rejected_extra_reward``      — pending reward exists
  for a worker_result_id that is NOT in ``matching_result_ids``
- ``governance_rejected_invalid_structure`` — validation or reward
  file failed structural checks
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


SCHEMA_BATCH = "trinity-useful-compute-governance-batch/v0.1"
SCHEMA_VALIDATION = "trinity-useful-compute-validation/v0.1"
SCHEMA_REWARD = "trinity-useful-compute-pending-reward/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent

_VALIDATION_REQUIRED = {
    "schema", "validation_id", "request_id", "mode",
    "min_workers", "workers_seen", "unique_workers",
    "accepted_compute_output_sha256", "validation_status",
    "matching_result_ids", "rejected_result_ids",
    "mismatch_groups", "manual_review_required",
    "safety_status",
}

_REWARD_REQUIRED = {
    "schema", "request_id", "worker_id", "pending_reward_stocks",
    "reason", "requires_manual_review", "reward_model_schema",
    "reward_model_deterministic_id", "safety_status",
}

_REWARD_SAFETY_FLAGS = (
    "no_wallet_access", "no_private_keys",
    "no_automatic_payout", "no_network_required",
    "manual_review_required",
)

_VALIDATION_SAFETY_FLAGS = (
    "no_wallet_access", "no_private_keys",
    "no_automatic_payout", "no_network_required",
    "no_onchain_registration",
    "governance_required_before_payment",
)


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
# Structural validation (hand-rolled)
# ---------------------------------------------------------------------------


def _validation_problem(obj: Any) -> Optional[str]:
    if not isinstance(obj, dict):
        return "not an object"
    missing = _VALIDATION_REQUIRED - set(obj.keys())
    if missing:
        return f"missing fields: {sorted(missing)}"
    if obj.get("schema") != SCHEMA_VALIDATION:
        return f"wrong schema: {obj.get('schema')!r}"
    rid = obj.get("request_id", "")
    if not re.match(r"^uc-[0-9a-f]{16,64}$", rid):
        return f"bad request_id: {rid!r}"
    vid = obj.get("validation_id", "")
    if not re.match(r"^val-[0-9a-f]{16}$", vid):
        return f"bad validation_id: {vid!r}"
    ss = obj.get("safety_status")
    if not isinstance(ss, dict):
        return "safety_status not an object"
    for flag in _VALIDATION_SAFETY_FLAGS:
        if ss.get(flag) is not True:
            return f"safety_status.{flag} is not True"
    return None


def _reward_problem(obj: Any) -> Optional[str]:
    if not isinstance(obj, dict):
        return "not an object"
    missing = _REWARD_REQUIRED - set(obj.keys())
    if missing:
        return f"missing fields: {sorted(missing)}"
    if obj.get("schema") != SCHEMA_REWARD:
        return f"wrong reward schema: {obj.get('schema')!r}"
    rid = obj.get("request_id", "")
    if not re.match(r"^uc-[0-9a-f]{16,64}$", rid):
        return f"bad request_id: {rid!r}"
    stocks = obj.get("pending_reward_stocks")
    if not (isinstance(stocks, int) and stocks >= 0):
        return f"bad pending_reward_stocks: {stocks!r}"
    ss = obj.get("safety_status")
    if not isinstance(ss, dict):
        return "reward safety_status not an object"
    for flag in _REWARD_SAFETY_FLAGS:
        if ss.get(flag) is not True:
            return f"reward safety_status.{flag} is not True"
    return None


# ---------------------------------------------------------------------------
# Filename parsing for worker_result_id extraction (Sprint 5.7 schema does
# not carry worker_result_id inside the reward file body; v0.1 governance
# reads it from the canonical file name).
# ---------------------------------------------------------------------------


_REWARD_NAME_RE = re.compile(
    r"^TRINITY_USEFUL_COMPUTE_PENDING_REWARD_"
    r"(uc-[0-9a-f]{16,64})_([0-9a-f]{16})\.json$"
)


def _extract_reward_ids(path: Path) -> Optional[Tuple[str, str]]:
    m = _REWARD_NAME_RE.match(path.name)
    if not m:
        return None
    return m.group(1), m.group(2)


def _load_rewards_index(
    rewards_dir: Path,
) -> Tuple[Dict[Tuple[str, str], Dict[str, Any]],
           List[Tuple[Tuple[str, str], str]],
           List[Path]]:
    """Index pending rewards by (request_id, worker_result_id).

    Returns (index, duplicates, ignored_paths). ``duplicates`` is a
    list of ((rid, wrid), reason) entries — if the same (rid, wrid)
    appears in two files, ALL of them are marked duplicate (so the
    validation that owns them gets rejected).
    """
    index: Dict[Tuple[str, str], Dict[str, Any]] = {}
    seen: Dict[Tuple[str, str], int] = {}
    duplicates: List[Tuple[Tuple[str, str], str]] = []
    ignored: List[Path] = []
    if not rewards_dir.exists():
        return index, duplicates, ignored

    files = sorted(
        rewards_dir.glob("TRINITY_USEFUL_COMPUTE_PENDING_REWARD_*.json")
    )
    for p in files:
        ids = _extract_reward_ids(p)
        if ids is None:
            ignored.append(p)
            continue
        rid, wrid = ids
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ignored.append(p)
            continue
        prob = _reward_problem(obj)
        if prob is not None:
            ignored.append(p)
            continue
        if obj.get("request_id") != rid:
            ignored.append(p)
            continue
        seen[(rid, wrid)] = seen.get((rid, wrid), 0) + 1
        if (rid, wrid) in index:
            duplicates.append((
                (rid, wrid),
                f"duplicate pending reward for {wrid} in {p.name}",
            ))
            continue
        index[(rid, wrid)] = obj
    # Promote any (rid, wrid) seen more than once to duplicates.
    for key, n in seen.items():
        if n > 1:
            duplicates.append((
                key,
                f"pending reward {key[1]} appears {n} times",
            ))
    return index, duplicates, ignored


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


def _conservative_approved_reward(rewards: List[Dict[str, Any]]) -> int:
    """Return the minimum pending_reward_stocks across the supplied
    reward reports. Empty list returns 0 (caller must reject)."""
    if not rewards:
        return 0
    return min(int(r["pending_reward_stocks"]) for r in rewards)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def _evaluate_validation(
    val: Dict[str, Any],
    rewards_index: Dict[Tuple[str, str], Dict[str, Any]],
    duplicate_keys: List[Tuple[str, str]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Decide whether one validation passes the gate. Returns
    (approved_item, None) on success or (None, rejection_reason)
    on failure."""
    rid = val["request_id"]
    vid = val["validation_id"]
    status = val["validation_status"]
    if status == "mismatch":
        return None, "governance_rejected_mismatch"
    if status == "insufficient_workers":
        return None, "governance_rejected_insufficient_workers"
    if status not in ("accepted",):
        return None, "governance_rejected_invalid_structure"
    if val.get("manual_review_required") is True:
        return None, "governance_rejected_manual_review"
    cos = val.get("accepted_compute_output_sha256")
    if not (isinstance(cos, str) and re.match(r"^[0-9a-f]{64}$", cos)):
        return None, "governance_rejected_invalid_structure"
    mw = int(val.get("min_workers", 0))
    uw = int(val.get("unique_workers", 0))
    if uw < mw:
        return None, "governance_rejected_insufficient_workers"

    matching = val.get("matching_result_ids", [])
    if not (isinstance(matching, list) and len(matching) >= mw):
        return None, "governance_rejected_insufficient_workers"

    # Per-validation duplicate guard.
    rid_dup_keys = {k for k in duplicate_keys if k[0] == rid}
    if rid_dup_keys:
        return None, "governance_rejected_duplicate_reward"

    # Pending rewards must exist for every matching_result_id.
    collected: List[Dict[str, Any]] = []
    for wrid in matching:
        rew = rewards_index.get((rid, wrid))
        if rew is None:
            return None, "governance_rejected_missing_reward"
        collected.append(rew)

    approved = _conservative_approved_reward(collected)

    item = {
        "request_id": rid,
        "validation_id": vid,
        "accepted_compute_output_sha256": cos,
        "matching_result_ids": sorted(matching),
        "unique_workers": uw,
        "approved_pending_reward_stocks": approved,
        "reason": (
            f"conservative=min({len(collected)} pending rewards); "
            f"unique_workers={uw}>=min_workers={mw}"
        ),
    }
    return item, None


def _scan_extra_rewards(
    rewards_index: Dict[Tuple[str, str], Dict[str, Any]],
    validations: List[Dict[str, Any]],
) -> List[str]:
    """Return a list of human-readable reasons describing pending
    rewards that exist for (rid, wrid) pairs NOT contained in any
    accepted validation's matching_result_ids."""
    accepted = set()
    for v in validations:
        rid = v.get("request_id", "")
        if v.get("validation_status") != "accepted":
            continue
        for w in v.get("matching_result_ids", []):
            accepted.add((rid, w))
    extra: List[str] = []
    for key in rewards_index:
        rid, wrid = key
        if any(v.get("request_id") == rid
               and v.get("validation_status") == "accepted"
               for v in validations):
            if key not in accepted:
                extra.append(
                    f"extra reward {wrid} for request {rid} is not in "
                    f"matching_result_ids"
                )
    return extra


def run_governance_gate(
    *,
    validations_dir: Path,
    rewards_dir: Path,
    out_dir: Path,
    reviewer_id: str,
    policy: str,
    pinned_time: str,
    error_memory_ledger: Optional[Path] = None,
) -> Dict[str, Any]:
    if policy not in ("conservative",):
        raise ValueError(f"unsupported policy: {policy!r}")
    if not (isinstance(reviewer_id, str) and 1 <= len(reviewer_id) <= 128):
        raise ValueError("reviewer_id must be 1..128 chars")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load validation reports.
    validations: List[Dict[str, Any]] = []
    invalid_validations: List[Tuple[str, str, str]] = []
    if validations_dir.exists():
        for p in sorted(
            validations_dir.glob(
                "TRINITY_USEFUL_COMPUTE_VALIDATION_*.json"
            )
        ):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                invalid_validations.append(
                    ("?", "?", f"file {p.name}: invalid JSON")
                )
                continue
            prob = _validation_problem(obj)
            if prob is not None:
                invalid_validations.append((
                    obj.get("request_id", "?") if isinstance(obj, dict)
                    else "?",
                    obj.get("validation_id", "?") if isinstance(obj, dict)
                    else "?",
                    f"file {p.name}: {prob}",
                ))
                continue
            validations.append(obj)

    # Load rewards.
    rewards_index, dup_pairs, _ignored_paths = \
        _load_rewards_index(rewards_dir)
    duplicate_keys = [k for k, _r in dup_pairs]

    approved: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []

    for v in validations:
        item, why = _evaluate_validation(v, rewards_index, duplicate_keys)
        if item is not None:
            approved.append(item)
        else:
            rejected.append({
                "request_id": v.get("request_id", "?"),
                "validation_id": v.get("validation_id", "?"),
                "reason": why or "governance_rejected_invalid_structure",
            })

    # Structurally invalid validations end up in rejected too.
    for rid, vid, reason in invalid_validations:
        rejected.append({
            "request_id": rid, "validation_id": vid,
            "reason": "governance_rejected_invalid_structure: " + reason,
        })

    # Extra rewards (worker_result_id not in matching_result_ids).
    for reason in _scan_extra_rewards(rewards_index, validations):
        rejected.append({
            "request_id": reason.split(" for request ")[-1].split(" ")[0],
            "validation_id": "n/a",
            "reason": "governance_rejected_extra_reward: " + reason,
        })

    # Sort for determinism.
    approved.sort(key=lambda x: (x["request_id"], x["validation_id"]))
    rejected.sort(
        key=lambda x: (x["request_id"], x["validation_id"], x["reason"]),
    )

    total_approved = sum(
        i["approved_pending_reward_stocks"] for i in approved
    )
    approved_count = len(approved)
    rejected_count = len(rejected)

    batch_id = "gov-" + _sha16(canonical_dumps({
        "reviewer_id": reviewer_id, "policy": policy,
        "pinned_time": pinned_time,
        "approved": [
            {k: i[k] for k in sorted(i)} for i in approved
        ],
        "rejected": [
            {k: i[k] for k in sorted(i)} for i in rejected
        ],
    }))

    batch = {
        "schema": SCHEMA_BATCH,
        "batch_id": batch_id,
        "mode": "local-dry-run",
        "reviewer_id": reviewer_id,
        "policy": policy,
        "created_at": pinned_time,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "total_approved_reward_stocks": int(total_approved),
        "approved_items": approved,
        "rejected_items": rejected,
        "safety_status": {
            "no_wallet_access":                 True,
            "no_private_keys":                  True,
            "no_automatic_payout":              True,
            "no_broadcast":                     True,
            "no_onchain_registration":          True,
            "governance_review_only":           True,
            "requires_separate_payment_sprint": True,
        },
    }

    batch_path = (
        out_dir / f"TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_{batch_id}.json"
    )
    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_GOVERNANCE_SUMMARY.md"
    )
    batch_path.write_text(canonical_dumps(batch), encoding="utf-8")
    summary_path.write_text(
        _render_summary_md(batch), encoding="utf-8",
    )

    # Record lessons for the rejection reasons.
    if error_memory_ledger is not None:
        em_mod = _load(
            "ucg_error_mem", _SCRIPTS_DIR / "trinity_error_memory.py",
        )
        for item in rejected:
            reason = item["reason"]
            short = reason.split(":")[0] if ":" in reason else reason
            cause = "overclaim_risk"
            if "mismatch" in short:
                cause = "overclaim_risk"
            elif "insufficient" in short:
                cause = "insufficient_evidence"
            elif "manual_review" in short:
                cause = "overclaim_risk"
            elif "missing_reward" in short:
                cause = "bad_input"
            elif "duplicate_reward" in short:
                cause = "duplicate_candidate"
            elif "extra_reward" in short:
                cause = "duplicate_candidate"
            elif "invalid_structure" in short:
                cause = "bad_input"
            em_mod.record_lesson(
                ledger_path=error_memory_ledger,
                vertical="useful_compute",
                task_inputs={
                    "request_id": item["request_id"],
                    "validation_id": item["validation_id"],
                    "governance_reason": short,
                },
                cause=cause,
                detail=reason,
                pinned_time=pinned_time,
            )

    return batch


def _render_summary_md(batch: Dict[str, Any]) -> str:
    lines = [
        "# TRINITY USEFUL COMPUTE — GOVERNANCE REVIEW SUMMARY",
        "",
        f"- schema: `{batch['schema']}`",
        f"- batch_id: `{batch['batch_id']}`",
        f"- mode: `{batch['mode']}`",
        f"- reviewer_id: `{batch['reviewer_id']}`",
        f"- policy: `{batch['policy']}`",
        f"- created_at: `{batch['created_at']}`",
        "",
        "## Counts",
        "",
        f"- approved: **{batch['approved_count']}**",
        f"- rejected: **{batch['rejected_count']}**",
        f"- total_approved_reward_stocks: "
        f"**{batch['total_approved_reward_stocks']}**",
        "",
        "## Approved items",
        "",
    ]
    if batch["approved_items"]:
        lines.append(
            "| request_id | validation_id | workers | reward |"
        )
        lines.append("|---|---|---|---|")
        for it in batch["approved_items"]:
            lines.append(
                f"| {it['request_id']} | {it['validation_id']} | "
                f"{it['unique_workers']} | "
                f"{it['approved_pending_reward_stocks']} |"
            )
    else:
        lines.append("_none_")
    lines.extend(["", "## Rejected items", ""])
    if batch["rejected_items"]:
        for it in batch["rejected_items"]:
            lines.append(
                f"- `{it['request_id']}` / `{it['validation_id']}` "
                f"— {it['reason']}"
            )
    else:
        lines.append("_none_")
    lines.extend([
        "",
        "## Safety",
        "",
        "- **THIS BATCH DOES NOT PAY.**",
        "- No wallet access, no private keys, no broadcast, no on-chain",
        "  registration.",
        "- A separate, governance-signed payment sprint is required",
        "  before any stocks move.",
        "- Approved items are inputs to that future sprint, not",
        "  authorisations to issue stocks today.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_governance_gate",
        description=(
            "Trinity Useful Compute governance gate v0.1. Builds a "
            "review-only batch of approved reward items from accepted "
            "replay validations + pending rewards. Never pays."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument("--validations-dir", required=True)
    p.add_argument("--rewards-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--reviewer-id", required=True)
    p.add_argument(
        "--policy", default="conservative", choices=["conservative"],
    )
    p.add_argument(
        "--pinned-time", default="2026-05-12T00:00:00+00:00",
    )
    p.add_argument(
        "--error-memory-ledger", default=None,
        help=(
            "Optional path to a Trinity error memory JSONL ledger. "
            "If supplied, rejection reasons are recorded as lessons."
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
            "[useful_compute_governance_gate] only local-dry-run "
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
                f"[useful_compute_governance_gate] flag {flag_name} "
                "is rejected in v0.1",
                file=sys.stderr,
            )
            return 2
    if args.wallet is not None:
        print(
            "[useful_compute_governance_gate] --wallet is rejected "
            "in v0.1; this gate NEVER touches wallets or keys",
            file=sys.stderr,
        )
        return 2

    batch = run_governance_gate(
        validations_dir=Path(args.validations_dir),
        rewards_dir=Path(args.rewards_dir),
        out_dir=Path(args.out_dir),
        reviewer_id=args.reviewer_id,
        policy=args.policy,
        pinned_time=args.pinned_time,
        error_memory_ledger=(
            Path(args.error_memory_ledger)
            if args.error_memory_ledger else None
        ),
    )

    print(
        f"[useful_compute_governance_gate] batch_id={batch['batch_id']}"
    )
    print(
        f"[useful_compute_governance_gate] approved="
        f"{batch['approved_count']} rejected={batch['rejected_count']}"
    )
    print(
        f"[useful_compute_governance_gate] "
        f"total_approved_reward_stocks="
        f"{batch['total_approved_reward_stocks']}"
    )
    print(
        f"[useful_compute_governance_gate] dry_run=True, no payment "
        f"issued; requires_separate_payment_sprint=True"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
