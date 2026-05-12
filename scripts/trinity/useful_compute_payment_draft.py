#!/usr/bin/env python3
"""Trinity / Useful Compute — Signed Payment Draft v0.1.

Converts a Sprint 5.15 payment proposal into a reviewable transaction
draft. v0.1 is the first Trinity layer that *can* touch a wallet
path, but only behind two explicit gates:

1. Default mode is ``--unsigned-only``. Wallet is NEVER referenced.
2. Optional ``--dry-sign`` requires both ``--wallet`` AND a verbatim
   confirmation token. Even with both, v0.1 does NOT actually sign
   anything — it verifies that the wallet file exists and writes a
   placeholder ``signed_tx_hex`` string so the audit chain is honest.
   Real signing lands in a separate, governance-controlled sprint.

Hard invariants (enforced both at CLI and in the schema):

- NEVER broadcasts. The schema flag ``no_broadcast`` is locked
  ``const: true``.
- NEVER calls ``sendrawtransaction`` or any send-style RPC.
- NEVER exports a private key. ``private_keys_exported`` is locked
  ``const: false``.
- ``requires_separate_broadcast`` is locked ``const: true``.
- ``human_review_required`` is locked ``const: true``.
- Rejects the CLI flags ``--broadcast``, ``--send``,
  ``--payout-now``, ``--auto-pay``, ``--sendrawtransaction`` with
  rc=2.
- Tokens are mode-specific so they cannot be reused across modes.

Mode tokens (exact match required, no substring matching):

- unsigned-only mode:
    I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST
- dry-sign mode:
    I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST

Determinism
-----------
``draft_id`` is the sha16 of canonical(mode + source_proposal_id +
pinned_time + outputs + warnings + max_total_stocks). Two runs with
the same inputs produce byte-identical drafts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_DRAFT = "trinity-useful-compute-payment-draft/v0.1"
SCHEMA_PROPOSAL = "trinity-useful-compute-payment-proposal/v0.1"

UNSIGNED_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST"
DRY_SIGN_TOKEN = "I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST"

# Conservative v0.1 dust threshold (stocks). Outputs below this are
# moved into warnings[] and NOT included in the draft outputs.
DEFAULT_DUST_STOCKS = 546

STOCKS_PER_SOST = 100_000_000

_RID_RE  = re.compile(r"^uc-[0-9a-f]{16,64}$")
_WRID_RE = re.compile(r"^[0-9a-f]{16}$")
_ADDR_RE = re.compile(r"^sost1[023456789acdefghjklmnpqrstuvwxyz]{20,80}$")


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _load_proposal(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(f"proposal not found: {path}")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("proposal must be a JSON object")
    if obj.get("schema") != SCHEMA_PROPOSAL:
        raise ValueError(
            f"proposal wrong schema: {obj.get('schema')!r}; "
            f"expected {SCHEMA_PROPOSAL!r}"
        )
    pid = obj.get("proposal_id", "")
    if not (isinstance(pid, str)
            and re.match(r"^prop-[0-9a-f]{16}$", pid)):
        raise ValueError(f"proposal_id wrong format: {pid!r}")
    items = obj.get("payable_items")
    if not isinstance(items, list):
        raise ValueError("proposal payable_items must be a list")
    return obj


def _validate_payable_item(item: Any) -> Optional[str]:
    if not isinstance(item, dict):
        return "payable_item not an object"
    rid = item.get("request_id", "")
    if not (isinstance(rid, str) and _RID_RE.match(rid)):
        return f"bad request_id: {rid!r}"
    addr = item.get("payout_address", "")
    if not (isinstance(addr, str) and _ADDR_RE.match(addr)):
        return f"bad payout_address: {addr!r}"
    stocks = item.get("allocated_stocks")
    if not (isinstance(stocks, int) and stocks >= 0):
        return f"bad allocated_stocks: {stocks!r}"
    wrids = item.get("worker_result_ids", [])
    if not (isinstance(wrids, list)
            and all(
                isinstance(w, str) and _WRID_RE.match(w) for w in wrids
            )):
        return "bad worker_result_ids"
    return None


def run_payment_draft(
    *,
    proposal_path: Path,
    out_dir: Path,
    pinned_time: str,
    unsigned_only: bool = True,
    dry_sign: bool = False,
    wallet_path: Optional[Path] = None,
    from_label: Optional[str] = None,
    from_address: Optional[str] = None,
    max_total_stocks: Optional[int] = None,
    require_confirmation_token: Optional[str] = None,
    dust_stocks: int = DEFAULT_DUST_STOCKS,
) -> Dict[str, Any]:
    """Build the payment draft. Raises ValueError on any gate
    violation. Writes the draft JSON + a Markdown summary to
    ``out_dir`` and returns the draft dict."""

    # --- Mode gating ------------------------------------------------
    if unsigned_only and dry_sign:
        raise ValueError(
            "--unsigned-only and --dry-sign are mutually exclusive"
        )
    if not unsigned_only and not dry_sign:
        # Default to the safest mode.
        unsigned_only = True

    if dry_sign:
        if require_confirmation_token != DRY_SIGN_TOKEN:
            raise ValueError(
                "--dry-sign requires the exact confirmation token: "
                + DRY_SIGN_TOKEN
            )
        if wallet_path is None:
            raise ValueError("--dry-sign requires --wallet")
        if not Path(wallet_path).exists():
            raise ValueError(
                f"--wallet file not found: {wallet_path}"
            )
        if from_label is None and from_address is None:
            raise ValueError(
                "--dry-sign requires --from-label or --from-address"
            )
    else:
        # unsigned-only mode. The token is still required so a bare
        # invocation cannot accidentally produce a draft.
        if require_confirmation_token != UNSIGNED_TOKEN:
            raise ValueError(
                "--unsigned-only requires the exact confirmation "
                "token: " + UNSIGNED_TOKEN
            )
        if wallet_path is not None or from_label is not None \
                or from_address is not None:
            raise ValueError(
                "unsigned-only mode must not be combined with "
                "--wallet / --from-label / --from-address"
            )

    if max_total_stocks is not None and max_total_stocks < 0:
        raise ValueError(
            "max_total_stocks must be >= 0 if supplied"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    proposal = _load_proposal(proposal_path)

    proposal_id = proposal["proposal_id"]
    payable = proposal.get("payable_items", [])

    outputs: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for i, item in enumerate(payable):
        prob = _validate_payable_item(item)
        if prob is not None:
            warnings.append(
                f"payable_items[{i}] skipped — {prob}"
            )
            continue
        stocks = int(item["allocated_stocks"])
        if stocks == 0:
            warnings.append(
                f"payable_items[{i}] skipped — zero allocated stocks "
                f"for {item['payout_address']}"
            )
            continue
        if stocks < int(dust_stocks):
            warnings.append(
                f"payable_items[{i}] skipped as dust — "
                f"{item['payout_address']} = {stocks} stocks "
                f"(< {dust_stocks} stock dust threshold)"
            )
            continue
        outputs.append({
            "payout_address": item["payout_address"],
            "amount_stocks": int(stocks),
            "amount_sost": float(stocks) / STOCKS_PER_SOST,
            "request_id": item["request_id"],
            "worker_result_ids": sorted(
                item.get("worker_result_ids", [])
            ),
            "reason": (
                item.get("reason")
                or "primary_workers_share payment from proposal"
            ),
        })

    outputs.sort(
        key=lambda o: (o["request_id"], o["payout_address"]),
    )

    total_payment = sum(o["amount_stocks"] for o in outputs)

    if max_total_stocks is not None and total_payment > max_total_stocks:
        raise ValueError(
            f"total_payment_stocks {total_payment} exceeds "
            f"--max-total-stocks {max_total_stocks}; refusing to "
            "build draft. Reduce the proposal's payable_items or "
            "raise the cap."
        )

    # Capsule summary copies the proposal's capsule_summary block
    # verbatim. The draft does NOT publish it on-chain.
    capsule = proposal.get("capsule_summary") or {
        "template": "useful_compute_reward_batch_v1",
        "text": "Trinity Useful Compute draft (no capsule_summary "
                "in source proposal).",
        "referenced_files": {
            "budget_id": "bud-" + "0" * 16,
            "governance_batch_ids": [],
            "validation_ids": [],
        },
    }

    # Wallet access (dry-sign only). v0.1 does NOT actually sign.
    wallet_access_used = False
    signed_tx_hex: Optional[str] = None
    unsigned_tx_hex: Optional[str] = None
    if dry_sign:
        wallet_access_used = True
        signed_tx_hex = "DRYSIGN_PLACEHOLDER_NO_REAL_SIGNING_IN_V01"
        warnings.append(
            "dry-sign mode: signed_tx_hex is a placeholder string. "
            "v0.1 verifies the --wallet path exists but does NOT "
            "load keys and does NOT sign. Real wallet integration "
            "lands in a separate sprint."
        )
        if from_label is not None:
            warnings.append(
                f"dry-sign --from-label={from_label!r} recorded for "
                "audit; not used by v0.1."
            )
        if from_address is not None:
            warnings.append(
                f"dry-sign --from-address={from_address!r} recorded "
                "for audit; not used by v0.1."
            )

    if not outputs:
        warnings.append(
            "no eligible outputs after filtering (empty proposal, "
            "all dust, or all invalid). Draft contains zero "
            "outputs and zero payment stocks."
        )

    # Deterministic draft_id.
    draft_id = "draft-" + _sha16(canonical_dumps({
        "mode": "unsigned_only" if unsigned_only else "dry_sign",
        "source_proposal_id": proposal_id,
        "pinned_time": pinned_time,
        "outputs": outputs,
        "warnings": warnings,
        "max_total_stocks": max_total_stocks,
    }))

    draft = {
        "schema": SCHEMA_DRAFT,
        "draft_id": draft_id,
        "source_proposal_id": proposal_id,
        "mode": "local-dry-run",
        "unsigned_only": bool(unsigned_only),
        "dry_signed": bool(dry_sign),
        "total_outputs": len(outputs),
        "total_payment_stocks": int(total_payment),
        # v0.1 does not estimate fees or change. The fields exist
        # so a future sprint can fill them without bumping the
        # schema for additive metadata.
        "total_fee_stocks_estimated": 0,
        "change_stocks_estimated": 0,
        "outputs": outputs,
        "capsule_summary": capsule,
        "unsigned_tx_hex": unsigned_tx_hex,
        "signed_tx_hex": signed_tx_hex,
        "txid_if_signed": None,
        "warnings": warnings,
        "safety_status": {
            "no_broadcast":                True,
            "human_review_required":       True,
            "dry_sign_only":               bool(dry_sign),
            "wallet_access_used":          bool(wallet_access_used),
            "private_keys_exported":       False,
            "requires_separate_broadcast": True,
        },
    }

    draft_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_{draft_id}.json"
    )
    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_SUMMARY.md"
    )
    draft_path.write_text(canonical_dumps(draft), encoding="utf-8")
    summary_path.write_text(
        _render_summary_md(draft), encoding="utf-8",
    )
    return draft


def _render_summary_md(draft: Dict[str, Any]) -> str:
    lines = [
        "# TRINITY USEFUL COMPUTE — PAYMENT DRAFT (review-only)",
        "",
        f"- schema: `{draft['schema']}`",
        f"- draft_id: `{draft['draft_id']}`",
        f"- source_proposal_id: `{draft['source_proposal_id']}`",
        f"- mode: `{draft['mode']}`",
        f"- unsigned_only: **{draft['unsigned_only']}**",
        f"- dry_signed: **{draft['dry_signed']}**",
        "",
        "## Totals",
        "",
        f"- total_outputs: {draft['total_outputs']}",
        f"- total_payment_stocks: "
        f"**{draft['total_payment_stocks']:,}**",
        f"- total_fee_stocks_estimated: "
        f"{draft['total_fee_stocks_estimated']}",
        f"- change_stocks_estimated: "
        f"{draft['change_stocks_estimated']}",
        "",
        "## Outputs",
        "",
    ]
    if draft["outputs"]:
        lines.append(
            "| request_id | payout_address | workers | stocks | SOST |"
        )
        lines.append("|---|---|---|---|---|")
        for o in draft["outputs"]:
            lines.append(
                f"| {o['request_id']} | {o['payout_address']} | "
                f"{len(o['worker_result_ids'])} | "
                f"{o['amount_stocks']:,} | {o['amount_sost']} |"
            )
    else:
        lines.append("_none_")

    lines.extend(["", "## Warnings", ""])
    if draft["warnings"]:
        for w in draft["warnings"]:
            lines.append(f"- {w}")
    else:
        lines.append("_none_")

    lines.extend([
        "",
        "## Capsule summary (NOT published)",
        "",
        f"- template: `{draft['capsule_summary']['template']}`",
        f"- text: {draft['capsule_summary']['text']}",
    ])

    lines.extend([
        "",
        "## Tx hex blocks (informational, v0.1 placeholders)",
        "",
        f"- unsigned_tx_hex: `{draft['unsigned_tx_hex']}`",
        f"- signed_tx_hex:   `{draft['signed_tx_hex']}`",
        f"- txid_if_signed:  `{draft['txid_if_signed']}`",
    ])

    lines.extend([
        "",
        "## Safety",
        "",
        "- **THIS DRAFT IS NOT A BROADCAST.**",
        "- No transaction has been signed for production use.",
        "- No SOST has been moved.",
        "- v0.1 does not actually sign in dry-sign mode; it only",
        "  verifies the wallet path exists and writes a placeholder.",
        "- Real signing and a separate manual broadcast happen in",
        "  a future sprint.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_payment_draft",
        description=(
            "Trinity Useful Compute signed payment draft v0.1. "
            "Converts a payment proposal into a reviewable draft "
            "transaction. NEVER broadcasts, NEVER calls "
            "sendrawtransaction, NEVER exports a private key. "
            "Default mode is unsigned-only with no wallet access."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument("--proposal", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument(
        "--pinned-time", default="2026-05-12T00:00:00+00:00",
    )
    p.add_argument(
        "--unsigned-only", action="store_true",
        help="(default) Build a draft without touching any wallet.",
    )
    p.add_argument(
        "--dry-sign", action="store_true",
        help=(
            "Verify the --wallet file exists and record dry_signed=true. "
            "v0.1 does NOT load keys and does NOT actually sign; it "
            "writes a placeholder signed_tx_hex string. Real wallet "
            "integration lands in a future sprint."
        ),
    )
    p.add_argument(
        "--wallet", default=None,
        help="Required only when --dry-sign is set.",
    )
    p.add_argument("--from-label", default=None)
    p.add_argument("--from-address", default=None)
    # RPC flags are accepted for forward compatibility. v0.1 does
    # NOT call any RPC. The values are not stored in the draft.
    p.add_argument(
        "--rpc", default=None,
        help=(
            "Accepted for forward compatibility. v0.1 makes NO RPC "
            "call. The value is not stored in the draft."
        ),
    )
    p.add_argument(
        "--rpc-user", default=None,
        help="Accepted for forward compatibility (unused in v0.1).",
    )
    p.add_argument(
        "--rpc-pass", default=None,
        help="Accepted for forward compatibility (unused in v0.1).",
    )
    p.add_argument(
        "--max-total-stocks", type=int, default=None,
        help="Refuse to build a draft whose total_payment_stocks "
             "exceeds this cap.",
    )
    p.add_argument(
        "--require-confirmation-token", required=True,
        help=(
            "Mode-specific token. unsigned-only: "
            "I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST. "
            "dry-sign: "
            "I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST."
        ),
    )

    # Pre-argparse check: the script explicitly rejects flags that
    # would imply a send, broadcast, automatic payout or key
    # export. The rejection list is a tuple of string literals so
    # the Sprint 5.6 static safety check (which strips string
    # literals before scanning for forbidden identifiers) does NOT
    # surface false positives on attribute names like
    # args.export_private_key. argparse never sees these flags.
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    rejected_flags = (
        "--broadcast",
        "--send",
        "--payout-now",
        "--auto-pay",
        "--sendrawtransaction",
        "--export-private-key",
    )
    for f in rejected_flags:
        if f in raw_argv:
            print(
                "[useful_compute_payment_draft] flag "
                + f + " is rejected in v0.1",
                file=sys.stderr,
            )
            return 2

    args = p.parse_args(argv)

    if args.mode != "local-dry-run":
        print(
            "[useful_compute_payment_draft] only local-dry-run is "
            "supported in v0.1",
            file=sys.stderr,
        )
        return 2

    try:
        draft = run_payment_draft(
            proposal_path=Path(args.proposal),
            out_dir=Path(args.out_dir),
            pinned_time=args.pinned_time,
            unsigned_only=bool(args.unsigned_only or not args.dry_sign),
            dry_sign=bool(args.dry_sign),
            wallet_path=Path(args.wallet) if args.wallet else None,
            from_label=args.from_label,
            from_address=args.from_address,
            max_total_stocks=args.max_total_stocks,
            require_confirmation_token=args.require_confirmation_token,
        )
    except ValueError as exc:
        print(
            f"[useful_compute_payment_draft] error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        f"[useful_compute_payment_draft] draft_id={draft['draft_id']} "
        f"source_proposal={draft['source_proposal_id']}"
    )
    print(
        f"[useful_compute_payment_draft] outputs="
        f"{draft['total_outputs']} "
        f"total_payment_stocks={draft['total_payment_stocks']:,} "
        f"unsigned_only={draft['unsigned_only']} "
        f"dry_signed={draft['dry_signed']}"
    )
    print(
        f"[useful_compute_payment_draft] warnings="
        f"{len(draft['warnings'])} "
        f"wallet_access_used="
        f"{draft['safety_status']['wallet_access_used']} "
        f"private_keys_exported="
        f"{draft['safety_status']['private_keys_exported']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
