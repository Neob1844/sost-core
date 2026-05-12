"""Trinity Web Miner Console x reward budget policy — Sprint 5.14."""

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


def test_budget_panel_card_present():
    src = _read()
    assert 'id="budgetPolicyCard"' in src
    assert "Reward Budget Policy" in src


def test_budget_counter_ids_present():
    src = _read()
    for cid in (
        "budgetCountGovApproved",
        "budgetCountAllocated",
        "budgetCountDeferred",
    ):
        assert f'id="{cid}"' in src


def test_budget_detail_ids_present():
    src = _read()
    for cid in (
        "budgetFile", "budgetBadge", "budgetDetails",
        "budBudgetId", "budPolicy", "budEpoch",
        "budPool", "budDaily", "budEpochBudget",
        "budRequested", "budAllocated", "budDeferred",
        "budCapsList", "budAllocTbody",
    ):
        assert f'id="{cid}"' in src


def test_budget_allocations_table_columns_present():
    src = _read()
    for hdr in (
        "request_id", "batch_id", "workers",
        "requested", "allocated", "deferred",
        "status", "cap_reason",
    ):
        m = re.search(
            r"<th\b[^>]*>\s*" + re.escape(hdr) + r"\s*</th>",
            src,
        )
        assert m is not None, (
            f"missing allocations column header {hdr!r}"
        )


# ---------------------------------------------------------------------------
# Counters / disclaimers
# ---------------------------------------------------------------------------


def test_three_visible_budget_labels():
    src = _read()
    for label in (
        "governance_approved_stocks",
        "budget_allocated_stocks",
        "budget_deferred_stocks",
    ):
        assert label in src


def test_budget_disclaimer_present():
    src = _read().lower()
    # Match across optional whitespace so HTML line wraps don't
    # break the assertion.
    assert re.search(
        r"budget\s+allocation\s+is\s+not\s+payment", src,
    ) is not None
    assert re.search(
        r"deferred\s+stocks\s+are\s+not\s+lost", src,
    ) is not None
    # Either of the canonical "separate payment sprint" phrasings.
    assert re.search(
        r"separate[^\.]*payment\s+sprint",
        src,
    ) is not None


# ---------------------------------------------------------------------------
# JS surface
# ---------------------------------------------------------------------------


def test_budget_js_function_surface_present():
    src = _read()
    for name in (
        "_budgetSetCounters",
        "_budgetRenderAllocations",
    ):
        assert f"function {name}" in src


def test_budget_schema_string_referenced():
    src = _read()
    assert "trinity-useful-compute-reward-budget/v0.1" in src


def test_budget_badge_names_budget_feature():
    src = _read().lower()
    assert "budget" in src
    for f in ("worker", "replay", "governance", "daemon",
              "console", "benchmark"):
        assert f in src, f"badge lost prior feature {f!r}"


# ---------------------------------------------------------------------------
# Safety: no payment / wallet / network primitives
# ---------------------------------------------------------------------------


_FORBIDDEN_NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "new WebSocket(", "EventSource(",
    "navigator.sendBeacon",
)


def test_no_network_primitives_in_budget_section():
    src = _read()
    for tok in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert tok not in src, (
            f"forbidden network primitive in web page: {tok!r}"
        )


def test_budget_section_has_no_sensitive_inputs():
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


def test_no_automatic_payment_phrases_in_budget_section():
    src = _read().lower()
    for phrase in (
        "click to pay",
        "send rewards now",
        "trigger payout",
        "auto-pay budget",
        "automatic payment authorised",
    ):
        assert phrase not in src
