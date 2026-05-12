"""Trinity Web Miner Console x payment proposal — Sprint 5.15."""

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


def test_proposal_panel_card_present():
    src = _read()
    assert 'id="proposalPreviewCard"' in src
    assert "Payment Proposal Preview" in src


def test_proposal_panel_ids_present():
    src = _read()
    for cid in (
        "proposalFile", "proposalBadge", "proposalDetails",
        "propId", "propBudgetId", "propPayable",
        "propDeferred", "propUnresolved", "propPayableSost",
        "propPayableTbody", "propUnresolvedList", "propCapsule",
    ):
        assert f'id="{cid}"' in src


def test_proposal_table_columns_present():
    src = _read()
    for hdr in (
        "request_id", "payout_address", "workers",
        "stocks", "SOST", "governance_batch",
    ):
        m = re.search(
            r"<th\b[^>]*>\s*" + re.escape(hdr) + r"\s*</th>",
            src,
        )
        assert m is not None, (
            f"missing proposal column header {hdr!r}"
        )


# ---------------------------------------------------------------------------
# JS + schema
# ---------------------------------------------------------------------------


def test_proposal_js_function_surface_present():
    src = _read()
    assert "function _proposalRender" in src
    assert "SCHEMA_PROPOSAL_V01" in src
    assert "trinity-useful-compute-payment-proposal/v0.1" in src


# ---------------------------------------------------------------------------
# Disclaimers
# ---------------------------------------------------------------------------


def test_proposal_disclaimer_present():
    src = _read().lower()
    assert re.search(r"this\s+is\s+not\s+a\s+transaction", src) \
        is not None
    assert re.search(r"manual\s+signing\s+is\s+required", src) \
        is not None
    assert re.search(
        r"no\s+payment\s+has\s+been\s+signed", src,
    ) is not None


def test_proposal_badge_names_payment_feature():
    src = _read().lower()
    assert "payment proposal" in src or "payment" in src
    for f in ("worker", "replay", "governance", "daemon",
              "console", "benchmark", "budget"):
        assert f in src, f"badge lost prior feature {f!r}"


# ---------------------------------------------------------------------------
# Safety surface
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "new WebSocket(", "EventSource(",
    "navigator.sendBeacon",
)


def test_no_network_primitives_after_proposal():
    src = _read()
    for tok in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert tok not in src, (
            f"forbidden network primitive: {tok!r}"
        )


def test_no_sensitive_input_fields_after_proposal():
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


def test_no_signing_or_payment_prompt_phrases():
    src = _read().lower()
    for phrase in (
        "sign and broadcast",
        "broadcast now",
        "send tx now",
        "send rewards now",
        "trigger payout",
        "auto-pay proposal",
    ):
        assert phrase not in src
