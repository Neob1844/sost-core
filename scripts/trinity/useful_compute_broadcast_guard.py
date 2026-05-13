#!/usr/bin/env python3
"""Trinity / Useful Compute — Human Broadcast Guard v0.1.

Sprint 5.18: the first Trinity layer that is *allowed* to broadcast a
SOST transaction, but only after a human operator passes every gate
explicitly. This script takes a Sprint 5.17 real-signed payment
draft (``trinity-useful-compute-payment-draft/v0.2`` with
``real_signed = true``), validates every safety flag on it, optionally
checks a maximum-payment cap, and either:

1. ``--mode local-dry-run`` (default): emits a receipt with
   ``broadcast_performed = false`` and ``txid_broadcast = null``,
   without invoking any subprocess; or
2. ``--mode human-broadcast``: requires the exact confirmation
   token ``I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION``,
   invokes ``sost-cli sendrawtransaction <signed_tx_hex>`` via
   ``subprocess.run(..., shell=False, timeout=...)`` and records
   the result in the receipt.

Hard invariants (enforced both at CLI and in the schema):

- NEVER touches a wallet. NEVER reads a private key. NEVER signs.
- NEVER auto-pays. NEVER loops. Exactly one transaction per run.
- ``subprocess.run`` is allowed ONLY for ``sost-cli`` with the
  ``sendrawtransaction`` subcommand and an allowlist of trusted
  argv values. No other subcommand is reachable. ``shell=False``
  always.
- ``--mode local-dry-run`` never invokes any subprocess.
- The CLI pre-argparse scan rejects any of these flags with rc=2:
  ``--auto-pay``, ``--send``, ``--payout-now``,
  ``--export-private-key``, ``--sign-now``.
- The receipt schema locks every safety_status flag to a const
  value so an offline reviewer can spot tampering trivially.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_RECEIPT = "trinity-useful-compute-broadcast-receipt/v0.1"
SCHEMA_DRAFT_V02 = "trinity-useful-compute-payment-draft/v0.2"

HUMAN_BROADCAST_TOKEN = "I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION"

# Tokens that must never appear in argv when we spawn sost-cli. The
# allowlist subcommand is "sendrawtransaction" only; everything else
# below is denied at runtime.
_ALLOWED_SUBCOMMANDS = ("sendrawtransaction",)
_FORBIDDEN_ARGV_TOKENS = (
    "--auto-pay",
    "--send",
    "--payout-now",
    "--export-private-key",
    "--sign-now",
)
_FLAGS_WITH_VALUE = (
    "--rpc",
    "--rpc-user",
    "--rpc-pass",
    "--node-host",
    "--node-port",
)

_TXID_RE = re.compile(r"^\s*Txid:\s*([0-9a-fA-F]{64})\s*$", re.MULTILINE)
_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")
_TXID64_RE = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_ID_RE = re.compile(r"^rcpt-[0-9a-f]{16}$")
_DRAFT_ID_RE = re.compile(r"^draft-[0-9a-f]{16}$")


class BroadcastGuardError(RuntimeError):
    """Raised by this module when any safety / parse precondition
    fails. main() turns it into a non-zero exit code with a user-
    facing message."""


@dataclass(frozen=True)
class _CliResult:
    txid: str


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hash_binary_file(path: Path) -> Optional[str]:
    try:
        return hashlib.sha256(
            Path(path).read_bytes(),
        ).hexdigest()[:16]
    except (OSError, FileNotFoundError):
        return None


def _scan_argv_safety(argv: List[str]) -> None:
    if not argv or not isinstance(argv, list):
        raise BroadcastGuardError("argv must be a non-empty list")
    for a in argv:
        if not isinstance(a, str):
            raise BroadcastGuardError("argv items must be strings")
    for tok in _FORBIDDEN_ARGV_TOKENS:
        if tok in argv:
            raise BroadcastGuardError(
                "forbidden token " + repr(tok)
                + " in argv (allowlist breach)"
            )
    # Find first non-flag positional (subcommand). Step over known
    # flag-with-value pairs so their VALUE is not mistaken for a
    # subcommand.
    subcmd = None
    i = 1
    while i < len(argv):
        a = argv[i]
        if a in _FLAGS_WITH_VALUE:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        subcmd = a
        break
    if subcmd not in _ALLOWED_SUBCOMMANDS:
        raise BroadcastGuardError(
            "subcommand " + repr(subcmd)
            + " not in allowlist " + repr(_ALLOWED_SUBCOMMANDS)
        )


def _load_draft(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise BroadcastGuardError(
            "payment draft not found: " + str(path)
        )
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BroadcastGuardError(
            "payment draft is not valid JSON: " + str(exc)
        ) from exc
    if not isinstance(obj, dict):
        raise BroadcastGuardError(
            "payment draft must be a JSON object"
        )
    return obj


def _validate_draft_for_broadcast(draft: Dict[str, Any]) -> None:
    """Refuse the draft if any safety precondition is missing or
    wrong. The checks are deliberately conservative — every test
    that the draft must pass is listed here, so a reviewer can read
    them top-to-bottom."""
    sch = draft.get("schema")
    if sch != SCHEMA_DRAFT_V02:
        raise BroadcastGuardError(
            "draft schema must be " + SCHEMA_DRAFT_V02
            + "; got " + repr(sch)
        )
    did = draft.get("draft_id", "")
    if not (isinstance(did, str) and _DRAFT_ID_RE.match(did)):
        raise BroadcastGuardError(
            "draft_id wrong format: " + repr(did)
        )
    if draft.get("real_signed") is not True:
        raise BroadcastGuardError(
            "draft.real_signed is not true; nothing to broadcast"
        )
    if draft.get("signing_mode") != "real_sign_local":
        raise BroadcastGuardError(
            "draft.signing_mode must be 'real_sign_local'; got "
            + repr(draft.get("signing_mode"))
        )
    scope = draft.get("signing_scope")
    if scope not in (
        "full_proposal", "single_payable_item_subset",
    ):
        raise BroadcastGuardError(
            "unknown draft.signing_scope: " + repr(scope)
        )
    hex_signed = draft.get("signed_tx_hex")
    if not (isinstance(hex_signed, str) and hex_signed
            and _HEX_RE.match(hex_signed)
            and len(hex_signed) % 2 == 0):
        raise BroadcastGuardError(
            "draft.signed_tx_hex is empty or not even-length hex"
        )
    txid = draft.get("txid_if_signed")
    if not (isinstance(txid, str) and _TXID64_RE.match(txid)):
        raise BroadcastGuardError(
            "draft.txid_if_signed must be 64 lowercase hex; got "
            + repr(txid)
        )
    if draft.get("capsule_attached") is not False:
        raise BroadcastGuardError(
            "draft.capsule_attached must be false in v0.1; got "
            + repr(draft.get("capsule_attached"))
        )
    ss = draft.get("safety_status")
    if not isinstance(ss, dict):
        raise BroadcastGuardError(
            "draft.safety_status missing or wrong type"
        )
    if ss.get("no_broadcast") is not True:
        raise BroadcastGuardError(
            "draft.safety_status.no_broadcast must be true on the "
            "source draft (the draft itself never broadcasts; the "
            "guard does)"
        )
    if ss.get("automatic_payout") is not False:
        raise BroadcastGuardError(
            "draft.safety_status.automatic_payout must be false"
        )
    if ss.get("human_review_required") is not True:
        raise BroadcastGuardError(
            "draft.safety_status.human_review_required must be true"
        )
    if ss.get("private_keys_exported") is not False:
        raise BroadcastGuardError(
            "draft.safety_status.private_keys_exported must be false"
        )
    if ss.get("requires_separate_broadcast") is not True:
        raise BroadcastGuardError(
            "draft.safety_status.requires_separate_broadcast must "
            "be true"
        )


def _call_sost_cli_sendraw(
    *,
    signed_tx_hex: str,
    sost_cli_bin: str,
    timeout_seconds: float,
) -> _CliResult:
    argv: List[str] = [
        str(sost_cli_bin),
        "sendrawtransaction",
        signed_tx_hex,
    ]
    _scan_argv_safety(argv)
    try:
        cp = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise BroadcastGuardError(
            "sost-cli sendrawtransaction timed out after "
            + str(timeout_seconds) + "s"
        ) from exc
    except FileNotFoundError as exc:
        raise BroadcastGuardError(
            "sost-cli binary not found at " + repr(sost_cli_bin)
        ) from exc
    if cp.returncode != 0:
        raise BroadcastGuardError(
            "sost-cli sendrawtransaction exited "
            + str(cp.returncode)
            + "; stderr: " + repr(cp.stderr.strip()[:512])
        )
    m = _TXID_RE.search(cp.stdout)
    if not m:
        raise BroadcastGuardError(
            "sost-cli sendrawtransaction stdout did not contain "
            "a Txid line"
        )
    return _CliResult(txid=m.group(1).lower())


def _build_receipt(
    *,
    draft: Dict[str, Any],
    mode: str,
    broadcast_performed: bool,
    txid_broadcast: Optional[str],
    confirmation_token: Optional[str],
    max_total_stocks: int,
    pinned_time: str,
    sost_cli_bin_hash: Optional[str],
) -> Dict[str, Any]:
    payment = int(draft.get("total_payment_stocks", 0))
    signed_hex = draft["signed_tx_hex"]
    receipt_id = "rcpt-" + _sha16(canonical_dumps({
        "mode": mode,
        "source_draft_id": draft["draft_id"],
        "txid_if_signed": draft["txid_if_signed"],
        "txid_broadcast": txid_broadcast,
        "broadcast_performed": broadcast_performed,
        "pinned_time": pinned_time,
        "max_total_stocks": max_total_stocks,
    }))
    return {
        "schema": SCHEMA_RECEIPT,
        "receipt_id": receipt_id,
        "source_draft_id": draft["draft_id"],
        "txid_if_signed": draft["txid_if_signed"],
        "txid_broadcast": txid_broadcast,
        "signed_tx_hex_sha256": hashlib.sha256(
            signed_hex.encode("utf-8"),
        ).hexdigest(),
        "broadcast_performed": bool(broadcast_performed),
        "broadcast_mode": mode,
        "confirmation_token_hash": (
            _sha256_hex(confirmation_token)
            if confirmation_token else None
        ),
        "total_payment_stocks": payment,
        "max_total_stocks": int(max_total_stocks),
        "pinned_time": pinned_time,
        "sost_cli_bin_hash": sost_cli_bin_hash,
        "safety_status": {
            "human_broadcast_only":          True,
            "requires_manual_confirmation":  True,
            "no_private_keys":               True,
            "no_wallet_access":              True,
            "no_signing":                    True,
            "no_automatic_payout":           True,
            "single_transaction_only":       True,
        },
    }


def run_broadcast_guard(
    *,
    draft_path: Path,
    out_dir: Path,
    mode: str,
    max_total_stocks: int,
    pinned_time: str,
    require_confirmation_token: Optional[str] = None,
    sost_cli_bin: str = "sost-cli",
    timeout_seconds: float = 60.0,
) -> Dict[str, Any]:
    """Validate a Sprint 5.17 real-signed draft and (optionally)
    broadcast its signed_tx_hex. Returns the receipt dict. Writes
    the receipt JSON + a Markdown summary into ``out_dir``."""

    if mode not in ("local-dry-run", "human-broadcast"):
        raise BroadcastGuardError(
            "--mode must be 'local-dry-run' or 'human-broadcast'; "
            "got " + repr(mode)
        )
    if max_total_stocks is None or int(max_total_stocks) < 0:
        raise BroadcastGuardError(
            "--max-total-stocks must be >= 0 and supplied"
        )

    draft = _load_draft(Path(draft_path))
    _validate_draft_for_broadcast(draft)

    payment = int(draft.get("total_payment_stocks", 0))
    if payment > int(max_total_stocks):
        raise BroadcastGuardError(
            "draft.total_payment_stocks " + str(payment)
            + " exceeds --max-total-stocks "
            + str(max_total_stocks)
            + "; refusing to broadcast anything"
        )

    if mode == "human-broadcast":
        if require_confirmation_token != HUMAN_BROADCAST_TOKEN:
            raise BroadcastGuardError(
                "--mode human-broadcast requires the exact "
                "confirmation token: " + HUMAN_BROADCAST_TOKEN
            )
        # All gates passed — invoke sost-cli sendrawtransaction.
        bin_hash = _hash_binary_file(Path(sost_cli_bin))
        if not Path(sost_cli_bin).is_absolute():
            # Recorded in the receipt's safety surface via the
            # bin_hash being None when sost-cli is only on PATH;
            # the operator can verify it ahead of time.
            pass
        res = _call_sost_cli_sendraw(
            signed_tx_hex=draft["signed_tx_hex"],
            sost_cli_bin=sost_cli_bin,
            timeout_seconds=timeout_seconds,
        )
        if res.txid != draft["txid_if_signed"]:
            raise BroadcastGuardError(
                "txid mismatch between draft ("
                + draft["txid_if_signed"]
                + ") and node response (" + res.txid + ")"
            )
        receipt = _build_receipt(
            draft=draft, mode=mode,
            broadcast_performed=True,
            txid_broadcast=res.txid,
            confirmation_token=require_confirmation_token,
            max_total_stocks=int(max_total_stocks),
            pinned_time=pinned_time,
            sost_cli_bin_hash=bin_hash,
        )
    else:
        # local-dry-run: no subprocess.
        bin_hash = _hash_binary_file(Path(sost_cli_bin))
        receipt = _build_receipt(
            draft=draft, mode=mode,
            broadcast_performed=False,
            txid_broadcast=None,
            confirmation_token=None,
            max_total_stocks=int(max_total_stocks),
            pinned_time=pinned_time,
            sost_cli_bin_hash=bin_hash,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    rid = receipt["receipt_id"]
    receipt_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_BROADCAST_RECEIPT_{rid}.json"
    )
    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_BROADCAST_SUMMARY.md"
    )
    receipt_path.write_text(canonical_dumps(receipt), encoding="utf-8")
    summary_path.write_text(_render_summary_md(receipt), encoding="utf-8")
    return receipt


def _render_summary_md(receipt: Dict[str, Any]) -> str:
    lines = [
        "# TRINITY USEFUL COMPUTE — HUMAN BROADCAST RECEIPT",
        "",
        f"- schema: `{receipt['schema']}`",
        f"- receipt_id: `{receipt['receipt_id']}`",
        f"- source_draft_id: `{receipt['source_draft_id']}`",
        f"- broadcast_mode: **{receipt['broadcast_mode']}**",
        f"- broadcast_performed: **{receipt['broadcast_performed']}**",
        "",
        "## Transaction",
        "",
        f"- txid_if_signed (from draft): `{receipt['txid_if_signed']}`",
        f"- txid_broadcast (from node): "
        f"`{receipt['txid_broadcast'] or '-'}`",
        f"- signed_tx_hex_sha256: `{receipt['signed_tx_hex_sha256']}`",
        "",
        "## Totals",
        "",
        f"- total_payment_stocks: "
        f"**{receipt['total_payment_stocks']:,}**",
        f"- max_total_stocks: {receipt['max_total_stocks']:,}",
        "",
        "## Safety",
        "",
    ]
    for k in sorted(receipt["safety_status"].keys()):
        lines.append(f"- {k} = {receipt['safety_status'][k]}")
    lines.extend([
        "",
        "## Disclaimer",
        "",
        "- Broadcast is **human-triggered** and **never automatic**.",
        "- This receipt is the audit trail. No wallet was touched.",
        "- No private key, seed phrase or passphrase was read by",
        "  this script. No signing happened. Signing belongs to",
        "  Sprint 5.17.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_broadcast_guard",
        description=(
            "Trinity Useful Compute Human Broadcast Guard v0.1. "
            "Validates a Sprint 5.17 real-signed payment draft and "
            "either emits a dry-run receipt OR invokes "
            "sost-cli sendrawtransaction to broadcast it. NEVER "
            "automatic. NEVER touches a wallet. NEVER signs."
        ),
    )
    p.add_argument(
        "--mode", required=True,
        choices=["local-dry-run", "human-broadcast"],
    )
    p.add_argument("--draft", required=True,
                   help="Path to a Sprint 5.17 real-signed draft.")
    p.add_argument("--out-dir", required=True)
    p.add_argument(
        "--pinned-time", default="2026-05-13T00:00:00+00:00",
    )
    p.add_argument(
        "--max-total-stocks", type=int, required=True,
        help="Refuse to broadcast if the draft's "
             "total_payment_stocks exceeds this cap.",
    )
    p.add_argument(
        "--require-confirmation-token", default=None,
        help=(
            "Required only in --mode human-broadcast. Exact: "
            "I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION."
        ),
    )
    p.add_argument(
        "--sost-cli-bin", default="sost-cli",
        help="Path to the sost-cli binary. Defaults to PATH.",
    )
    p.add_argument(
        "--sost-cli-timeout", type=float, default=60.0,
        help="Timeout (seconds) per sost-cli invocation.",
    )

    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    rejected_flags = (
        "--auto-pay",
        "--send",
        "--payout-now",
        "--export-private-key",
        "--sign-now",
    )
    for f in rejected_flags:
        if f in raw_argv:
            print(
                "[useful_compute_broadcast_guard] flag "
                + f + " is rejected in v0.1",
                file=sys.stderr,
            )
            return 2

    args = p.parse_args(argv)

    try:
        receipt = run_broadcast_guard(
            draft_path=Path(args.draft),
            out_dir=Path(args.out_dir),
            mode=args.mode,
            max_total_stocks=args.max_total_stocks,
            pinned_time=args.pinned_time,
            require_confirmation_token=
                args.require_confirmation_token,
            sost_cli_bin=args.sost_cli_bin,
            timeout_seconds=args.sost_cli_timeout,
        )
    except BroadcastGuardError as exc:
        print(
            "[useful_compute_broadcast_guard] error: " + str(exc),
            file=sys.stderr,
        )
        return 2

    print(
        "[useful_compute_broadcast_guard] receipt_id="
        + receipt["receipt_id"]
        + " mode=" + receipt["broadcast_mode"]
        + " broadcast_performed="
        + str(receipt["broadcast_performed"])
    )
    if receipt["broadcast_performed"]:
        print(
            "[useful_compute_broadcast_guard] "
            "txid_broadcast=" + receipt["txid_broadcast"]
            + " payment_stocks="
            + str(receipt["total_payment_stocks"])
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
