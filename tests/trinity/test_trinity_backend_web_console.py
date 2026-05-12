"""Web miner console x backend adapters — Sprint 5.12 surfaces."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PATH = REPO_ROOT / "website" / "trinity-useful-compute.html"


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Backend counters present
# ---------------------------------------------------------------------------


def test_backend_kind_counter_ids_present():
    src = _read()
    for cid in (
        "backendCountPlaceholder",
        "backendCountSandboxToy",
        "backendCountRealBackend",
    ):
        assert f'id="{cid}"' in src, (
            f"missing backend counter element: {cid!r}"
        )


def test_real_backend_counter_labeled_v01_zero():
    src = _read()
    # The label must spell out that v0.1 keeps it 0.
    assert "real_backend_rewards (v0.1: always 0)" in src \
        or "must remain 0" in src.lower()


def test_task_table_includes_backend_columns():
    src = _read()
    for hdr in ("backend", "kind"):
        # Match a <th> cell whose text is exactly that header.
        m = re.search(
            r"<th\b[^>]*>\s*" + re.escape(hdr) + r"\s*</th>",
            src,
        )
        assert m is not None, (
            f"missing backend column header {hdr!r}"
        )


def test_backend_disclaimer_present_on_console():
    src = _read().lower()
    assert "sandbox toy backends are not scientific validation" in src
    assert "real dft" in src
    assert "not enabled" in src


# ---------------------------------------------------------------------------
# Schema strings bumped
# ---------------------------------------------------------------------------


def test_console_uses_v02_reward_and_validation_schemas():
    """The console does NOT load result files; it inspects pending
    rewards (v0.2) and validations (v0.2). The v0.3 result schema
    string is intentionally absent from the HTML because no parser
    here consumes that file kind."""
    src = _read()
    assert "trinity-useful-compute-pending-reward/v0.2" in src
    assert "trinity-useful-compute-validation/v0.2" in src
    assert "trinity-useful-compute-result/v0.3" not in src


def test_console_references_pending_reward_v02_schema_string():
    src = _read()
    assert "trinity-useful-compute-pending-reward/v0.2" in src


def test_console_references_validation_v02_schema_string():
    src = _read()
    assert "trinity-useful-compute-validation/v0.2" in src


# ---------------------------------------------------------------------------
# JS surface: backend kind counters update
# ---------------------------------------------------------------------------


def test_js_aggregates_backend_kind_counts():
    src = _read()
    # The recompute function must keep three counter buckets and
    # update three text nodes accordingly.
    assert "byKind" in src
    assert "byKind.placeholder" in src
    assert "byKind.sandbox_toy" in src
    assert "byKind.real_backend" in src
    assert '_consoleSetText("backendCountPlaceholder"' in src
    assert '_consoleSetText("backendCountSandboxToy"' in src
    assert '_consoleSetText("backendCountRealBackend"' in src


def test_export_summary_includes_backend_kind_counts():
    src = _read()
    assert "backend_kind_counts" in src


# ---------------------------------------------------------------------------
# Safety surface for the new section: no prohibited claims
# ---------------------------------------------------------------------------


_FORBIDDEN_CLAIM_PHRASES = (
    "real dft validated",
    "scientifically validated",
    "scientific validation completed",
    "publishable result",
)


def test_no_real_dft_claim_phrases():
    src = _read().lower()
    for phrase in _FORBIDDEN_CLAIM_PHRASES:
        assert phrase not in src, (
            f"forbidden claim phrase present in web page: {phrase!r}"
        )


def test_console_badge_names_backend_feature():
    src = _read().lower()
    assert "backend" in src
    # The badge should also still name the other features.
    for f in ("worker", "replay", "governance", "daemon", "console"):
        assert f in src, f"badge lost feature {f!r}"
