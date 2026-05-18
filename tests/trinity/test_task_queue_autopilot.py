"""Functional tests for Sprint 5.38 task_queue_autopilot.py."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
AUTOPILOT_SCRIPT = SCRIPTS_DIR / "task_queue_autopilot.py"
TASK_QUEUE_SCRIPT = SCRIPTS_DIR / "task_queue.py"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "task_queue_autopilot_report.schema.json"
)
FIXTURES = REPO_ROOT / "tests" / "trinity" / "fixtures" / "useful_compute"


def _import(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def autopilot():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return _import("task_queue_autopilot", AUTOPILOT_SCRIPT)


@pytest.fixture(scope="module")
def task_queue():
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    return _import("task_queue", TASK_QUEUE_SCRIPT)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _init_and_enqueue(task_queue, queue_dir, n_items=2):
    request_path = FIXTURES / "request_materials_engine.json"
    addr_map = FIXTURES / "address_map.json"
    governor = (
        REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"
    )
    pinned = "2026-05-18T00:01:00+00:00"
    task_queue.init_queue(queue_dir, pinned_time=pinned)
    for i in range(n_items):
        # Vary pinned_time per item so queue_item_id is unique.
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


def test_script_exists():
    assert AUTOPILOT_SCRIPT.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_max_batches_above_cap_refused(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    with pytest.raises(autopilot.AutopilotError):
        autopilot.run_autopilot(
            queue_dir=queue_dir,
            max_batches=25,  # > AUTOPILOT_MAX_BATCHES_CAP
            max_items_per_batch=1,
            pinned_time="2026-05-18T00:00:00+00:00",
            dashboard_out_dir=tmp_path / "dash",
        )


def test_max_batches_zero_refused(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    with pytest.raises(autopilot.AutopilotError):
        autopilot.run_autopilot(
            queue_dir=queue_dir,
            max_batches=0,
            max_items_per_batch=1,
            pinned_time="2026-05-18T00:00:00+00:00",
            dashboard_out_dir=tmp_path / "dash",
        )


def test_max_items_per_batch_above_cap_refused(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    with pytest.raises(autopilot.AutopilotError):
        autopilot.run_autopilot(
            queue_dir=queue_dir,
            max_batches=1,
            max_items_per_batch=51,
            pinned_time="2026-05-18T00:00:00+00:00",
            dashboard_out_dir=tmp_path / "dash",
        )


def test_one_batch_processes_items(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=2)
    report = autopilot.run_autopilot(
        queue_dir=queue_dir,
        max_batches=1,
        max_items_per_batch=2,
        pinned_time="2026-05-18T00:00:00+00:00",
        dashboard_out_dir=tmp_path / "dash",
    )
    assert report["schema"] == "trinity-task-queue-autopilot-report/v0.1"
    assert re.match(r"^tap-[0-9a-f]{16}$", report["autopilot_id"])
    assert report["batches_attempted"] == 1
    assert report["items_completed"] == 2
    assert report["items_failed"] == 0
    assert report["safety_status"] == "ok"
    assert report["final_queue_counts"]["pending"] == 0
    assert report["final_queue_counts"]["completed"] == 2
    assert report["stopped_reason"] in (
        "max_batches_reached", "queue_empty",
    )


def test_dashboard_files_written(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    dash_dir = tmp_path / "dash"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    report = autopilot.run_autopilot(
        queue_dir=queue_dir,
        max_batches=1,
        max_items_per_batch=1,
        pinned_time="2026-05-18T00:00:00+00:00",
        dashboard_out_dir=dash_dir,
    )
    assert len(report["dashboard_paths"]) == 1
    json_path = dash_dir / report["dashboard_paths"][0]
    html_path = json_path.with_suffix(".html")
    assert json_path.is_file()
    assert html_path.is_file()
    assert report["latest_dashboard_basename"] == json_path.name


def test_report_validates_against_schema(autopilot, task_queue, tmp_path, schema):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=2)
    report = autopilot.run_autopilot(
        queue_dir=queue_dir,
        max_batches=2,
        max_items_per_batch=2,
        pinned_time="2026-05-18T00:00:00+00:00",
        dashboard_out_dir=tmp_path / "dash",
    )
    # Schema doesn't have the runtime-only _report_path field.
    on_disk = dict(report)
    on_disk.pop("_report_path", None)
    jsonschema.validate(on_disk, schema)


def test_empty_queue_stops_early(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    task_queue.init_queue(queue_dir, pinned_time="2026-05-18T00:00:00+00:00")
    # No items enqueued.
    report = autopilot.run_autopilot(
        queue_dir=queue_dir,
        max_batches=24,
        max_items_per_batch=8,
        pinned_time="2026-05-18T00:00:00+00:00",
        dashboard_out_dir=tmp_path / "dash",
    )
    assert report["batches_attempted"] == 1
    assert report["items_completed"] == 0
    assert report["stopped_reason"] == "queue_empty"


def test_report_written_under_queue_dir(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    report = autopilot.run_autopilot(
        queue_dir=queue_dir,
        max_batches=1,
        max_items_per_batch=1,
        pinned_time="2026-05-18T00:00:00+00:00",
        dashboard_out_dir=tmp_path / "dash",
    )
    rp = Path(report["_report_path"])
    assert rp.parent == queue_dir / "reports" / "_autopilot"
    assert rp.name.startswith("TRINITY_TASK_QUEUE_AUTOPILOT_REPORT_")


def test_safety_flags_all_const_true(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    report = autopilot.run_autopilot(
        queue_dir=queue_dir,
        max_batches=1,
        max_items_per_batch=1,
        pinned_time="2026-05-18T00:00:00+00:00",
        dashboard_out_dir=tmp_path / "dash",
    )
    for flag in (
        "no_wallet",
        "no_private_key",
        "no_signing",
        "no_broadcast",
        "no_autonomous_payment",
        "no_network",
        "local_dry_run_only",
    ):
        assert report["safety_flags"][flag] is True, "flag: " + flag


def test_cli_run_autopilot_smoke(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    rc = autopilot.main([
        "run-autopilot",
        "--queue-dir", str(queue_dir),
        "--max-batches", "1",
        "--max-items-per-batch", "1",
        "--pinned-time", "2026-05-18T00:00:00+00:00",
        "--dashboard-out-dir", str(tmp_path / "dash"),
    ])
    assert rc == 0


def test_cli_max_batches_above_cap_returns_2(autopilot, task_queue, tmp_path):
    queue_dir = tmp_path / "q"
    _init_and_enqueue(task_queue, queue_dir, n_items=1)
    rc = autopilot.main([
        "run-autopilot",
        "--queue-dir", str(queue_dir),
        "--max-batches", "25",
        "--max-items-per-batch", "1",
        "--pinned-time", "2026-05-18T00:00:00+00:00",
        "--dashboard-out-dir", str(tmp_path / "dash"),
    ])
    assert rc == 2
