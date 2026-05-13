"""Trinity Web Miner Console x broadcast receipt — Sprint 5.18."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PATH = REPO_ROOT / "website" / "trinity-useful-compute.html"


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Panel + IDs present
# ---------------------------------------------------------------------------


def test_receipt_panel_card_present():
    src = _read()
    assert 'id="broadcastReceiptCard"' in src
    assert "Human Broadcast Guard" in src


def test_receipt_panel_ids_present():
    src = _read()
    for cid in (
        "receiptFile", "receiptBadge", "receiptDetails",
        "receiptId", "receiptDraftId", "receiptMode",
        "receiptPerformed", "receiptTxidSigned",
        "receiptTxidBroadcast", "receiptHexSha",
        "receiptPaymentStocks", "receiptMaxTotal",
        "receiptCliBinHash", "receiptSafetyList",
    ):
        assert f'id="{cid}"' in src, (
            f"broadcast receipt panel missing id {cid!r}"
        )


def test_receipt_js_render_function_present():
    src = _read()
    assert "function _receiptRender" in src
    assert "SCHEMA_RECEIPT_V01" in src
    assert "trinity-useful-compute-broadcast-receipt/v0.1" in src


# ---------------------------------------------------------------------------
# Disclaimers
# ---------------------------------------------------------------------------


def test_receipt_section_declares_human_triggered():
    src = _read().lower()
    assert "broadcast is human-triggered and never automatic" in src


def test_receipt_section_states_no_wallet_no_key():
    src = _read().lower()
    assert "no wallet" in src
    assert ("no private key" in src or "no key" in src)
    assert "seed" in src


def test_receipt_loaded_status_labels_present():
    """The badge advertises both dry-run and broadcasted states."""
    src = _read().lower()
    assert "loaded — broadcasted" in src or \
           "loaded - broadcasted" in src
    assert "loaded — dry-run" in src or \
           "loaded - dry-run" in src


# ---------------------------------------------------------------------------
# Safety surface for the new section (no fetch, no wallet inputs)
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "new WebSocket(", "EventSource(",
    "navigator.sendBeacon",
)


def test_no_network_primitives_with_receipt_panel():
    src = _read()
    for tok in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert tok not in src, (
            f"forbidden network primitive: {tok!r}"
        )


def test_no_sensitive_inputs_with_receipt_panel():
    src = _read()
    inputs = re.findall(r"<input\b[^>]*>", src, re.IGNORECASE)
    for tag in inputs:
        lower = tag.lower()
        for forbidden in (
            "private", "wallet", "seed", "mnemonic", "passphrase",
            "rpcpass", "rpcuser", "signature",
        ):
            assert forbidden not in lower, (
                f"<input> looks sensitive: {tag}"
            )


def test_no_broadcast_prompt_phrases():
    src = _read().lower()
    for phrase in (
        "broadcast now", "send tx now", "click to sign",
        "auto-pay draft", "publish capsule now", "sign in browser",
        "send transaction", "broadcast immediately",
    ):
        assert phrase not in src, (
            f"forbidden prompt phrase: {phrase!r}"
        )
