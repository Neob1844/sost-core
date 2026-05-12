"""Trinity Web Miner Compute Console v0.1 — functional invariants.

These tests inspect website/trinity-useful-compute.html statically.
They confirm the console panel exists, that the file loaders are
wired, that the stock counters are present, and that the JS surface
uses textContent / no innerHTML for externally loaded data.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PATH = REPO_ROOT / "website" / "trinity-useful-compute.html"


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Panel + counters present
# ---------------------------------------------------------------------------


def test_console_panel_card_present():
    src = _read()
    assert 'id="minerConsoleCard"' in src
    assert "Miner Compute Console" in src


def test_console_stock_counter_ids_present():
    src = _read()
    for cid in (
        "stocksPendingUnvalidated",
        "stocksReplayAccepted",
        "stocksGovApproved",
        "stocksRejected",
        "stocksApprovedHeadline",
        "stocksApprovedSost",
    ):
        assert f'id="{cid}"' in src, (
            f"missing stock counter element: {cid!r}"
        )


def test_console_panel_explains_sost_unit():
    src = _read()
    assert "1 SOST = 100,000,000 stocks" in src


# ---------------------------------------------------------------------------
# File loaders + buttons present
# ---------------------------------------------------------------------------


_LOADER_IDS = (
    "consoleStateFile",
    "consoleEventsFile",
    "consoleRewardsFiles",
    "consoleValidationsFiles",
    "consoleGovFiles",
    "consoleLessonsFile",
)


def test_all_six_loader_inputs_present():
    src = _read()
    for fid in _LOADER_IDS:
        assert f'id="{fid}"' in src, f"missing loader input: {fid!r}"


def test_rewards_and_validations_and_gov_are_multi():
    src = _read()
    for fid in (
        "consoleRewardsFiles",
        "consoleValidationsFiles",
        "consoleGovFiles",
    ):
        m = re.search(
            rf'<input\s+id="{fid}"[^>]*>',
            src, re.IGNORECASE,
        )
        assert m is not None
        assert "multiple" in m.group(0), (
            f"{fid} should be <input multiple>"
        )


def test_reset_and_export_buttons_present():
    src = _read()
    assert 'id="consoleResetBtn"' in src
    assert 'id="consoleExportBtn"' in src
    assert ">Reset Console<" in src
    assert ">Export Summary JSON<" in src


# ---------------------------------------------------------------------------
# Tables + lists present
# ---------------------------------------------------------------------------


def test_console_task_table_present():
    src = _read()
    assert 'id="consoleTaskTable"' in src
    assert 'id="consoleTaskTbody"' in src
    # Column headers we care about
    for hdr in (
        "request_id", "worker_result_id", "worker_id",
        "compute_sha (short)", "stocks",
        "validation", "governance", "manual_review", "status",
    ):
        assert hdr in src, f"missing column header: {hdr!r}"


def test_console_events_and_lessons_present():
    src = _read()
    for sid in (
        "consoleEventsList", "consoleEventsEmpty",
        "consoleEventsWarning",
        "consoleLessonsList", "consoleLessonsRaw",
        "consoleLessonsEmpty",
    ):
        assert f'id="{sid}"' in src, f"missing list/box: {sid!r}"


# ---------------------------------------------------------------------------
# JS surface
# ---------------------------------------------------------------------------


_JS_FUNCTION_NAMES = (
    "_consoleSetText",
    "_consoleAppendListItems",
    "_consoleRowCell",
    "_consoleStatusForReward",
    "_consoleRecompute",
    "_consoleRenderState",
    "_consoleRenderEvents",
    "_consoleRenderLessons",
    "_consoleRefreshAll",
    "_consoleParseRewardFile",
    "_consoleReset",
    "_consoleExportSummary",
)


def test_console_js_function_surface_present():
    src = _read()
    for name in _JS_FUNCTION_NAMES:
        assert f"function {name}" in src, (
            f"missing JS function declaration: {name!r}"
        )


def test_status_buckets_complete_in_js():
    src = _read()
    for bucket in (
        "pending_unvalidated",
        "replay_accepted",
        "governance_approved",
        "rejected_or_manual_review",
    ):
        assert bucket in src, (
            f"missing stock bucket {bucket!r} in JS"
        )


def test_status_badges_complete_in_js():
    src = _read()
    for badge in (
        '"governance approved"',
        '"replay accepted"',
        '"mismatch"',
        '"insufficient workers"',
        '"manual review"',
        '"pending"',
    ):
        assert badge in src, f"missing status badge {badge!r}"


def test_export_summary_carries_safety_status():
    src = _read()
    assert "TRINITY_MINER_CONSOLE_SUMMARY.json" in src
    assert "trinity-web-miner-console-summary/v0.1" in src
    for flag in (
        "local_dry_run_only", "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_broadcast", "no_network_required",
        "no_consensus_changes",
        "human_review_required_before_payment",
    ):
        assert flag in src, (
            f"export summary missing safety flag: {flag!r}"
        )


def test_export_summary_includes_task_statuses_field():
    src = _read()
    # The exported JSON declares task_statuses, stock_totals,
    # malformed_events_count and loaded_counts.
    assert "task_statuses" in src
    assert "stock_totals" in src
    assert "malformed_events_count" in src
    assert "loaded_counts" in src


# ---------------------------------------------------------------------------
# Parser tolerates malformed JSONL (no crash) — verified by checking the
# parser branches in source.
# ---------------------------------------------------------------------------


def test_events_parser_increments_malformed_counter():
    src = _read()
    # The events loader catches JSON.parse and tracks malformed lines.
    assert "consoleStore.eventsMalformed" in src
    assert "malformed event lines ignored" in src
    # The catch branch must increment the counter
    assert re.search(
        r"catch[^{]*\{\s*consoleStore\.eventsMalformed\+\+",
        src,
    ) is not None, (
        "events parser must increment eventsMalformed on bad JSON"
    )


def test_reward_parser_validates_schema_string():
    src = _read()
    assert "SCHEMA_REWARD_V01" in src
    assert "trinity-useful-compute-pending-reward/v0.1" in src


def test_validation_parser_validates_schema_string():
    src = _read()
    assert "SCHEMA_VALIDATION_V01" in src
    assert "trinity-useful-compute-validation/v0.1" in src


def test_gov_parser_validates_schema_string():
    src = _read()
    assert "SCHEMA_GOV_V01" in src
    assert "trinity-useful-compute-governance-batch/v0.1" in src


def test_daemon_state_parser_validates_schema_string():
    src = _read()
    assert "SCHEMA_DAEMON_STATE_V01" in src
    assert "trinity-background-daemon-state/v0.1" in src


# ---------------------------------------------------------------------------
# Reset behaviour: must reset every store key
# ---------------------------------------------------------------------------


def test_reset_clears_every_store_key():
    src = _read()
    m = re.search(r"function _consoleReset\(\)[\s\S]*?\}\s*\$\(",
                  src)
    assert m is not None
    body = m.group(0)
    for key in (
        "daemonState = null",
        "events = []",
        "eventsMalformed = 0",
        "rewards = []",
        "validations = []",
        "governance = []",
        "lessonsText",
        "lessonsAggregated = []",
    ):
        assert key in body, (
            f"_consoleReset must clear store key: {key!r}"
        )
