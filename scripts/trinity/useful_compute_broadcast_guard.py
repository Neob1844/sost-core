#!/usr/bin/env python3
"""Trinity / Useful Compute — Human Broadcast Guard v0.2.

Sprint 5.18 (hardened): the first Trinity layer allowed to broadcast
a SOST transaction, but only after a human operator passes every
gate explicitly.

v0.2 adds an audit trail for FAILED broadcast attempts: every
invocation of ``--mode human-broadcast`` leaves a receipt on disk,
including when the subprocess returns non-zero, when the stdout
cannot be parsed, or when the node-returned txid does not match the
draft's ``txid_if_signed``. No silent failures.

Three states the receipt can land in for ``--mode human-broadcast``:

- ``broadcasted``    — node accepted, txid matched.
- ``node_rejected``  — sost-cli exited non-zero.
- ``parse_error``    — stdout had no Txid line.
- ``txid_mismatch``  — node returned a different txid than the draft.

For ``--mode local-dry-run`` the receipt status is ``dry_run`` and
no subprocess is invoked.

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
- ``broadcast_performed`` is true ONLY when ``broadcast_result_status``
  is ``broadcasted``. Any other state implies ``False``.
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


SCHEMA_RECEIPT = "trinity-useful-compute-broadcast-receipt/v0.2"
SCHEMA_DRAFT_V02 = "trinity-useful-compute-payment-draft/v0.2"

HUMAN_BROADCAST_TOKEN = "I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION"

# Allowed subcommand and forbidden tokens. _FLAGS_WITH_VALUE lets
# the argv-safety scan step over value-bearing flags so the FIRST
# positional argument is correctly identified as the subcommand.
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
_DRAFT_ID_RE = re.compile(r"^draft-[0-9a-f]{16}$")

# Stderr signatures that mean the CLI itself rejected the call
# BEFORE contacting the node. Distinguishing CLI-side rejections
# from node-side rejections lets the operator triage faster:
# "fix your CLI invocation" vs "investigate the node".
_CLI_REJECTION_PATTERNS = (
    "error loading wallet",
    "empty hex",
    "hex length",
    "non-hex character",
    "accepts exactly one",
    "usage: sost-cli sendrawtransaction",
    "no such file",
    "permission denied",
    "401 unauthorized",
)


def _classify_subprocess_failure(stderr: str) -> str:
    """Inspect captured stderr from a non-zero sost-cli exit and
    decide whether the failure happened in the CLI wrapper itself
    (e.g. wallet load failure, hex validation, RPC auth) or after
    the wrapper handed the tx to the node. Returns either
    ``"cli_rejected"`` or ``"node_rejected"``."""
    low = (stderr or "").lower()
    for pat in _CLI_REJECTION_PATTERNS:
        if pat in low:
            return "cli_rejected"
    return "node_rejected"


class BroadcastGuardError(RuntimeError):
    """Raised by this module when a precondition fails BEFORE any
    subprocess is spawned. main() turns it into a non-zero exit code
    with a user-facing message. NO receipt is written for these
    pre-subprocess refusals — the draft never reached the wallet."""


class BroadcastAttemptFailure(RuntimeError):
    """Raised AFTER a subprocess attempt has been made and a receipt
    has been written. main() turns it into a non-zero exit code so
    the operator notices, while the receipt on disk preserves the
    audit trail."""

    def __init__(self, message: str, receipt_path: Path) -> None:
        super().__init__(message)
        self.receipt_path = receipt_path


@dataclass(frozen=True)
class _CliResult:
    txid: str
    stdout: str
    stderr: str


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
    # First positional argv (after argv[0] = binary path) is the
    # subcommand. Step over flags-with-value pairs.
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
            "source draft"
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
):
    """Returns a tuple ``(returncode, stdout, stderr)``. Does NOT
    raise on non-zero exit. The caller decides what to do with the
    result so that an audit receipt is always written first."""
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
        return (
            -1,
            "",
            "TIMEOUT after " + str(timeout_seconds) + "s",
        )
    except FileNotFoundError:
        return (
            -1,
            "",
            "sost-cli binary not found at " + repr(sost_cli_bin),
        )
    return (cp.returncode, cp.stdout, cp.stderr)


def _build_receipt(
    *,
    draft: Dict[str, Any],
    mode: str,
    broadcast_attempted: bool,
    broadcast_performed: bool,
    broadcast_result_status: str,
    txid_broadcast: Optional[str],
    node_txid_observed: Optional[str],
    node_stdout: Optional[str],
    node_stderr: Optional[str],
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
        "broadcast_attempted": broadcast_attempted,
        "broadcast_performed": broadcast_performed,
        "broadcast_result_status": broadcast_result_status,
        "node_txid_observed": node_txid_observed,
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
        "broadcast_attempted": bool(broadcast_attempted),
        "broadcast_performed": bool(broadcast_performed),
        "broadcast_mode": mode,
        "broadcast_result_status": broadcast_result_status,
        "node_txid_observed": node_txid_observed,
        "node_stdout_sha256": (
            _sha256_hex(node_stdout) if node_stdout else None
        ),
        "node_stderr_sha256": (
            _sha256_hex(node_stderr) if node_stderr else None
        ),
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


def _write_receipt(out_dir: Path, receipt: Dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = receipt["receipt_id"]
    receipt_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_BROADCAST_RECEIPT_{rid}.json"
    )
    summary_path = (
        out_dir / "TRINITY_USEFUL_COMPUTE_BROADCAST_SUMMARY.md"
    )
    receipt_path.write_text(
        canonical_dumps(receipt), encoding="utf-8",
    )
    summary_path.write_text(
        _render_summary_md(receipt), encoding="utf-8",
    )
    return receipt_path


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
    the receipt JSON + a Markdown summary into ``out_dir`` for
    EVERY outcome that reaches subprocess: even non-zero exit,
    stdout parse failure or txid mismatch leaves a receipt on disk
    for audit. Refusals that happen BEFORE subprocess (token
    missing, schema wrong, cap exceeded, …) raise
    BroadcastGuardError and do NOT write a receipt.
    """

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

    bin_hash = _hash_binary_file(Path(sost_cli_bin))

    if mode == "local-dry-run":
        receipt = _build_receipt(
            draft=draft, mode=mode,
            broadcast_attempted=False,
            broadcast_performed=False,
            broadcast_result_status="dry_run",
            txid_broadcast=None,
            node_txid_observed=None,
            node_stdout=None, node_stderr=None,
            confirmation_token=None,
            max_total_stocks=int(max_total_stocks),
            pinned_time=pinned_time,
            sost_cli_bin_hash=bin_hash,
        )
        _write_receipt(out_dir, receipt)
        return receipt

    # mode == "human-broadcast"
    if require_confirmation_token != HUMAN_BROADCAST_TOKEN:
        raise BroadcastGuardError(
            "--mode human-broadcast requires the exact "
            "confirmation token: " + HUMAN_BROADCAST_TOKEN
        )

    rc, stdout, stderr = _call_sost_cli_sendraw(
        signed_tx_hex=draft["signed_tx_hex"],
        sost_cli_bin=sost_cli_bin,
        timeout_seconds=timeout_seconds,
    )

    # subprocess returned non-zero (-1 also covers timeout and
    # FileNotFoundError surfaced as a synthetic stderr in
    # _call_sost_cli_sendraw). Classify so the receipt distinguishes
    # CLI-side rejection (wallet load failure, hex validation, RPC
    # auth) from node-side rejection (insufficient fee, double
    # spend, mempool full, …).
    if rc != 0:
        status = _classify_subprocess_failure(stderr)
        receipt = _build_receipt(
            draft=draft, mode=mode,
            broadcast_attempted=True,
            broadcast_performed=False,
            broadcast_result_status=status,
            txid_broadcast=None,
            node_txid_observed=None,
            node_stdout=stdout, node_stderr=stderr,
            confirmation_token=require_confirmation_token,
            max_total_stocks=int(max_total_stocks),
            pinned_time=pinned_time,
            sost_cli_bin_hash=bin_hash,
        )
        receipt_path = _write_receipt(out_dir, receipt)
        raise BroadcastAttemptFailure(
            "sost-cli sendrawtransaction exited " + str(rc)
            + " (" + status + "); receipt written to "
            + str(receipt_path)
            + "; stderr (first 256 chars): "
            + repr(stderr.strip()[:256]),
            receipt_path=receipt_path,
        )

    m = _TXID_RE.search(stdout)
    if not m:
        receipt = _build_receipt(
            draft=draft, mode=mode,
            broadcast_attempted=True,
            broadcast_performed=False,
            broadcast_result_status="parse_error",
            txid_broadcast=None,
            node_txid_observed=None,
            node_stdout=stdout, node_stderr=stderr,
            confirmation_token=require_confirmation_token,
            max_total_stocks=int(max_total_stocks),
            pinned_time=pinned_time,
            sost_cli_bin_hash=bin_hash,
        )
        receipt_path = _write_receipt(out_dir, receipt)
        raise BroadcastAttemptFailure(
            "sost-cli sendrawtransaction stdout did not contain a "
            "Txid line; the broadcast MAY have succeeded on the "
            "node — check mempool with sost-cli getrawmempool. "
            "Receipt written to " + str(receipt_path),
            receipt_path=receipt_path,
        )

    node_txid = m.group(1).lower()
    if node_txid != draft["txid_if_signed"]:
        receipt = _build_receipt(
            draft=draft, mode=mode,
            broadcast_attempted=True,
            broadcast_performed=False,
            broadcast_result_status="txid_mismatch",
            txid_broadcast=None,
            node_txid_observed=node_txid,
            node_stdout=stdout, node_stderr=stderr,
            confirmation_token=require_confirmation_token,
            max_total_stocks=int(max_total_stocks),
            pinned_time=pinned_time,
            sost_cli_bin_hash=bin_hash,
        )
        receipt_path = _write_receipt(out_dir, receipt)
        raise BroadcastAttemptFailure(
            "txid mismatch between draft ("
            + draft["txid_if_signed"]
            + ") and node response (" + node_txid
            + "); receipt written to " + str(receipt_path),
            receipt_path=receipt_path,
        )

    receipt = _build_receipt(
        draft=draft, mode=mode,
        broadcast_attempted=True,
        broadcast_performed=True,
        broadcast_result_status="broadcasted",
        txid_broadcast=node_txid,
        node_txid_observed=node_txid,
        node_stdout=stdout, node_stderr=stderr,
        confirmation_token=require_confirmation_token,
        max_total_stocks=int(max_total_stocks),
        pinned_time=pinned_time,
        sost_cli_bin_hash=bin_hash,
    )
    _write_receipt(out_dir, receipt)
    return receipt


