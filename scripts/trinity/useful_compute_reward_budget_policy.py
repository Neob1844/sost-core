#!/usr/bin/env python3
"""Trinity / Useful Compute — Reward Budget Policy v0.1.

Reads a directory of governance-approved batches (Sprint 5.9) and
applies the v0.1 conservative budget policy on top. Emits a budget
plan that caps total stocks by pool, daily, epoch, job and worker
limits.

v0.1 is dry-run only:
- NEVER pays
- NEVER touches a wallet
- NEVER broadcasts
- NEVER registers on-chain
- Deferred stocks are NOT lost; the next budget cycle re-evaluates
  them.

Cap stack
---------
For each governance-approved item (request_id, matching workers,
approved_pending_reward_stocks per worker):

1. **Worker cap** — per-worker allocation ≤
   ``max_worker_reward_stocks``.
2. **Job cap** — total per request_id ≤ ``max_job_reward_stocks``;
   when hit, per-worker allocation is scaled down evenly.
3. **Epoch cap** — running total over the whole budget run ≤
   ``effective_epoch_budget_stocks``; excess is deferred.
4. **Daily cap** — running total ≤
   ``effective_daily_budget_stocks``; excess is deferred.

Where:
- ``effective_daily_budget_stocks = min(pool * max_daily_fraction,
   fixed_daily_cap_stocks)``
- ``effective_epoch_budget_stocks = min(pool * max_epoch_fraction,
   fixed_epoch_cap_stocks)``

Of the allocated total for one item, the v0.1 split is:
- 70% primary_workers_share
- 20% replay_validator_reserve (held for cross-worker replay payouts
  in a future sprint)
- 10% governance_review_reserve (held for the human review step in
  the payment sprint)

Allocation statuses
-------------------
- ``approved_as_requested`` — no caps hit, full allocation
- ``capped_by_worker`` / ``capped_by_job`` — partial allocation,
  cap was the primary limit
- ``capped_by_daily`` / ``capped_by_epoch`` — partial or zero
  allocation; remainder is deferred to the next budget run
- ``deferred`` — zero allocation (multiple caps fully blocked it)
- ``rejected`` — input was structurally invalid

Determinism
-----------
``budget_id`` is sha16 of canonical(policy + pinned_time + epoch_id +
pool + sorted allocation items). Two runs on the same inputs produce
byte-identical plans.
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


SCHEMA_BUDGET = "trinity-useful-compute-reward-budget/v0.1"
SCHEMA_GOVERNANCE = "trinity-useful-compute-governance-batch/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent


# Conservative defaults — these are deliberately tight so the v0.1
# policy can be relaxed by governance later, never the other way
# round.
_DEFAULT_POLICY_CAPS: Dict[str, Any] = {
    "max_daily_fraction_of_pool":  0.0001,    # 0.01% / day
    "fixed_daily_cap_stocks":      100_000_000,        # 1 SOST
    "max_epoch_fraction_of_pool":  0.001,     # 0.1% / epoch
    "fixed_epoch_cap_stocks":      1_000_000_000,      # 10 SOST
    "max_job_reward_stocks":       5_000_000,          # 0.05 SOST
    "max_worker_reward_stocks":    2_000_000,          # 0.02 SOST
    "primary_worker_share":        0.70,
    "replay_validator_share":      0.20,
    "governance_review_reserve":   0.10,
}


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Load + structurally validate governance batches
# ---------------------------------------------------------------------------


def _governance_problem(obj: Any) -> Optional[str]:
    if not isinstance(obj, dict):
        return "not an object"
    if obj.get("schema") != SCHEMA_GOVERNANCE:
        return f"wrong schema: {obj.get('schema')!r}"
    if not isinstance(obj.get("batch_id"), str):
        return "missing batch_id"
    if not re.match(r"^gov-[0-9a-f]{16}$", obj.get("batch_id", "")):
        return f"bad batch_id: {obj.get('batch_id')!r}"
    if not isinstance(obj.get("approved_items"), list):
        return "approved_items must be a list"
    return None


def _approved_item_problem(item: Any) -> Optional[str]:
    if not isinstance(item, dict):
        return "approved_item not an object"
    rid = item.get("request_id", "")
    if not (isinstance(rid, str)
            and re.match(r"^uc-[0-9a-f]{16,64}$", rid)):
        return f"bad request_id: {rid!r}"
    stocks = item.get("approved_pending_reward_stocks")
    if not (isinstance(stocks, int) and stocks >= 0):
        return f"bad approved_pending_reward_stocks: {stocks!r}"
    matching = item.get("matching_result_ids")
    if not (isinstance(matching, list) and len(matching) >= 1
            and all(
                isinstance(w, str)
                and re.match(r"^[0-9a-f]{16}$", w) for w in matching
            )):
        return "bad matching_result_ids"
    return None


def _load_governance_batches(
    governance_dir: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """Return (valid_batches, structural_rejections)."""
    valid: List[Dict[str, Any]] = []
    rejections: List[Dict[str, str]] = []
    if not governance_dir.exists():
        return valid, rejections
    files = sorted(
        governance_dir.glob(
            "TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_*.json"
        )
    )
    for p in files:
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            rejections.append({
                "request_id": "uc-" + "0" * 16,
                "governance_batch_id": "gov-" + "0" * 16,
                "reason": f"file {p.name}: invalid JSON",
            })
            continue
        prob = _governance_problem(obj)
        if prob is not None:
            rejections.append({
                "request_id": "uc-" + "0" * 16,
                "governance_batch_id": obj.get("batch_id")
                    if isinstance(obj, dict) else "gov-" + "0" * 16,
                "reason": f"file {p.name}: {prob}",
            })
            continue
        valid.append(obj)
    return valid, rejections


# ---------------------------------------------------------------------------
# Core allocation
# ---------------------------------------------------------------------------


def _allocate_one(
    batch_id: str,
    item: Dict[str, Any],
    caps: Dict[str, Any],
    daily_used: int,
    daily_budget: int,
    epoch_used: int,
    epoch_budget: int,
) -> Tuple[Dict[str, Any], int, int]:
    """Allocate one governance approved item under the cap stack.
    Returns (allocation_dict, new_daily_used, new_epoch_used)."""
    rid = item["request_id"]
    matching = sorted(item.get("matching_result_ids", []))
    n_workers = max(1, len(matching))
    per_worker_requested = int(item.get("approved_pending_reward_stocks", 0))
    requested = per_worker_requested * n_workers

    reasons: List[str] = []
    allocated_per_worker = per_worker_requested
    allocation_status = "approved_as_requested"

    # 1) Worker cap.
    if allocated_per_worker > int(caps["max_worker_reward_stocks"]):
        allocated_per_worker = int(caps["max_worker_reward_stocks"])
        reasons.append("capped_by_worker")
        allocation_status = "capped_by_worker"

    allocated_total = allocated_per_worker * n_workers

    # 2) Job cap.
    if allocated_total > int(caps["max_job_reward_stocks"]):
        allocated_per_worker = (
            int(caps["max_job_reward_stocks"]) // n_workers
        )
        allocated_total = allocated_per_worker * n_workers
        reasons.append("capped_by_job")
        allocation_status = "capped_by_job"

    # 3) Epoch cap.
    epoch_remaining = max(0, epoch_budget - epoch_used)
    if allocated_total > epoch_remaining:
        allowed = epoch_remaining
        if allowed < n_workers:
            allocated_per_worker = 0
            allocated_total = 0
        else:
            allocated_per_worker = allowed // n_workers
            allocated_total = allocated_per_worker * n_workers
        reasons.append("capped_by_epoch")
        allocation_status = (
            "deferred" if allocated_total == 0 else "capped_by_epoch"
        )

    # 4) Daily cap.
    daily_remaining = max(0, daily_budget - daily_used)
    if allocated_total > daily_remaining:
        allowed = daily_remaining
        if allowed < n_workers:
            allocated_per_worker = 0
            allocated_total = 0
        else:
            allocated_per_worker = allowed // n_workers
            allocated_total = allocated_per_worker * n_workers
        reasons.append("capped_by_daily")
        allocation_status = (
            "deferred" if allocated_total == 0 else "capped_by_daily"
        )

    deferred = max(0, requested - allocated_total)

    if not reasons:
        cap_reason = "none"
    else:
        cap_reason = ",".join(reasons)

    # v0.1 split: 70 / 20 / 10 of the allocated total. Integer math;
    # the remainder (if any) lands in the governance reserve so the
    # caller never sees a fractional underflow.
    primary = (
        allocated_total * int(round(caps["primary_worker_share"] * 1000))
    ) // 1000
    replay = (
        allocated_total * int(round(caps["replay_validator_share"] * 1000))
    ) // 1000
    governance_reserve = max(0, allocated_total - primary - replay)

    return ({
        "request_id": rid,
        "governance_batch_id": batch_id,
        "worker_result_ids": matching,
        "requested_stocks": int(requested),
        "allocated_stocks": int(allocated_total),
        "deferred_stocks": int(deferred),
        "primary_workers_share_stocks": int(primary),
        "replay_validator_reserve_stocks": int(replay),
        "governance_review_reserve_stocks": int(governance_reserve),
        "cap_reason": cap_reason,
        "allocation_status": allocation_status,
    }, daily_used + allocated_total, epoch_used + allocated_total)


def run_budget_policy(
    *,
    pool_balance_stocks: int,
    governance_dir: Path,
    out_dir: Path,
    pinned_time: str,
    epoch_id: str,
    policy: str = "conservative",
    policy_caps: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if policy != "conservative":
        raise ValueError(f"unsupported policy: {policy!r}")
    if not (isinstance(pool_balance_stocks, int)
            and pool_balance_stocks >= 1):
        raise ValueError(
            f"pool_balance_stocks must be a positive int, got "
            f"{pool_balance_stocks!r}"
        )
    if not (isinstance(epoch_id, str) and 1 <= len(epoch_id) <= 64):
        raise ValueError("epoch_id must be 1..64 chars")

    caps = dict(_DEFAULT_POLICY_CAPS)
    if policy_caps:
        for k, v in policy_caps.items():
            if k not in caps:
                raise ValueError(f"unknown policy cap: {k!r}")
            caps[k] = v

    # Share sanity (must be on [0, 1] and sum to 1.0 within rounding).
    shares = (
        caps["primary_worker_share"]
        + caps["replay_validator_share"]
        + caps["governance_review_reserve"]
    )
    if abs(shares - 1.0) > 1e-6:
        raise ValueError(
            f"shares must sum to 1.0, got {shares}"
        )

    out_dir.mkdir(parents=True, exist_ok=True)

    # Compute effective budgets.
    daily_budget = int(min(
        pool_balance_stocks * float(caps["max_daily_fraction_of_pool"]),
        int(caps["fixed_daily_cap_stocks"]),
    ))
    epoch_budget = int(min(
        pool_balance_stocks * float(caps["max_epoch_fraction_of_pool"]),
        int(caps["fixed_epoch_cap_stocks"]),
    ))

    valid_batches, rejections = _load_governance_batches(governance_dir)

    # Flatten approved items with a deterministic sort key.
    candidates: List[Tuple[str, Dict[str, Any]]] = []
    for batch in valid_batches:
        bid = batch["batch_id"]
        for item in batch.get("approved_items", []):
            prob = _approved_item_problem(item)
            if prob is not None:
                rejections.append({
                    "request_id": item.get("request_id", "uc-" + "0" * 16)
                        if isinstance(item, dict)
                        else "uc-" + "0" * 16,
                    "governance_batch_id": bid,
                    "reason": (
                        "governance_rejected_invalid_structure: "
                        + prob
                    ),
                })
                continue
            candidates.append((bid, item))
    # Sort by request_id then batch_id for determinism.
    candidates.sort(
        key=lambda kv: (kv[1]["request_id"], kv[0]),
    )

    allocations: List[Dict[str, Any]] = []
    daily_used = 0
    epoch_used = 0
    for bid, item in candidates:
        alloc, daily_used, epoch_used = _allocate_one(
            batch_id=bid, item=item, caps=caps,
            daily_used=daily_used, daily_budget=daily_budget,
            epoch_used=epoch_used, epoch_budget=epoch_budget,
        )
        allocations.append(alloc)

    # Append structural rejections as zero-allocated entries so the
    # report has one row per known input.
    for rej in rejections:
        allocations.append({
            "request_id": rej["request_id"],
            "governance_batch_id": rej["governance_batch_id"],
            "worker_result_ids": [],
            "requested_stocks": 0,
            "allocated_stocks": 0,
            "deferred_stocks": 0,
            "primary_workers_share_stocks": 0,
            "replay_validator_reserve_stocks": 0,
            "governance_review_reserve_stocks": 0,
            "cap_reason": rej["reason"],
            "allocation_status": "rejected",
        })

    allocations.sort(
        key=lambda a: (a["request_id"], a["governance_batch_id"]),
    )

    total_requested = sum(a["requested_stocks"] for a in allocations)
    total_allocated = sum(a["allocated_stocks"] for a in allocations)
    total_deferred  = sum(a["deferred_stocks"] for a in allocations)

    budget_id = "bud-" + _sha16(canonical_dumps({
        "policy": policy,
        "pinned_time": pinned_time,
        "epoch_id": epoch_id,
        "pool": int(pool_balance_stocks),
        "caps": caps,
        "allocations": allocations,
    }))

    plan = {
        "schema": SCHEMA_BUDGET,
        "budget_id": budget_id,
        "mode": "local-dry-run",
        "policy": policy,
        "pinned_time": pinned_time,
        "epoch_id": epoch_id,
        "pool_balance_stocks": int(pool_balance_stocks),
        "effective_daily_budget_stocks": int(daily_budget),
        "effective_epoch_budget_stocks": int(epoch_budget),
        "policy_caps": {
            k: caps[k] for k in sorted(caps.keys())
        },
        "total_requested_stocks": int(total_requested),
        "total_allocated_stocks": int(total_allocated),
        "total_deferred_stocks":  int(total_deferred),
        "allocation_items": allocations,
        "safety_status": {
            "no_wallet_access":                 True,
            "no_private_keys":                  True,
            "no_automatic_payout":              True,
            "no_broadcast":                     True,
            "budget_only":                      True,
            "requires_separate_payment_sprint": True,
        },
    }

    plan_path = (
        out_dir / f"TRINITY_USEFUL_COMPUTE_REWARD_BUDGET_{budget_id}.json"
    )
    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_REWARD_BUDGET_SUMMARY.md"
    )
    plan_path.write_text(canonical_dumps(plan), encoding="utf-8")
    summary_path.write_text(_render_summary_md(plan), encoding="utf-8")

    return plan


def _render_summary_md(plan: Dict[str, Any]) -> str:
    lines = [
        "# TRINITY USEFUL COMPUTE — REWARD BUDGET PLAN",
        "",
        f"- schema: `{plan['schema']}`",
        f"- budget_id: `{plan['budget_id']}`",
        f"- mode: `{plan['mode']}`",
        f"- policy: `{plan['policy']}`",
        f"- pinned_time: `{plan['pinned_time']}`",
        f"- epoch_id: `{plan['epoch_id']}`",
        "",
        "## Pool + effective budgets",
        "",
        f"- pool_balance_stocks: {plan['pool_balance_stocks']:,}",
        f"- effective_daily_budget_stocks: "
        f"**{plan['effective_daily_budget_stocks']:,}**",
        f"- effective_epoch_budget_stocks: "
        f"**{plan['effective_epoch_budget_stocks']:,}**",
        "",
        "## Policy caps",
        "",
    ]
    for k in sorted(plan["policy_caps"].keys()):
        lines.append(f"- `{k}` = {plan['policy_caps'][k]}")
    lines.extend([
        "",
        "## Totals",
        "",
        f"- requested:  {plan['total_requested_stocks']:,}",
        f"- allocated:  {plan['total_allocated_stocks']:,}",
        f"- deferred:   {plan['total_deferred_stocks']:,}",
        "",
        "## Allocation items",
        "",
    ])
    if plan["allocation_items"]:
        lines.append(
            "| request_id | batch_id | workers | requested | allocated | "
            "deferred | status | cap_reason |"
        )
        lines.append(
            "|---|---|---|---|---|---|---|---|"
        )
        for a in plan["allocation_items"]:
            lines.append(
                f"| {a['request_id']} | {a['governance_batch_id']} | "
                f"{len(a['worker_result_ids'])} | "
                f"{a['requested_stocks']:,} | "
                f"{a['allocated_stocks']:,} | "
                f"{a['deferred_stocks']:,} | "
                f"{a['allocation_status']} | {a['cap_reason']} |"
            )
    else:
        lines.append("_none_")
    lines.extend([
        "",
        "## Safety",
        "",
        "- **THIS PLAN DOES NOT PAY.**",
        "- Budget allocation is NOT payment.",
        "- A separate, governance-signed payment sprint is required",
        "  before any stocks move.",
        "- Deferred stocks are NOT lost; the next budget cycle "
        "  re-evaluates them.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_reward_budget_policy",
        description=(
            "Trinity Useful Compute reward budget policy v0.1. "
            "Caps governance-approved totals by pool / daily / "
            "epoch / job / worker before any payment sprint. "
            "NEVER pays."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument(
        "--pool-balance-stocks", type=int, required=True,
        help="Current pool balance in stocks (1 SOST = 100,000,000 stocks)",
    )
    p.add_argument("--policy", default="conservative",
                   choices=["conservative"])
    p.add_argument("--governance-dir", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument(
        "--pinned-time", default="2026-05-12T00:00:00+00:00",
    )
    p.add_argument(
        "--epoch-id", default="epoch-default",
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
            "[useful_compute_reward_budget_policy] only local-dry-run "
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
                f"[useful_compute_reward_budget_policy] flag "
                f"{flag_name} is rejected in v0.1",
                file=sys.stderr,
            )
            return 2
    if args.wallet is not None:
        print(
            "[useful_compute_reward_budget_policy] --wallet is "
            "rejected in v0.1",
            file=sys.stderr,
        )
        return 2

    try:
        plan = run_budget_policy(
            pool_balance_stocks=args.pool_balance_stocks,
            governance_dir=Path(args.governance_dir),
            out_dir=Path(args.out_dir),
            pinned_time=args.pinned_time,
            epoch_id=args.epoch_id,
            policy=args.policy,
        )
    except ValueError as exc:
        print(
            f"[useful_compute_reward_budget_policy] budget error: "
            f"{exc}",
            file=sys.stderr,
        )
        return 2

    print(
        f"[useful_compute_reward_budget_policy] budget_id="
        f"{plan['budget_id']}"
    )
    print(
        f"[useful_compute_reward_budget_policy] pool="
        f"{plan['pool_balance_stocks']:,} "
        f"daily_budget={plan['effective_daily_budget_stocks']:,} "
        f"epoch_budget={plan['effective_epoch_budget_stocks']:,}"
    )
    print(
        f"[useful_compute_reward_budget_policy] requested="
        f"{plan['total_requested_stocks']:,} "
        f"allocated={plan['total_allocated_stocks']:,} "
        f"deferred={plan['total_deferred_stocks']:,}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
