"""Trinity Web Miner Console x benchmark ledger — Sprint 5.13."""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PATH = REPO_ROOT / "website" / "trinity-useful-compute.html"


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Benchmark counters
# ---------------------------------------------------------------------------


def test_benchmark_source_counter_ids_present():
    src = _read()
    for cid in (
        "benchSourceCountNone",
        "benchSourceCountReport",
        "benchSourceCountExperimental",
    ):
        assert f'id="{cid}"' in src


def test_visible_benchmark_counter_labels():
    src = _read()
    for label in (
        "unbenchmarked_rewards",
        "benchmarked_rewards",
        "experimental_rewards",
    ):
        assert label in src


def test_benchmark_disclaimer_present():
    src = _read().lower()
    assert "benchmark score is not proof of useful scientific output" \
        in src


def test_task_table_includes_benchmark_columns():
    src = _read()
    for hdr in ("benchmark", "work_score"):
        m = re.search(
            r"<th\b[^>]*>\s*" + re.escape(hdr) + r"\s*</th>",
            src,
        )
        assert m is not None, (
            f"missing benchmark column header {hdr!r}"
        )


# ---------------------------------------------------------------------------
# JS surface
# ---------------------------------------------------------------------------


def test_js_aggregates_benchmark_source_counts():
    src = _read()
    assert "bySource" in src
    assert "bySource.none" in src
    assert "bySource.report" in src
    assert "bySource.experimental" in src
    assert '_consoleSetText("benchSourceCountNone"' in src
    assert '_consoleSetText("benchSourceCountReport"' in src
    assert '_consoleSetText("benchSourceCountExperimental"' in src


def test_export_summary_includes_benchmark_source_counts():
    src = _read()
    assert "benchmark_source_counts" in src


def test_reward_parser_extracts_benchmark_fields():
    src = _read()
    # The reward parser must read benchmark_id,
    # normalized_work_score, benchmark_source from the JSON.
    assert "obj.benchmark_id" in src
    assert "obj.normalized_work_score" in src
    assert "obj.benchmark_source" in src


# ---------------------------------------------------------------------------
# Schema strings bumped in console
# ---------------------------------------------------------------------------


def test_console_uses_reward_v03_string():
    src = _read()
    assert "trinity-useful-compute-pending-reward/v0.3" in src
    assert "trinity-useful-compute-pending-reward/v0.2" not in src


def test_console_keeps_validation_v02_string():
    src = _read()
    assert "trinity-useful-compute-validation/v0.2" in src


# ---------------------------------------------------------------------------
# Badge name carries benchmark
# ---------------------------------------------------------------------------


def test_benchmark_present_in_badge():
    src = _read().lower()
    assert "benchmark" in src
    for f in ("worker", "replay", "governance", "daemon", "console"):
        assert f in src, f"badge lost feature {f!r}"


# ---------------------------------------------------------------------------
# Safety: no forbidden claim phrases
# ---------------------------------------------------------------------------


_FORBIDDEN_CLAIM_PHRASES = (
    "benchmark proves scientific",
    "benchmark validates science",
    "benchmark proves accuracy",
)


def test_no_benchmark_overclaim_phrases():
    src = _read().lower()
    for phrase in _FORBIDDEN_CLAIM_PHRASES:
        assert phrase not in src, (
            f"forbidden benchmark claim phrase: {phrase!r}"
        )
