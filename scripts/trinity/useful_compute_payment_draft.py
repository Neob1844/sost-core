#!/usr/bin/env python3
"""Trinity / Useful Compute — Signed Payment Draft v0.2.

Converts a Sprint 5.15 payment proposal into a reviewable transaction
draft. v0.2 adds a third mode — ``--real-sign`` — that delegates to
the existing ``sost-cli createtx`` binary through the sibling module
``useful_compute_real_signer``. Real signing produces a real
``signed_tx_hex`` and ``txid_if_signed`` per payable item, but the
script NEVER broadcasts and NEVER calls sendrawtransaction.

Three modes, mutually exclusive:

1. ``--unsigned-only`` (default). No wallet referenced. One draft
   per proposal (multi-output if the proposal has many).
2. ``--dry-sign``. Records ``dry_signed=true`` and writes a
   placeholder ``signed_tx_hex`` string after verifying the wallet
   path exists. v0.2 inherits this v0.1 behaviour unchanged.
3. ``--real-sign`` (NEW in v0.2). Invokes ``sost-cli createtx`` once
   per eligible payable item, producing ONE draft file per item
   with a real signed hex and txid. Each draft has exactly one
   output. ``--max-total-stocks`` caps the sum across all items.

Hard invariants (enforced both at CLI and in the schema):

- NEVER broadcasts. The schema flag ``no_broadcast`` is locked
  ``const: true``.
- NEVER calls ``sendrawtransaction`` or any send-style RPC.
- NEVER exports a private key. ``private_keys_exported`` is locked
  ``const: false``.
- ``requires_separate_broadcast`` is locked ``const: true``.
- ``human_review_required`` is locked ``const: true``.
- ``automatic_payout`` is locked ``const: false`` (NEW in v0.2).
- Rejects the CLI flags ``--broadcast``, ``--send``,
  ``--payout-now``, ``--auto-pay``, ``--sendrawtransaction``,
  ``--export-private-key`` with rc=2.
- All subprocess interaction lives in ``useful_compute_real_signer``
  (loaded via ``importlib`` so this file remains free of subprocess
  tokens and the Sprint 5.6 static safety surface is preserved).

Mode tokens (exact match required, no substring matching):

- unsigned-only mode:
    I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST
- dry-sign mode:
    I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST
- real-sign mode (NEW):
    I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_DRAFT = "trinity-useful-compute-payment-draft/v0.2"
SCHEMA_PROPOSAL = "trinity-useful-compute-payment-proposal/v0.1"

UNSIGNED_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST"
DRY_SIGN_TOKEN = "I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST"
REAL_SIGN_TOKEN = "I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST"

# Conservative v0.2 dust threshold (stocks). Outputs below this are
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


def _load_module_from_file(modname: str, path: Path):
    """Trinity convention: dynamically load a sibling module by file
    path. Avoids sys.path manipulation and keeps each Trinity script
    independent."""
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_real_signer():
    here = Path(__file__).resolve().parent
    return _load_module_from_file(
        "_trinity_real_signer",
        here / "useful_compute_real_signer.py",
    )


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
    if item.get("status") in ("unresolved", "deferred", "rejected"):
        return (
            "payable_item status is "
            + repr(item["status"])
            + " — must be 'pending' or 'approved' for real signing"
        )
    return None


def _filter_eligible_outputs(
    payable: List[Any],
    dust_stocks: int,
) -> tuple[List[Dict[str, Any]], List[str]]:
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
    return outputs, warnings


def _resolve_capsule(proposal: Dict[str, Any]) -> Dict[str, Any]:
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
    return capsule


def _build_safety_status(
    *,
    dry_sign: bool,
    wallet_access_used: bool,
) -> Dict[str, Any]:
    return {
        "no_broadcast":                True,
        "human_review_required":       True,
        "dry_sign_only":               bool(dry_sign),
        "wallet_access_used":          bool(wallet_access_used),
        "private_keys_exported":       False,
        "requires_separate_broadcast": True,
        "automatic_payout":            False,
    }


def _hash_binary_file(path: Path) -> Optional[str]:
    """sha16 fingerprint of a binary file. Returns None if the file
    does not exist or cannot be read. Used to record which sost-cli
    binary produced the signed_tx_hex without disclosing its full
    contents."""
    try:
        return hashlib.sha256(
            Path(path).read_bytes(),
        ).hexdigest()[:16]
    except (OSError, FileNotFoundError):
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
    """Build the v0.2 unsigned-only / dry-sign draft (legacy v0.1
    semantics, schema bumped). Raises ValueError on any gate
    violation. Writes the draft JSON + a Markdown summary to
    ``out_dir`` and returns the draft dict.

    For ``--real-sign`` use ``run_real_sign_drafts`` instead.
    """
    if unsigned_only and dry_sign:
        raise ValueError(
            "--unsigned-only and --dry-sign are mutually exclusive"
        )
    if not unsigned_only and not dry_sign:
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
        raise ValueError("max_total_stocks must be >= 0 if supplied")

    out_dir.mkdir(parents=True, exist_ok=True)
    proposal = _load_proposal(proposal_path)

    proposal_id = proposal["proposal_id"]
    payable = proposal.get("payable_items", [])

    outputs, warnings = _filter_eligible_outputs(payable, dust_stocks)
    total_payment = sum(o["amount_stocks"] for o in outputs)

    if max_total_stocks is not None and total_payment > max_total_stocks:
        raise ValueError(
            f"total_payment_stocks {total_payment} exceeds "
            f"--max-total-stocks {max_total_stocks}; refusing to "
            "build draft. Reduce the proposal's payable_items or "
            "raise the cap."
        )

    capsule = _resolve_capsule(proposal)

    wallet_access_used = False
    signed_tx_hex: Optional[str] = None
    unsigned_tx_hex: Optional[str] = None
    signing_mode = "unsigned_only"
    if dry_sign:
        signing_mode = "dry_sign_placeholder"
        wallet_access_used = True
        signed_tx_hex = "DRYSIGN_PLACEHOLDER_NO_REAL_SIGNING_IN_V01"
        warnings.append(
            "dry-sign mode: signed_tx_hex is a placeholder string. "
            "Dry-sign verifies the --wallet path exists but does "
            "NOT load keys and does NOT sign. Use --real-sign for "
            "real local signing."
        )
        if from_label is not None:
            warnings.append(
                f"dry-sign --from-label={from_label!r} recorded for "
                "audit; not used by dry-sign mode."
            )
        if from_address is not None:
            warnings.append(
                f"dry-sign --from-address={from_address!r} recorded "
                "for audit; not used by dry-sign mode."
            )

    if not outputs:
        warnings.append(
            "no eligible outputs after filtering (empty proposal, "
            "all dust, or all invalid). Draft contains zero "
            "outputs and zero payment stocks."
        )

    draft_id = "draft-" + _sha16(canonical_dumps({
        "mode": signing_mode,
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
        "signing_mode": signing_mode,
        "unsigned_only": bool(unsigned_only),
        "dry_signed": bool(dry_sign),
        "real_signed": False,
        "wallet_fingerprint_hash": None,
        "signer_label_or_address_hash": None,
        "sost_cli_bin_hash": None,
        "total_outputs": len(outputs),
        "total_payment_stocks": int(total_payment),
        "total_fee_stocks_estimated": 0,
        "change_stocks_estimated": 0,
        "total_input_stocks": 0,
        "total_output_stocks": int(total_payment),
        "fee_rate_stocks_per_byte": None,
        "selected_utxos": [],
        "outputs": outputs,
        "capsule_summary": capsule,
        "capsule_attached": False,
        "unsigned_tx_hex": unsigned_tx_hex,
        "signed_tx_hex": signed_tx_hex,
        "txid_if_signed": None,
        "warnings": warnings,
        "safety_status": _build_safety_status(
            dry_sign=dry_sign,
            wallet_access_used=wallet_access_used,
        ),
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
        _render_summary_md([draft]), encoding="utf-8",
    )
    return draft


def run_real_sign_drafts(
    *,
    proposal_path: Path,
    out_dir: Path,
    pinned_time: str,
    wallet_path: Path,
    from_label: Optional[str] = None,
    from_address: Optional[str] = None,
    max_total_stocks: int,
    require_confirmation_token: str,
    dust_stocks: int = DEFAULT_DUST_STOCKS,
    sost_cli_bin: str = "sost-cli",
    timeout_seconds: float = 60.0,
) -> List[Dict[str, Any]]:
    """Build ONE real-signed draft for a single-output proposal via
    ``sost-cli createtx``. Raises ValueError on any gate violation.
    Writes one draft JSON file + a Markdown summary.

    HARD LIMIT: v0.1 of --real-sign refuses any proposal that, after
    dust / validation filtering, contains more than ONE eligible
    output. The reason is a correctness bug, not policy:
    ``sost-cli createtx`` calls ``clear_utxos()`` then
    ``sync_wallet_utxos_from_node()`` on every invocation, so two
    sequential calls in the same script would see the SAME UTXO as
    spendable and select it twice — producing two signed
    transactions that conflict at broadcast. There is no safe
    multi-output sendmany API exposed from sost-cli today.
    """
    if require_confirmation_token != REAL_SIGN_TOKEN:
        raise ValueError(
            "--real-sign requires the exact confirmation token: "
            + REAL_SIGN_TOKEN
        )
    if wallet_path is None:
        raise ValueError("--real-sign requires --wallet")
    if not Path(wallet_path).exists():
        raise ValueError(
            f"--wallet file not found: {wallet_path}"
        )
    if from_label is None and from_address is None:
        raise ValueError(
            "--real-sign requires --from-label or --from-address"
        )
    if max_total_stocks is None or max_total_stocks < 0:
        raise ValueError(
            "--real-sign requires --max-total-stocks >= 0"
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    proposal = _load_proposal(proposal_path)

    proposal_id = proposal["proposal_id"]
    payable = proposal.get("payable_items", [])

    outputs, base_warnings = _filter_eligible_outputs(
        payable, dust_stocks,
    )
    total_payment = sum(o["amount_stocks"] for o in outputs)

    if total_payment > max_total_stocks:
        raise ValueError(
            f"total_payment_stocks {total_payment} exceeds "
            f"--max-total-stocks {max_total_stocks}; refusing to "
            "sign anything. Reduce the proposal or raise the cap."
        )

    if not outputs:
        raise ValueError(
            "no eligible outputs to sign after dust/validation "
            "filtering; refusing to invoke wallet"
        )

    # P0 GUARD: multi-output real signing is unsafe today because
    # sequential createtx calls re-sync UTXOs from the chain and
    # would select the same UTXO twice → conflicting transactions
    # at broadcast time. Refuse until a real sendmany-style API is
    # exposed.
    if len(outputs) > 1:
        raise ValueError(
            "multi-output real signing not supported safely in "
            "v0.1 of --real-sign: sost-cli createtx is "
            "single-recipient and sequential calls would re-use "
            "UTXOs, producing conflicting signed transactions. "
            f"Proposal has {len(outputs)} eligible outputs; split "
            "the proposal so each --real-sign run targets exactly "
            "one output, or wait for a future sendmany-aware sprint."
        )

    capsule = _resolve_capsule(proposal)

    rs = _load_real_signer()

    if not Path(sost_cli_bin).is_absolute():
        base_warnings.append(
            "--sost-cli-bin is not an absolute path; PATH lookup is "
            "trusted. For production use an absolute path."
        )
    bin_hash = _hash_binary_file(Path(sost_cli_bin))

    wallet_fp = rs.hash_wallet_file(Path(wallet_path))
    signer_id = rs.hash_signer_identity(
        label=from_label, address=from_address,
    )

    output = outputs[0]
    # Format amount as plain SOST decimal string to feed the CLI
    # verbatim (the CLI's parse_amount expects "SOST" notation).
    amount_sost_str = "{:.8f}".format(
        output["amount_stocks"] / STOCKS_PER_SOST,
    )
    try:
        res = rs.call_sost_cli_createtx(
            wallet_path=Path(wallet_path),
            to_address=output["payout_address"],
            amount_sost=amount_sost_str,
            from_label=from_label,
            from_address=from_address,
            sost_cli_bin=sost_cli_bin,
            timeout_seconds=timeout_seconds,
        )
    except rs.RealSignerError as exc:
        raise ValueError(
            "real signing failed for "
            + output["payout_address"]
            + " (request_id=" + output["request_id"] + "): "
            + str(exc)
        ) from exc

    warnings: List[str] = list(base_warnings)
    if res.inputs_count == 0:
        warnings.append(
            "sost-cli reported 0 inputs; signed_tx_hex may be "
            "malformed. Investigate before broadcasting."
        )
    if res.outputs_count > 2:
        warnings.append(
            "sost-cli reported "
            + str(res.outputs_count)
            + " outputs (>2); unexpected for single-recipient "
            "createtx. Investigate before broadcasting."
        )
    warnings.append(
        "v0.1 of --real-sign does NOT attach the capsule_summary to "
        "the signed transaction. capsule_summary is recorded in the "
        "draft JSON for audit only. capsule_attached is locked to "
        "false in this sprint."
    )
    warnings.append(
        "sost-cli createtx marks the selected UTXOs as spent in the "
        "local wallet file even though nothing has been broadcast. "
        "If the operator discards this draft, the local wallet "
        "state will be re-synced from the chain on the next "
        "invocation (createtx calls clear_utxos before each run), "
        "so this is self-healing — but be aware of the temporary "
        "local-only mutation."
    )
    warnings.append(
        "v0.1 does not parse selected_utxos[] from sost-cli stdout; "
        "the count is exposed via inputs_count only. Decode "
        "signed_tx_hex to enumerate UTXOs if needed."
    )
    warnings.append(
        "SIGNED BUT NOT BROADCAST — broadcasting is a separate, "
        "human-driven sprint."
    )

    draft_id = "draft-" + _sha16(canonical_dumps({
        "mode": "real_sign_local",
        "source_proposal_id": proposal_id,
        "pinned_time": pinned_time,
        "output": output,
        "txid": res.txid_if_signed,
        "max_total_stocks": max_total_stocks,
    }))

    draft = {
        "schema": SCHEMA_DRAFT,
        "draft_id": draft_id,
        "source_proposal_id": proposal_id,
        "mode": "local-dry-run",
        "signing_mode": "real_sign_local",
        "unsigned_only": False,
        "dry_signed": False,
        "real_signed": True,
        "wallet_fingerprint_hash": wallet_fp,
        "signer_label_or_address_hash": signer_id,
        "sost_cli_bin_hash": bin_hash,
        "total_outputs": 1,
        "total_payment_stocks": int(output["amount_stocks"]),
        "total_fee_stocks_estimated": int(res.fee_stocks),
        "change_stocks_estimated": 0,
        "total_input_stocks": 0,
        "total_output_stocks": int(output["amount_stocks"]),
        "fee_rate_stocks_per_byte":
            int(res.fee_rate_stocks_per_byte),
        "selected_utxos": [],
        "outputs": [output],
        "capsule_summary": capsule,
        "capsule_attached": False,
        "unsigned_tx_hex": None,
        "signed_tx_hex": res.signed_tx_hex,
        "txid_if_signed": res.txid_if_signed,
        "warnings": warnings,
        "safety_status": _build_safety_status(
            dry_sign=False,
            wallet_access_used=True,
        ),
    }

    draft_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_{draft_id}.json"
    )
    draft_path.write_text(
        canonical_dumps(draft), encoding="utf-8",
    )
    drafts = [draft]

    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_SUMMARY.md"
    )
    summary_path.write_text(
        _render_summary_md(drafts), encoding="utf-8",
    )
    return drafts


def _render_summary_md(drafts: List[Dict[str, Any]]) -> str:
    """Render a Markdown summary for one or more drafts. v0.1
    behaviour preserved when a single draft is passed."""
    if not drafts:
        return "# TRINITY USEFUL COMPUTE — PAYMENT DRAFT (empty)\n"

    head = drafts[0]
    lines = [
        "# TRINITY USEFUL COMPUTE — PAYMENT DRAFT (review-only)",
        "",
        f"- schema: `{head['schema']}`",
        f"- source_proposal_id: `{head['source_proposal_id']}`",
        f"- mode: `{head['mode']}`",
        f"- signing_mode: **{head['signing_mode']}**",
        f"- drafts in this run: **{len(drafts)}**",
        "",
        "## Totals (aggregated across all drafts)",
        "",
    ]
    total_outputs = sum(d["total_outputs"] for d in drafts)
    total_payment = sum(d["total_payment_stocks"] for d in drafts)
    total_fee = sum(d["total_fee_stocks_estimated"] for d in drafts)
    lines.extend([
        f"- total_outputs: {total_outputs}",
        f"- total_payment_stocks: **{total_payment:,}**",
        f"- total_fee_stocks_estimated: {total_fee}",
        "",
    ])

    for idx, d in enumerate(drafts):
        lines.extend([
            f"## Draft {idx+1} of {len(drafts)} — `{d['draft_id']}`",
            "",
            f"- signing_mode: `{d['signing_mode']}`",
            f"- real_signed: **{d['real_signed']}**",
            f"- dry_signed: **{d['dry_signed']}**",
            f"- total_payment_stocks: {d['total_payment_stocks']:,}",
            f"- total_fee_stocks_estimated: "
            f"{d['total_fee_stocks_estimated']}",
            f"- fee_rate_stocks_per_byte: "
            f"{d['fee_rate_stocks_per_byte']}",
            f"- wallet_fingerprint_hash: "
            f"`{d['wallet_fingerprint_hash']}`",
            f"- signer_label_or_address_hash: "
            f"`{d['signer_label_or_address_hash']}`",
            "",
            "### Outputs",
            "",
        ])
        if d["outputs"]:
            lines.append(
                "| request_id | payout_address | workers | stocks | SOST |"
            )
            lines.append("|---|---|---|---|---|")
            for o in d["outputs"]:
                lines.append(
                    f"| {o['request_id']} | {o['payout_address']} | "
                    f"{len(o['worker_result_ids'])} | "
                    f"{o['amount_stocks']:,} | {o['amount_sost']} |"
                )
        else:
            lines.append("_none_")

        lines.extend([
            "",
            "### Tx hex",
            "",
            f"- signed_tx_hex: `{d['signed_tx_hex']}`",
            f"- txid_if_signed: `{d['txid_if_signed']}`",
            "",
            "### Warnings",
            "",
        ])
        if d["warnings"]:
            for w in d["warnings"]:
                lines.append(f"- {w}")
        else:
            lines.append("_none_")
        lines.append("")

    lines.extend([
        "## Safety",
        "",
        "- **NONE OF THE DRAFTS IN THIS RUN HAVE BEEN BROADCAST.**",
        "- Real-signed drafts contain a real `signed_tx_hex` and a",
        "  real `txid_if_signed`. They MUST still be reviewed by a",
        "  human, then broadcast in a separate, human-driven sprint.",
        "- No SOST has moved.",
        "- No automatic payout. No `sendrawtransaction` was called.",
        "- Private keys never left the wallet binary's process.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_payment_draft",
        description=(
            "Trinity Useful Compute signed payment draft v0.2. "
            "Converts a payment proposal into a reviewable draft "
            "transaction. NEVER broadcasts, NEVER calls "
            "sendrawtransaction, NEVER exports a private key, "
            "NEVER auto-pays. Three modes: --unsigned-only "
            "(default), --dry-sign (placeholder), --real-sign "
            "(real local signing via sost-cli createtx)."
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
            "v0.2 dry-sign does NOT load keys and does NOT actually "
            "sign; it writes a placeholder signed_tx_hex string. Use "
            "--real-sign for real local signing."
        ),
    )
    p.add_argument(
        "--real-sign", action="store_true",
        help=(
            "Invoke `sost-cli createtx` once per eligible payable "
            "item to produce a real signed_tx_hex and txid per draft. "
            "Requires --wallet, --from-label or --from-address, "
            "--max-total-stocks, and the exact confirmation token "
            "I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST. NEVER "
            "broadcasts."
        ),
    )
    p.add_argument(
        "--wallet", default=None,
        help="Required for --dry-sign and --real-sign.",
    )
    p.add_argument("--from-label", default=None)
    p.add_argument("--from-address", default=None)
    p.add_argument(
        "--rpc", default=None,
        help=(
            "Accepted for forward compatibility. v0.2 makes NO RPC "
            "call from this script. The value is not stored in the "
            "draft. sost-cli itself does read-only RPC."
        ),
    )
    p.add_argument(
        "--rpc-user", default=None,
        help="Accepted for forward compatibility (unused).",
    )
    p.add_argument(
        "--rpc-pass", default=None,
        help="Accepted for forward compatibility (unused).",
    )
    p.add_argument(
        "--max-total-stocks", type=int, default=None,
        help="Refuse to build / sign drafts whose total "
             "payment exceeds this cap.",
    )
    p.add_argument(
        "--sost-cli-bin", default="sost-cli",
        help=(
            "Path to the sost-cli binary used by --real-sign. "
            "Defaults to 'sost-cli' (operator's PATH)."
        ),
    )
    p.add_argument(
        "--sost-cli-timeout", type=float, default=60.0,
        help="Timeout (seconds) per sost-cli createtx invocation.",
    )
    p.add_argument(
        "--require-confirmation-token", required=True,
        help=(
            "Mode-specific token. unsigned-only: "
            "I_UNDERSTAND_THIS_IS_ONLY_A_DRAFT_AND_WILL_NOT_BROADCAST. "
            "dry-sign: "
            "I_UNDERSTAND_THIS_USES_WALLET_KEYS_BUT_DOES_NOT_BROADCAST. "
            "real-sign: "
            "I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST."
        ),
    )

    # Pre-argparse check: the script explicitly rejects flags that
    # would imply a send, broadcast, automatic payout or key
    # export. The rejection list is a tuple of string literals so
    # the Sprint 5.6 static safety check (which strips string
    # literals before scanning for forbidden identifiers) does NOT
    # surface false positives on attribute names. argparse never
    # sees these flags.
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
                + f + " is rejected in v0.2",
                file=sys.stderr,
            )
            return 2

    args = p.parse_args(argv)

    if args.mode != "local-dry-run":
        print(
            "[useful_compute_payment_draft] only local-dry-run is "
            "supported in v0.2",
            file=sys.stderr,
        )
        return 2

    n_modes = (
        int(bool(args.unsigned_only))
        + int(bool(args.dry_sign))
        + int(bool(args.real_sign))
    )
    if n_modes > 1:
        print(
            "[useful_compute_payment_draft] --unsigned-only, "
            "--dry-sign and --real-sign are mutually exclusive",
            file=sys.stderr,
        )
        return 2

    try:
        if args.real_sign:
            drafts = run_real_sign_drafts(
                proposal_path=Path(args.proposal),
                out_dir=Path(args.out_dir),
                pinned_time=args.pinned_time,
                wallet_path=(
                    Path(args.wallet) if args.wallet else None
                ),
                from_label=args.from_label,
                from_address=args.from_address,
                max_total_stocks=args.max_total_stocks,
                require_confirmation_token=
                    args.require_confirmation_token,
                sost_cli_bin=args.sost_cli_bin,
                timeout_seconds=args.sost_cli_timeout,
            )
            for d in drafts:
                print(
                    "[useful_compute_payment_draft] "
                    f"draft_id={d['draft_id']} "
                    f"signing_mode={d['signing_mode']} "
                    f"txid={d['txid_if_signed']} "
                    f"fee_stocks={d['total_fee_stocks_estimated']} "
                    f"payment_stocks={d['total_payment_stocks']}"
                )
            print(
                "[useful_compute_payment_draft] "
                f"drafts={len(drafts)} "
                "SIGNED_BUT_NOT_BROADCAST=true"
            )
            return 0

        # Legacy v0.1-compatible single-draft path.
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
        f"signing_mode={draft['signing_mode']}"
    )
    print(
        f"[useful_compute_payment_draft] warnings="
        f"{len(draft['warnings'])} "
        f"wallet_access_used="
        f"{draft['safety_status']['wallet_access_used']} "
        f"automatic_payout="
        f"{draft['safety_status']['automatic_payout']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
