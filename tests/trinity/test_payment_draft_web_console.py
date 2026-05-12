"""Trinity Web Miner Console x payment draft — Sprint 5.16."""

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


def test_draft_panel_card_present():
    src = _read()
    assert 'id="draftPreviewCard"' in src
    assert "Signed Payment Draft" in src


def test_draft_panel_ids_present():
    src = _read()
    for cid in (
        "draftFile", "draftBadge", "draftDetails",
        "draftId", "draftProposalId",
        "draftOutputs", "draftPaymentStocks",
        "draftPaymentSost", "draftFeeStocks",
        "draftChangeStocks", "draftSignedStatus",
        "draftSafetyList", "draftOutputsTbody",
        "draftWarningsList", "draftTxHexBlock",
    ):
        assert f'id="{cid}"' in src


def test_draft_outputs_table_columns():
    src = _read()
    for hdr in (
        "request_id", "payout_address", "workers",
        "stocks", "SOST",
    ):
        m = re.search(
            r"<th\b[^>]*>\s*" + re.escape(hdr) + r"\s*</th>",
            src,
        )
        assert m is not None, (
            f"missing draft column header {hdr!r}"
        )


# ---------------------------------------------------------------------------
# JS surface
# ---------------------------------------------------------------------------


def test_draft_js_render_function_present():
    src = _read()
    assert "function _draftRender" in src
    assert "SCHEMA_DRAFT_V01" in src
    assert "trinity-useful-compute-payment-draft/v0.1" in src


# ---------------------------------------------------------------------------
# Safety disclaimers
# ---------------------------------------------------------------------------


def test_draft_section_declares_no_signing_no_broadcast():
    src = _read().lower()
    # "This page does not sign or broadcast payments" disclaimer.
    assert re.search(
        r"this\s+page\s+does\s+not\s+sign\s+or\s+broadcast",
        src,
    ) is not None
    # Strip below the danger strip too.
    assert re.search(
        r"this\s+page\s+does\s+not\s+sign\s+or\s+broadcast\s+payments",
        src,
    ) is not None


def test_draft_section_mentions_separate_sprint():
    src = _read().lower()
    assert "separate wallet sprint" in src
    assert "separate" in src and "human-driven sprint" in src


def test_draft_badge_names_signed_payment_draft():
    src = _read().lower()
    assert "signed payment draft" in src
    # Old features still present.
    for f in ("worker", "replay", "governance", "daemon",
              "console", "benchmark", "budget", "proposal"):
        assert f in src, f"badge lost prior feature {f!r}"


# ---------------------------------------------------------------------------
# Static safety surface for the section
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "new WebSocket(", "EventSource(",
    "navigator.sendBeacon",
)


def test_no_network_primitives_after_draft():
    src = _read()
    for tok in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert tok not in src, (
            f"forbidden network primitive: {tok!r}"
        )


def test_no_sensitive_input_fields_after_draft():
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


def test_no_payment_prompt_phrases_in_draft_section():
    src = _read().lower()
    for phrase in (
        "send tx now",
        "broadcast now",
        "trigger payout",
        "click to sign",
        "auto-pay draft",
        "auto-sign",
        "publish capsule now",
    ):
        assert phrase not in src
