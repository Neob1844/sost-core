#!/usr/bin/env python3
"""Trinity / Useful Compute — Payment Proposal v0.1.

Converts a Sprint 5.14 reward budget plan into a deterministic,
review-only payment proposal that lists payout_address, amount and
reason per item. Does NOT sign, NOT broadcast, NOT touch a wallet.

Resolution
----------
Each budget allocation_item references workers by ``worker_result_id``.
To pay a worker we need their ``payout_address``. Two artefacts
bridge the gap:

1. The worker address map
   (``trinity-worker-address-map/v0.1``) maps
   ``worker_id_hash`` -> ``payout_address``.

2. Pending reward files
   (``TRINITY_USEFUL_COMPUTE_PENDING_REWARD_<rid>_<wrid>.json``,
   schema v0.3) carry ``worker_id`` per submission. We compute
   ``worker_id_hash = sha16(worker_id)`` on the fly and look the
   address up.

When either link is missing, the worker's share lands in
``unresolved_items`` (not ``rejected_items``) — the operator can fix
the address map and rerun in v0.1.

Hard invariants
---------------
- v0.1 only accepts ``--mode local-dry-run``.
- The proposal NEVER signs, broadcasts, or touches a wallet.
- ``safety_status`` carries seven const-true flags including
  ``proposal_only``, ``requires_manual_signing``,
  ``requires_separate_broadcast``.
- Only the budget's ``primary_workers_share_stocks`` (70% of the
  allocated total) lands in payable_items. The replay and governance
  reserves remain held back for future sprints.
- ``proposal_id`` is sha16 of canonical(pinned_time +
  source_budget_id + payable_items + unresolved_items +
  deferred_items + rejected_items). Two runs on the same inputs
  produce byte-identical proposals.
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


SCHEMA_PROPOSAL    = "trinity-useful-compute-payment-proposal/v0.1"
SCHEMA_BUDGET      = "trinity-useful-compute-reward-budget/v0.1"
SCHEMA_REWARD      = "trinity-useful-compute-pending-reward/v0.3"
SCHEMA_ADDRESS_MAP = "trinity-worker-address-map/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent

_ADDRESS_RE = re.compile(r"^sost1[023456789acdefghjklmnpqrstuvwxyz]{20,80}$")
_WORKER_HASH_RE = re.compile(r"^[0-9a-f]{16}$")
_WRID_RE = re.compile(r"^[0-9a-f]{16}$")
_RID_RE  = re.compile(r"^uc-[0-9a-f]{16,64}$")
_REWARD_NAME_RE = re.compile(
    r"^TRINITY_USEFUL_COMPUTE_PENDING_REWARD_"
    r"(uc-[0-9a-f]{16,64})_([0-9a-f]{16})\.json$"
)

STOCKS_PER_SOST = 100_000_000


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


def _load_budget(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("budget plan must be a JSON object")
    if obj.get("schema") != SCHEMA_BUDGET:
        raise ValueError(
            f"budget plan wrong schema: {obj.get('schema')!r}; "
            f"expected {SCHEMA_BUDGET!r}"
        )
    bid = obj.get("budget_id", "")
    if not (isinstance(bid, str) and re.match(r"^bud-[0-9a-f]{16}$", bid)):
        raise ValueError(f"budget_id wrong format: {bid!r}")
    return obj


def _load_address_map(path: Path) -> Dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("address map must be a JSON object")
    if obj.get("schema") != SCHEMA_ADDRESS_MAP:
        raise ValueError(
            f"address map wrong schema: {obj.get('schema')!r}; "
            f"expected {SCHEMA_ADDRESS_MAP!r}"
        )
    workers = obj.get("workers")
    if not isinstance(workers, list):
        raise ValueError("address map workers must be a list")
    # Build by_hash + by_address indices, also validate uniqueness +
    # well-formed sost1 addresses.
    by_hash: Dict[str, str] = {}
    by_addr: Dict[str, str] = {}
    for i, w in enumerate(workers):
        if not isinstance(w, dict):
            raise ValueError(f"workers[{i}] not an object")
        wh = w.get("worker_id_hash", "")
        if not (isinstance(wh, str) and _WORKER_HASH_RE.match(wh)):
            raise ValueError(f"workers[{i}].worker_id_hash invalid: {wh!r}")
        addr = w.get("payout_address", "")
        if not (isinstance(addr, str) and _ADDRESS_RE.match(addr)):
            raise ValueError(
                f"workers[{i}].payout_address invalid: {addr!r}"
            )
        if wh in by_hash:
            raise ValueError(f"duplicate worker_id_hash: {wh}")
        if addr in by_addr:
            raise ValueError(f"duplicate payout_address: {addr}")
        by_hash[wh] = addr
        by_addr[addr] = wh
    return {"by_hash": by_hash, "by_address": by_addr}


def _scan_rewards_dir(
    rewards_dir: Optional[Path],
) -> Dict[Tuple[str, str], str]:
    """Build a (request_id, worker_result_id) -> worker_id_hash
    lookup from pending reward files. Skips files that are not v0.3
    or have inconsistent ids."""
    out: Dict[Tuple[str, str], str] = {}
    if rewards_dir is None or not rewards_dir.exists():
        return out
    for p in sorted(rewards_dir.glob(
        "TRINITY_USEFUL_COMPUTE_PENDING_REWARD_*.json"
    )):
        m = _REWARD_NAME_RE.match(p.name)
        if m is None:
            continue
        rid_from_name = m.group(1)
        wrid_from_name = m.group(2)
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("schema") != SCHEMA_REWARD:
            continue
        if obj.get("request_id") != rid_from_name:
            continue
        # Prefer body's worker_result_id, fall back to filename.
        wrid_body = obj.get("worker_result_id", wrid_from_name)
        if not (isinstance(wrid_body, str)
                and _WRID_RE.match(wrid_body)):
            continue
        wid = obj.get("worker_id", "")
        if not (isinstance(wid, str) and 1 <= len(wid) <= 128):
            continue
        out[(rid_from_name, wrid_body)] = _sha16(wid)
    return out


def _split_per_worker_payout(
    allocation_item: Dict[str, Any],
) -> Tuple[int, int]:
    """Return (primary_workers_share_stocks, per_worker_payout_stocks).
    The 20% replay reserve and 10% governance reserve stay held back
    and do NOT enter the proposal."""
    primary = int(allocation_item.get("primary_workers_share_stocks", 0))
    wrids = allocation_item.get("worker_result_ids", [])
    n = max(1, len(wrids))
    per_worker = primary // n
    return primary, per_worker


def run_payment_proposal(
    *,
    budget_path: Path,
    address_map_path: Path,
    out_dir: Path,
    pinned_time: str,
    rewards_dir: Optional[Path] = None,
    proposal_id_override: Optional[str] = None,
) -> Dict[str, Any]:
    budget = _load_budget(budget_path)
    addr_index = _load_address_map(address_map_path)
    wrid_to_hash = _scan_rewards_dir(rewards_dir)

    budget_id = budget["budget_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    payable: List[Dict[str, Any]] = []
    unresolved: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    governance_batches: List[str] = []

    for item in budget.get("allocation_items", []):
        status = item.get("allocation_status")
        rid = item.get("request_id", "")
        batch_id = item.get("governance_batch_id", "")
        if batch_id and batch_id not in governance_batches:
            governance_batches.append(batch_id)

        if status == "rejected":
            rejected.append({
                "request_id": rid,
                "source_budget_id": budget_id,
                "reason": (
                    "budget_rejected: "
                    + str(item.get("cap_reason", ""))
                ),
            })
            continue

        if status == "deferred":
            deferred.append({
                "request_id": rid,
                "deferred_stocks": int(item.get("deferred_stocks", 0)),
                "source_budget_id": budget_id,
                "reason": (
                    "budget_deferred: "
                    + str(item.get("cap_reason", ""))
                ),
            })
            continue

        # Capped or approved: the allocated_stocks is the figure we
        # work with. Defer the leftover.
        deferred_stocks = int(item.get("deferred_stocks", 0))
        if deferred_stocks > 0:
            deferred.append({
                "request_id": rid,
                "deferred_stocks": deferred_stocks,
                "source_budget_id": budget_id,
                "reason": (
                    "budget_partial_defer: "
                    + str(item.get("cap_reason", ""))
                ),
            })

        primary_share, per_worker = _split_per_worker_payout(item)
        if primary_share == 0 or per_worker == 0:
            # No primary share to distribute (rounded to zero on a
            # very tight cap). Treat as unresolved to keep audit.
            for wrid in item.get("worker_result_ids", []):
                unresolved.append({
                    "request_id": rid,
                    "worker_result_id": wrid,
                    "allocated_stocks": 0,
                    "missing_lookup": (
                        "primary_share=0 (caps zeroed per-worker payout)"
                    ),
                    "reason": "no_per_worker_share_after_caps",
                })
            continue

        # Resolve every worker_result_id to a payout address.
        by_hash = addr_index["by_hash"]
        # Group workers by destination address so we emit one
        # payable_item per (request_id, payout_address).
        per_address_workers: Dict[str, List[str]] = {}
        for wrid in sorted(item.get("worker_result_ids", [])):
            wh = wrid_to_hash.get((rid, wrid))
            if wh is None:
                unresolved.append({
                    "request_id": rid,
                    "worker_result_id": wrid,
                    "allocated_stocks": int(per_worker),
                    "missing_lookup": (
                        "worker_id_hash unknown; rewards-dir entry "
                        "missing or invalid"
                    ),
                    "reason": "no_worker_id_hash_for_wrid",
                })
                continue
            addr = by_hash.get(wh)
            if addr is None:
                unresolved.append({
                    "request_id": rid,
                    "worker_result_id": wrid,
                    "allocated_stocks": int(per_worker),
                    "missing_lookup": (
                        f"worker_id_hash:{wh} not in address map"
                    ),
                    "reason": "no_payout_address_for_worker_id_hash",
                })
                continue
            per_address_workers.setdefault(addr, []).append(wrid)

        for addr in sorted(per_address_workers.keys()):
            wrids_for_addr = sorted(per_address_workers[addr])
            allocated_for_addr = per_worker * len(wrids_for_addr)
            payable.append({
                "request_id": rid,
                "worker_result_ids": wrids_for_addr,
                "payout_address": addr,
                "allocated_stocks": int(allocated_for_addr),
                "allocated_sost": (
                    int(allocated_for_addr) / STOCKS_PER_SOST
                ),
                "source_budget_id": budget_id,
                "source_governance_batch_id": batch_id,
                "reason": (
                    f"primary_workers_share / "
                    f"{len(wrids_for_addr)} worker(s) -> {addr}"
                ),
            })

    payable.sort(
        key=lambda x: (x["request_id"], x["payout_address"]),
    )
    unresolved.sort(
        key=lambda x: (x["request_id"], x["worker_result_id"]),
    )
    deferred.sort(
        key=lambda x: x["request_id"],
    )
    rejected.sort(
        key=lambda x: x["request_id"],
    )

    total_payable = sum(p["allocated_stocks"] for p in payable)
    total_unresolved = sum(u["allocated_stocks"] for u in unresolved)
    total_deferred = sum(d["deferred_stocks"] for d in deferred)

    proposal_id = (
        proposal_id_override
        or "prop-" + _sha16(canonical_dumps({
            "pinned_time": pinned_time,
            "source_budget_id": budget_id,
            "payable": payable,
            "unresolved": unresolved,
            "deferred": deferred,
            "rejected": rejected,
        }))
    )

    capsule_summary = {
        "template": "useful_compute_reward_batch_v1",
        "text": (
            f"Trinity Useful Compute reward proposal {proposal_id}; "
            f"payable={total_payable} stocks; "
            f"deferred={total_deferred} stocks; "
            f"unresolved={total_unresolved} stocks; "
            f"budget={budget_id}"
        ),
        "referenced_files": {
            "budget_id": budget_id,
            "governance_batch_ids": sorted(set(governance_batches)),
            "validation_ids": [],
        },
    }

    proposal = {
        "schema": SCHEMA_PROPOSAL,
        "proposal_id": proposal_id,
        "mode": "local-dry-run",
        "pinned_time": pinned_time,
        "source_budget_id": budget_id,
        "total_payable_stocks": int(total_payable),
        "total_deferred_stocks": int(total_deferred),
        "total_unresolved_stocks": int(total_unresolved),
        "payable_items": payable,
        "unresolved_items": unresolved,
        "deferred_items": deferred,
        "rejected_items": rejected,
        "capsule_summary": capsule_summary,
        "safety_status": {
            "no_private_keys":             True,
            "no_wallet_access":            True,
            "no_signature":                True,
            "no_broadcast":                True,
            "proposal_only":               True,
            "requires_manual_signing":     True,
            "requires_separate_broadcast": True,
        },
    }

    proposal_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_PAYMENT_PROPOSAL_{proposal_id}.json"
    )
    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_PAYMENT_PROPOSAL_SUMMARY.md"
    )
    proposal_path.write_text(
        canonical_dumps(proposal), encoding="utf-8",
    )
    summary_path.write_text(
        _render_summary_md(proposal), encoding="utf-8",
    )
    return proposal


def _render_summary_md(proposal: Dict[str, Any]) -> str:
    lines = [
        "# TRINITY USEFUL COMPUTE — PAYMENT PROPOSAL (review-only)",
        "",
        f"- schema: `{proposal['schema']}`",
        f"- proposal_id: `{proposal['proposal_id']}`",
        f"- mode: `{proposal['mode']}`",
        f"- pinned_time: `{proposal['pinned_time']}`",
        f"- source_budget_id: `{proposal['source_budget_id']}`",
        "",
        "## Totals",
        "",
        f"- payable_stocks:    {proposal['total_payable_stocks']:,}",
        f"- deferred_stocks:   {proposal['total_deferred_stocks']:,}",
        f"- unresolved_stocks: {proposal['total_unresolved_stocks']:,}",
        "",
        "## Payable",
        "",
    ]
    if proposal["payable_items"]:
        lines.append(
            "| request_id | payout_address | workers | stocks | SOST |"
        )
        lines.append("|---|---|---|---|---|")
        for p in proposal["payable_items"]:
            lines.append(
                f"| {p['request_id']} | {p['payout_address']} | "
                f"{len(p['worker_result_ids'])} | "
                f"{p['allocated_stocks']:,} | {p['allocated_sost']} |"
            )
    else:
        lines.append("_none_")

    lines.extend(["", "## Unresolved", ""])
    if proposal["unresolved_items"]:
        for u in proposal["unresolved_items"]:
            lines.append(
                f"- `{u['request_id']}` wrid=`{u['worker_result_id']}` "
                f"({u['allocated_stocks']:,} stocks) — "
                f"{u['missing_lookup']}"
            )
    else:
        lines.append("_none_")

    lines.extend(["", "## Deferred", ""])
    if proposal["deferred_items"]:
        for d in proposal["deferred_items"]:
            lines.append(
                f"- `{d['request_id']}` deferred="
                f"{d['deferred_stocks']:,} stocks — {d['reason']}"
            )
    else:
        lines.append("_none_")

    lines.extend(["", "## Capsule summary (NOT published yet)", ""])
    lines.append(f"- template: `{proposal['capsule_summary']['template']}`")
    lines.append(f"- text: {proposal['capsule_summary']['text']}")
    lines.append(
        "- budget: `"
        + proposal["capsule_summary"]["referenced_files"]["budget_id"]
        + "`"
    )
    gbatches = proposal["capsule_summary"]["referenced_files"][
        "governance_batch_ids"
    ]
    if gbatches:
        for g in gbatches:
            lines.append(f"  - gov batch: `{g}`")

    lines.extend([
        "",
        "## Safety",
        "",
        "- **THIS IS NOT A TRANSACTION.**",
        "- No payment has been signed or broadcast.",
        "- No wallet was touched. No private key was touched.",
        "- Manual signing is required in a later sprint.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_payment_proposal",
        description=(
            "Trinity Useful Compute payment proposal v0.1. Reviews "
            "and bundles budget allocations into a payout-ready "
            "proposal. NEVER signs, NEVER touches a wallet, NEVER "
            "broadcasts."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument("--budget-plan", required=True)
    p.add_argument("--worker-address-map", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--proposal-id", default=None)
    p.add_argument(
        "--pinned-time", default="2026-05-12T00:00:00+00:00",
    )
    p.add_argument(
        "--rewards-dir", default=None,
        help=(
            "Optional directory of pending reward JSON files. When "
            "supplied, the proposal can map worker_result_id -> "
            "worker_id_hash on the fly. Without it, every wrid "
            "lands in unresolved_items."
        ),
    )

    # Hard-rejection guards.
    p.add_argument("--broadcast", action="store_true", help="REJECTED")
    p.add_argument("--payout",    action="store_true", help="REJECTED")
    p.add_argument("--send",      action="store_true", help="REJECTED")
    p.add_argument("--wallet",    type=str, default=None, help="REJECTED")
    p.add_argument("--network",   action="store_true", help="REJECTED")
    p.add_argument("--sign",      action="store_true", help="REJECTED")
    args = p.parse_args(argv)

    if args.mode != "local-dry-run":
        print(
            "[useful_compute_payment_proposal] only local-dry-run "
            "is supported in v0.1",
            file=sys.stderr,
        )
        return 2
    for flag_value, flag_name in (
        (args.broadcast, "--broadcast"),
        (args.payout,    "--payout"),
        (args.send,      "--send"),
        (args.network,   "--network"),
        (args.sign,      "--sign"),
    ):
        if flag_value:
            print(
                f"[useful_compute_payment_proposal] flag "
                f"{flag_name} is rejected in v0.1",
                file=sys.stderr,
            )
            return 2
    if args.wallet is not None:
        print(
            "[useful_compute_payment_proposal] --wallet is rejected "
            "in v0.1",
            file=sys.stderr,
        )
        return 2

    try:
        proposal = run_payment_proposal(
            budget_path=Path(args.budget_plan),
            address_map_path=Path(args.worker_address_map),
            out_dir=Path(args.out_dir),
            pinned_time=args.pinned_time,
            rewards_dir=Path(args.rewards_dir) if args.rewards_dir
                else None,
            proposal_id_override=args.proposal_id,
        )
    except ValueError as exc:
        print(
            f"[useful_compute_payment_proposal] error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        f"[useful_compute_payment_proposal] proposal_id="
        f"{proposal['proposal_id']}"
    )
    print(
        f"[useful_compute_payment_proposal] payable="
        f"{proposal['total_payable_stocks']:,} stocks; "
        f"deferred={proposal['total_deferred_stocks']:,}; "
        f"unresolved={proposal['total_unresolved_stocks']:,}"
    )
    print(
        f"[useful_compute_payment_proposal] payable_items="
        f"{len(proposal['payable_items'])} / "
        f"unresolved_items={len(proposal['unresolved_items'])}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
