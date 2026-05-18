"""Functional tests for Sprint 5.39 trinity_daily_report.py."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCRIPT = SCRIPTS_DIR / "trinity_daily_report.py"
TASK_QUEUE_SCRIPT = SCRIPTS_DIR / "task_queue.py"
AUTOPILOT_SCRIPT = SCRIPTS_DIR / "task_queue_autopilot.py"
DASHBOARD_SCRIPT = SCRIPTS_DIR / "task_queue_dashboard.py"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity" / "daily_report.schema.json"
)
FIXTURES = REPO_ROOT / "tests" / "trinity" / "fixtures" / "useful_compute"


def _import(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def daily():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return _import("trinity_daily_report", SCRIPT)


@pytest.fixture(scope="module")
def task_queue():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return _import("task_queue", TASK_QUEUE_SCRIPT)


@pytest.fixture(scope="module")
def autopilot():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return _import("task_queue_autopilot", AUTOPILOT_SCRIPT)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _drive_queue(task_queue, autopilot, tmp_path, n_items=2):
    queue_dir = tmp_path / "q"
    dash_dir = tmp_path / "dash"
    request_path = FIXTURES / "request_materials_engine.json"
    addr_map = FIXTURES / "address_map.json"
    governor = (
        REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"
    )
    pinned = "2026-05-18T00:00:00+00:00"
    task_queue.init_queue(queue_dir, pinned_time=pinned)
    for i in range(n_items):
        per_item_pinned = (
            "2026-05-18T00:0" + str(i + 1) + ":00+00:00"
        )
        task_queue.enqueue_item(
            queue_dir=queue_dir,
            request_json=request_path,
            worker_address_map=addr_map,
            governor_policy=governor,
            pinned_time=per_item_pinned,
            max_attempts=3,
        )
    autopilot.run_autopilot(
        queue_dir=queue_dir,
        max_batches=1,
        max_items_per_batch=n_items,
        pinned_time=pinned,
        dashboard_out_dir=dash_dir,
    )
    dash_files = sorted(dash_dir.glob(
        "TRINITY_TASK_QUEUE_DASHBOARD_*.json"
    ))
    assert dash_files, "autopilot did not write a dashboard"
    return queue_dir, dash_files[-1]


def test_script_exists():
    assert SCRIPT.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_report_validates_against_schema(daily, task_queue, autopilot, tmp_path, schema):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 2)
    report = daily.build_daily_report(
        dashboard_json=dash_json,
        queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    jsonschema.validate(report, schema)


def test_report_shape(daily, task_queue, autopilot, tmp_path):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 2)
    report = daily.build_daily_report(
        dashboard_json=dash_json,
        queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    assert report["schema"] == "trinity-daily-report/v0.1"
    assert re.match(r"^tdr-[0-9a-f]{16}$", report["report_id"])
    assert report["counts"]["completed"] == 2
    assert report["counts"]["failed"] == 0
    assert "PrOx" in report["top_materials"]
    assert report["cache_hits_total"] >= 2
    assert report["workers_seen_total"] >= 2
    # Two workers expected per item.
    assert "worker-A" in report["worker_ids"]
    assert "worker-B" in report["worker_ids"]
    assert report["safety_status"] in ("ok", "warning", "failed")


def test_markdown_render_no_absolute_tmp(daily, task_queue, autopilot, tmp_path):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 1)
    report = daily.build_daily_report(
        dashboard_json=dash_json,
        queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    md = daily.render_markdown(report)
    assert "/tmp/" not in md, "absolute /tmp/ leaked into markdown"


def test_markdown_render_no_javascript(daily, task_queue, autopilot, tmp_path):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 1)
    report = daily.build_daily_report(
        dashboard_json=dash_json, queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    md = daily.render_markdown(report)
    assert "<script" not in md
    assert "javascript:" not in md
    # Markdown report has NO <html> shell.
    assert "<html" not in md


def test_markdown_render_has_counts_table(daily, task_queue, autopilot, tmp_path):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 1)
    report = daily.build_daily_report(
        dashboard_json=dash_json, queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    md = daily.render_markdown(report)
    assert "# Trinity Daily Report" in md
    assert "## Counts" in md
    assert "## Top materials" in md
    assert "## Workers seen" in md
    assert "## Materials cache" in md
    assert "## Completed items" in md
    assert "## Failed items" in md
    assert "## Warnings" in md
    assert "## Safety flags" in md


def test_safety_flags_all_const_true(daily, task_queue, autopilot, tmp_path):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 1)
    report = daily.build_daily_report(
        dashboard_json=dash_json, queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    for flag in (
        "no_wallet",
        "no_private_key",
        "no_signing",
        "no_broadcast",
        "no_autonomous_payment",
        "no_network",
    ):
        assert report["safety_flags"][flag] is True, "flag: " + flag


def test_report_deterministic(daily, task_queue, autopilot, tmp_path):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 1)
    r1 = daily.build_daily_report(
        dashboard_json=dash_json, queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    r2 = daily.build_daily_report(
        dashboard_json=dash_json, queue_dir=queue_dir,
        pinned_time="2026-05-18T00:01:00+00:00",
    )
    assert r1 == r2


def test_bad_dashboard_schema_rejected(daily, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({
        "schema": "trinity-task-queue-dashboard/v999",
        "counts": {},
        "latest_items": [],
    }))
    with pytest.raises(daily.DailyReportError):
        daily.build_daily_report(
            dashboard_json=bad,
            queue_dir=None,
            pinned_time="2026-05-18T00:00:00+00:00",
        )


def test_missing_dashboard_rejected(daily, tmp_path):
    with pytest.raises(daily.DailyReportError):
        daily.build_daily_report(
            dashboard_json=tmp_path / "nope.json",
            queue_dir=None,
            pinned_time="2026-05-18T00:00:00+00:00",
        )


def test_cli_writes_json_and_md(daily, task_queue, autopilot, tmp_path):
    queue_dir, dash_json = _drive_queue(task_queue, autopilot, tmp_path, 1)
    out_json = tmp_path / "report.json"
    out_md   = tmp_path / "report.md"
    rc = daily.main([
        "--dashboard-json", str(dash_json),
        "--queue-dir", str(queue_dir),
        "--out-json", str(out_json),
        "--out-md",   str(out_md),
        "--pinned-time", "2026-05-18T00:01:00+00:00",
    ])
    assert rc == 0
    assert out_json.is_file()
    assert out_md.is_file()
    parsed = json.loads(out_json.read_text())
    assert parsed["schema"] == "trinity-daily-report/v0.1"


def test_cli_missing_dashboard_returns_2(daily, tmp_path):
    out_json = tmp_path / "report.json"
    out_md   = tmp_path / "report.md"
    rc = daily.main([
        "--dashboard-json", str(tmp_path / "nope.json"),
        "--out-json", str(out_json),
        "--out-md",   str(out_md),
        "--pinned-time", "2026-05-18T00:01:00+00:00",
    ])
    assert rc == 2