def _render_summary_md(receipt: Dict[str, Any]) -> str:
    lines = [
        "# TRINITY USEFUL COMPUTE — HUMAN BROADCAST RECEIPT",
        "",
        f"- schema: `{receipt['schema']}`",
        f"- receipt_id: `{receipt['receipt_id']}`",
        f"- source_draft_id: `{receipt['source_draft_id']}`",
        f"- broadcast_mode: **{receipt['broadcast_mode']}**",
        f"- broadcast_attempted: **{receipt['broadcast_attempted']}**",
        f"- broadcast_performed: **{receipt['broadcast_performed']}**",
        f"- broadcast_result_status: "
        f"**{receipt['broadcast_result_status']}**",
        "",
        "## Transaction",
        "",
        f"- txid_if_signed (from draft): `{receipt['txid_if_signed']}`",
        f"- txid_broadcast: `{receipt['txid_broadcast'] or '-'}`",
        f"- node_txid_observed: "
        f"`{receipt['node_txid_observed'] or '-'}`",
        f"- signed_tx_hex_sha256: `{receipt['signed_tx_hex_sha256']}`",
        f"- node_stdout_sha256: "
        f"`{receipt['node_stdout_sha256'] or '-'}`",
        f"- node_stderr_sha256: "
        f"`{receipt['node_stderr_sha256'] or '-'}`",
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
        "- Even FAILED broadcast attempts leave a receipt on disk.",
        "  Compare broadcast_result_status across receipts to find",
        "  the audit story.",
    ])
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_broadcast_guard",
        description=(
            "Trinity Useful Compute Human Broadcast Guard v0.2. "
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
                + f + " is rejected in v0.2",
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
    except BroadcastAttemptFailure as exc:
        # A receipt has been written; surface the failure to the
        # operator but point them at the audit file.
        print(
            "[useful_compute_broadcast_guard] attempt failed: "
            + str(exc),
            file=sys.stderr,
        )
        return 3

    print(
        "[useful_compute_broadcast_guard] receipt_id="
        + receipt["receipt_id"]
        + " mode=" + receipt["broadcast_mode"]
        + " status=" + receipt["broadcast_result_status"]
        + " attempted=" + str(receipt["broadcast_attempted"])
        + " performed=" + str(receipt["broadcast_performed"])
    )
    if receipt["broadcast_performed"]:
        print(
            "[useful_compute_broadcast_guard] "
            "txid_broadcast=" + (receipt["txid_broadcast"] or "")
            + " payment_stocks="
            + str(receipt["total_payment_stocks"])
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
