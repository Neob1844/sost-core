#!/usr/bin/env python3
"""Trinity / Useful Compute — real-signer delegate (Sprint 5.17).

This module is the ONLY part of the Trinity Useful Compute stack
allowed to spawn a subprocess. It wraps the existing
`sost-cli createtx` binary (single-recipient build + sign) so that
the higher-level `useful_compute_payment_draft.py` can stay free of
subprocess / shell tokens and keeps its Sprint 5.6 static safety
surface unchanged.

Hard invariants (enforced both statically and at runtime):

- Only the `sost-cli` binary is invoked. Path is overridable via the
  `sost_cli_bin` argument for tests; the literal default is the
  short name "sost-cli" so it picks up the operator's PATH.
- Only the `createtx` subcommand is allowed. Any other subcommand
  aborts before subprocess.run runs.
- Forbidden argv tokens (--broadcast, --send, --payout-now,
  --auto-pay, --sendrawtransaction, --export-private-key) are
  rejected before subprocess.run runs, as belt+braces over the
  obvious shell=False guarantee.
- shell=False always. No string interpolation into a shell ever.
- The module never reads or parses key material. The wallet file is
  hashed (sha256 of bytes) only to produce an audit fingerprint;
  no parsing of its contents.
- No HTTP / TCP / WebSocket primitives. The CLI itself talks to the
  local node via JSON-RPC read-only methods (listunspent, getblockcount)
  which is explicitly permitted by the Sprint 5.17 spec.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


_ALLOWED_SUBCOMMANDS = ("createtx",)

# Flags that take a separate argument after them. Knowing this is
# what lets _scan_argv_safety correctly identify the first
# *positional* argv element as the subcommand: when we see one of
# these, we step over its value before looking for the subcommand.
_FLAGS_WITH_VALUE = (
    "--wallet",
    "--from-label",
    "--from-address",
    "--node-host",
    "--node-port",
    "--rpc",
    "--rpc-user",
    "--rpc-pass",
)

_FORBIDDEN_ARGV_TOKENS = (
    "--broadcast",
    "--send",
    "--payout-now",
    "--auto-pay",
    "--sendrawtransaction",
    "--export-private-key",
)

_RAW_HEX_RE = re.compile(
    r"^\s*Raw hex:\s*([0-9a-fA-F]+)\s*$", re.MULTILINE,
)
_TXID_RE = re.compile(
    r"^\s*Txid:\s*([0-9a-fA-F]{64})\s*$", re.MULTILINE,
)
_FEE_RE = re.compile(
    r"^\s*Fee:\s*\S+\s+SOST\s*"
    r"\((\d+)\s+stocks\s*=\s*(\d+)\s+bytes\s+x\s+(\d+)\s+rate\)",
    re.MULTILINE,
)
_INPUTS_RE = re.compile(
    r"^\s*Inputs:\s*(\d+)\s*$", re.MULTILINE,
)
_OUTPUTS_RE = re.compile(
    r"^\s*Outputs:\s*(\d+)\s*$", re.MULTILINE,
)


class RealSignerError(RuntimeError):
    """Raised by this module when any safety / parse precondition
    fails. The higher-level draft script turns this into a non-zero
    exit code with a user-facing message."""


@dataclass(frozen=True)
class SignedTxResult:
    signed_tx_hex: str
    txid_if_signed: str
    fee_stocks: int
    size_bytes: int
    fee_rate_stocks_per_byte: int
    inputs_count: int
    outputs_count: int


def _sha16_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def _sha16_str(s: str) -> str:
    return _sha16_bytes(s.encode("utf-8"))


def hash_wallet_file(wallet_path: Path) -> str:
    """sha16 fingerprint of the wallet file bytes. Never parses
    contents. Never extracts keys. The hash is a pure audit token."""
    return _sha16_bytes(Path(wallet_path).read_bytes())


def hash_signer_identity(
    *, label: Optional[str], address: Optional[str],
) -> str:
    """sha16 of the label, falling back to address. Used to record
    which key was used to sign without storing the label/address in
    cleartext."""
    if label:
        return _sha16_str("label:" + label)
    if address:
        return _sha16_str("address:" + address)
    raise RealSignerError(
        "hash_signer_identity needs label or address"
    )


def _scan_argv_safety(argv: List[str]) -> None:
    if not argv or not isinstance(argv, list):
        raise RealSignerError("argv must be a non-empty list")
    for a in argv:
        if not isinstance(a, str):
            raise RealSignerError("argv items must be strings")
    # Forbidden tokens are checked BEFORE subcommand detection so a
    # broadcast-style flag always raises the "forbidden token"
    # message regardless of where it sits in argv.
    for tok in _FORBIDDEN_ARGV_TOKENS:
        if tok in argv:
            raise RealSignerError(
                "forbidden token " + repr(tok)
                + " in argv (allowlist breach)"
            )
    # Walk argv left-to-right. argv[0] is the binary path. Step
    # over flags-with-values so we do not mistake their VALUE for a
    # subcommand. The first positional non-flag string is the
    # subcommand; it must be in the allowlist.
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
        raise RealSignerError(
            "subcommand " + repr(subcmd)
            + " not in allowlist " + repr(_ALLOWED_SUBCOMMANDS)
        )


def call_sost_cli_createtx(
    *,
    wallet_path: Path,
    to_address: str,
    amount_sost: str,
    from_label: Optional[str] = None,
    from_address: Optional[str] = None,
    sost_cli_bin: str = "sost-cli",
    timeout_seconds: float = 60.0,
) -> SignedTxResult:
    """Invoke `sost-cli createtx` and parse the signed hex + txid.

    `amount_sost` is passed as a string so the caller controls
    decimal formatting. This function does not interpret it beyond
    handing it to the CLI verbatim.
    """
    argv: List[str] = [
        str(sost_cli_bin),
        "--wallet", str(wallet_path),
    ]
    if from_label is not None:
        argv += ["--from-label", from_label]
    if from_address is not None:
        argv += ["--from-address", from_address]
    argv += ["createtx", to_address, amount_sost]

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
        raise RealSignerError(
            "sost-cli createtx timed out after "
            + str(timeout_seconds) + "s"
        ) from exc
    except FileNotFoundError as exc:
        raise RealSignerError(
            "sost-cli binary not found at " + repr(sost_cli_bin)
            + "; install it or pass an explicit sost_cli_bin path"
        ) from exc

    if cp.returncode != 0:
        raise RealSignerError(
            "sost-cli createtx exited " + str(cp.returncode)
            + "; stderr: " + repr(cp.stderr.strip()[:512])
        )

    raw_m = _RAW_HEX_RE.search(cp.stdout)
    txid_m = _TXID_RE.search(cp.stdout)
    fee_m = _FEE_RE.search(cp.stdout)
    ins_m = _INPUTS_RE.search(cp.stdout)
    outs_m = _OUTPUTS_RE.search(cp.stdout)
    if not (raw_m and txid_m and fee_m and ins_m and outs_m):
        raise RealSignerError(
            "sost-cli createtx stdout did not match expected format"
        )

    return SignedTxResult(
        signed_tx_hex=raw_m.group(1).lower(),
        txid_if_signed=txid_m.group(1).lower(),
        fee_stocks=int(fee_m.group(1)),
        size_bytes=int(fee_m.group(2)),
        fee_rate_stocks_per_byte=int(fee_m.group(3)),
        inputs_count=int(ins_m.group(1)),
        outputs_count=int(outs_m.group(1)),
    )
