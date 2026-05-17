"""Schema tests for the Trinity Task Queue Dashboard v0.1.

Validates:
  - the dashboard schema is a valid draft-07 schema with v0.1 $id
  - the counts object exposes every status + batches
  - the safety_status enum has exactly {ok, warning, failed}
  - the latest_items and latest_batches arrays have the right
    item shape (sha-pattern ids, status enum, watchdog enum)
  - reports produced by scripts/trinity/task_queue_dashboard.py
    validate in every documented safety_status branch
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "task_queue_dashboard.schema.json"
)
FIXTURES = REPO_ROOT / "tests" / "trinity" / "fixtures" / "useful_compute"
REQUEST_FIXTURE = FIXTURES / "request_scientific_intake.json"
ADDRESS_MAP_FIXTURE = FIXTURES / "address_map.json"
EXAMPLE_POLICY = REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"
PINNED = "2026-05-17T00:00:00+00:00"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def tq():
    return _load("task_queue_dsh_sch", SCRIPTS_DIR / "task_queue.py")


@pytest.fixture(scope="module")
def dash():
    return _load(
        "task_queue_dashboard_dsh_sch",
        SCRIPTS_DIR / "task_queue_dashboard.py",
    )


# ---------------------------------------------------------------------------
# Schema self-consistency
# ---------------------------------------------------------------------------


def test_dashboard_schema_loads_as_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_dashboard_schema_declares_v01_id(schema):
    assert schema.get("$id") == "trinity-task-queue-dashboard/v0.1"


def test_dashboard_schema_safety_status_enum(schema):
    enum = schema["properties"]["safety_status"]["enum"]
    assert set(enum) == {"ok", "warning", "failed"}


def test_dashboard_schema_counts_required_keys(schema):
    counts = schema["properties"]["counts"]
    assert set(counts["required"]) == {
        "pending", "running", "completed", "failed", "batches",
    }


def test_dashboard_schema_dashboard_id_pattern(schema):
    assert schema["properties"]["dashboard_id"]["pattern"] == (
        "^dsh-[0-9a-f]{16}$"
    )


def test_dashboard_schema_queue_id_pattern(schema):
    assert schema["properties"]["queue_id"]["pattern"] == (
        "^tq-[0-9a-f]{16}$"
    )


def test_dashboard_schema_item_id_pattern(schema):
    item = schema["properties"]["latest_items"]["items"]
    assert item["properties"]["queue_item_id"]["pattern"] == (
        "^qit-[0-9a-f]{16}$"
    )


def test_dashboard_schema_batch_id_pattern(schema):
    item = schema["properties"]["latest_batches"]["items"]
    assert item["properties"]["batch_id"]["pattern"] == (
        "^tqr-[0-9a-f]{16}$"
    )


def test_dashboard_schema_status_enum_on_items(schema):
    item = schema["properties"]["latest_items"]["items"]
    assert set(item["properties"]["status"]["enum"]) == {
        "pending", "running", "completed", "failed",
    }


def test_dashboard_schema_watchdog_status_enum_on_items(schema):
    item = schema["properties"]["latest_items"]["items"]
    wd = item["properties"]["watchdog_safety_status"]
    string_branch = next(
        b for b in wd["oneOf"] if b.get("type") == "string"
    )
    assert set(string_branch["enum"]) == {
        "ok", "warning", "stale", "critical",
    }


def test_dashboard_schema_batch_safety_status_enum(schema):
    item = schema["properties"]["latest_batches"]["items"]
    assert set(item["properties"]["safety_status"]["enum"]) == {
        "ok", "warning", "failed",
    }


# ---------------------------------------------------------------------------
# End-to-end: real dashboards validate in every safety branch
# ---------------------------------------------------------------------------


def _enqueue(tq, qd, pinned):
    return tq.enqueue_item(
        queue_dir=qd, request_json=REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=pinned,
    )


def test_empty_dashboard_validates(tmp_path, tq, dash, schema):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    jsonschema.validate(d, schema)
    assert d["safety_status"] == "ok"


def test_ok_dashboard_validates(tmp_path, tq, dash, schema):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    _enqueue(tq, qd, PINNED)
    tq.run_batch(queue_dir=qd, max_items=1, pinned_time=PINNED)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    jsonschema.validate(d, schema)
    assert d["safety_status"] == "ok"


def test_warning_dashboard_validates_on_failed_item(
    tmp_path, tq, dash, schema,
):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    bad = tmp_path / "bad.json"
    bad.write_bytes(REQUEST_FIXTURE.read_bytes())
    tq.enqueue_item(
        queue_dir=qd, request_json=bad,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    bad.unlink()
    tq.run_batch(queue_dir=qd, max_items=1, pinned_time=PINNED)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    jsonschema.validate(d, schema)
    assert d["safety_status"] == "warning"


def test_dashboard_with_two_items_one_batch_validates(
    tmp_path, tq, dash, schema,
):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    _enqueue(tq, qd, "2026-05-17T00:00:00+00:00")
    _enqueue(tq, qd, "2026-05-17T01:00:00+00:00")
    tq.run_batch(queue_dir=qd, max_items=2, pinned_time=PINNED)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    jsonschema.validate(d, schema)
    assert d["counts"] == {
        "pending": 0, "running": 0, "completed": 2,
        "failed": 0, "batches": 1,
    }
