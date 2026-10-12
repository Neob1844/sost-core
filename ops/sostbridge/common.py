"""Shared primitives for the wSOST bridge, Gold Reserve V2 and SOST governance (Stage 1, devnet only).

Nothing here touches SOST consensus. It reads the SOST chain through the node's RPC and parses the
existing capsule format (SCPv1, active since block 7,350) out of transaction outputs.
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_DOWN
from typing import Optional

from eth_utils import keccak, to_checksum_address, is_address

STOCKS_PER_SOST = 100_000_000
BRIDGE_VERSION = 1

# ---------------------------------------------------------------- amounts
def to_stocks(value) -> int:
    """SOST decimal (str/Decimal/int stocks) -> integer stocks, exact. Floats are refused."""
    if isinstance(value, bool):
        raise TypeError("bool is not an amount")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise TypeError("float amounts are refused (precision); pass a string")
    d = Decimal(str(value))
    q = d * STOCKS_PER_SOST
    if q != q.to_integral_value(rounding=ROUND_DOWN):
        raise ValueError(f"amount {value} has more than 8 decimals")
    return int(q)


def fmt_sost(stocks: int) -> str:
    s = "-" if stocks < 0 else ""
    stocks = abs(stocks)
    return f"{s}{stocks // STOCKS_PER_SOST}.{stocks % STOCKS_PER_SOST:08d}"


# ---------------------------------------------------------------- addresses
SOST_ADDR_RE = re.compile(r"^sost1[0-9a-f]{40}$")


def is_sost_address(a: str) -> bool:
    return bool(SOST_ADDR_RE.match(a or ""))


def vault_hash(sost_address: str) -> bytes:
    """bridgeVault field of the WSOST contract: keccak256 of the vault address string."""
    if not is_sost_address(sost_address):
        raise ValueError("bad SOST vault address")
    return keccak(text=sost_address)


# ---------------------------------------------------------------- deposit / burn ids
def deposit_id(txid_hex: str, vout: int) -> bytes:
    """Deterministic deposit id: keccak256("SOST-WSOST-DEPOSIT-V1" || txid(32) || vout(u32 BE))."""
    txid = bytes.fromhex(txid_hex)
    if len(txid) != 32 or not (0 <= vout < 2**32):
        raise ValueError("bad outpoint")
    return keccak(b"SOST-WSOST-DEPOSIT-V1" + txid + vout.to_bytes(4, "big"))


# ---------------------------------------------------------------- capsules (SCPv1 open note)
CAPSULE_HEADER = 12
OPEN_NOTE_TYPE = 0x01
OPEN_NOTE_MAX = 80


def build_open_note(text: str) -> str:
    """Payload hex of an SCPv1 open-note capsule (used by tests and the fake chain)."""
    t = text.encode("utf-8")
    if len(t) > OPEN_NOTE_MAX:
        raise ValueError("open note longer than 80 bytes")
    body = bytes([len(t)]) + t
    hdr = bytes([0x53, 0x43, 0x01, OPEN_NOTE_TYPE, 0, 0, 0, 0, 0, len(body), 0, 0])
    return (hdr + body).hex()


def parse_open_note(payload_hex: Optional[str]) -> Optional[str]:
    """Return the text of a well-formed SCPv1 open note, or None for anything else."""
    if not payload_hex:
        return None
    try:
        b = bytes.fromhex(payload_hex)
    except ValueError:
        return None
    if len(b) < CAPSULE_HEADER + 1 or b[0] != 0x53 or b[1] != 0x43 or b[2] != 0x01:
        return None
    if b[3] != OPEN_NOTE_TYPE or b[4] != 0:          # open note, no flags (never encrypted)
        return None
    body_len = b[9]
    body = b[CAPSULE_HEADER:]
    if len(body) != body_len or body_len < 1:
        return None
    n = body[0]
    if n + 1 != body_len or n > OPEN_NOTE_MAX:
        return None
    try:
        return body[1:].decode("utf-8")
    except UnicodeDecodeError:
        return None


WSOST_DEPOSIT_RE = re.compile(r"^WSOST:(0x[0-9a-fA-F]{40})$")
WSOST_RELEASE_RE = re.compile(r"^WSOST-RELEASE:(0x[0-9a-f]{64})$")


def parse_wsost_recipient(text: Optional[str]) -> Optional[str]:
    """'WSOST:0x<40 hex>' -> checksummed Ethereum address. Mixed-case input must carry a valid checksum."""
    if not text:
        return None
    m = WSOST_DEPOSIT_RE.match(text)
    if not m:
        return None
    a = m.group(1)
    body = a[2:]
    if body != body.lower() and body != body.upper():
        if to_checksum_address(a) != a:            # EIP-55 checksum must match when mixed case
            return None
    if not is_address(a):
        return None
    cs = to_checksum_address(a)
    if int(cs, 16) == 0:
        return None
    return cs


def release_note(burn_id: bytes) -> str:
    note = "WSOST-RELEASE:0x" + burn_id.hex()
    assert len(note.encode()) <= OPEN_NOTE_MAX
    return note


def parse_release(text: Optional[str]) -> Optional[bytes]:
    if not text:
        return None
    m = WSOST_RELEASE_RE.match(text)
    return bytes.fromhex(m.group(1)[2:]) if m else None
