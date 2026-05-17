"""Schema tests for the Trinity Task Queue v0.1.

Validates:
  - the queue schema is a valid draft-07 schema with the v0.1 $id
  - the queue.json shape (with the inlined queue_item_index)
  - the queue_item shape exposed via $defs/queue_item
  - the status enum
  - the queue_item_id / queue_id / sha256 / threat_refs patterns
  - the queue runner produces files that validate against the schema
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
    REPO_ROOT / "schemas" / "trinity" / "task_queue.schema.json"
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
def item_schema(schema):
    return schema["$defs"]["queue_item"]


@pytest.fixture(scope="module")
def tq():
    return _load("task_queue_sch", SCRIPTS_DIR / "task_queue.py")


# ---------------------------------------------------------------------------
# Schema self-consistency
# ---------------------------------------------------------------------------


def test_queue_schema_loads_as_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_queue_schema_declares_v01_id(schema):
    assert schema.get("$id") == "trinity-task-queue/v0.1"


def test_queue_schema_status_enum_has_four_values(schema):
    enum = schema["properties"]["items"]["items"]["properties"]["status"]["enum"]
    assert set(enum) == {"pending", "running", "completed", "failed"}


def test_queue_item_schema_status_enum_matches(schema, item_schema):
    assert set(item_schema["properties"]["status"]["enum"]) == {
        "pending", "running", "completed", "failed",
    }


def test_queue_item_schema_locks_schema_const(item_schema):
    assert item_schema["properties"]["schema"]["const"] == (
        "trinity-task-queue-item/v0.1"
    )


def test_queue_item_id_pattern(item_schema):
    assert item_schema["properties"]["queue_item_id"]["pattern"] == (
        "^qit-[0-9a-f]{16}$"
    )


def test_queue_id_pattern(schema):
    assert schema["properties"]["queue_id"]["pattern"] == (
        "^tq-[0-9a-f]{16}$"
    )


def test_queue_item_sha256_patterns(item_schema):
    for key in ("policy_sha256", "request_sha256"):
        assert item_schema["properties"][key]["pattern"] == "^[0-9a-f]{64}$"


def test_queue_item_threat_refs_pattern(item_schema):
    refs = item_schema["properties"]["threat_refs"]
    assert refs["type"] == "array"
    assert refs["items"]["pattern"] == "^T[0-9]{2}$"


def test_queue_item_watchdog_status_enum(item_schema):
    wd = item_schema["properties"]["watchdog_safety_status"]
    # oneOf [string-enum, null]
    string_branch = next(
        b for b in wd["oneOf"] if b.get("type") == "string"
    )
    assert set(string_branch["enum"]) == {
        "ok", "warning", "stale", "critical",
    }


def test_queue_item_max_attempts_is_bounded(item_schema):
    ma = item_schema["properties"]["max_attempts"]
    assert ma["minimum"] == 1
    assert ma["maximum"] == 16


# ---------------------------------------------------------------------------
# End-to-end: real queue runner produces schema-valid files
# ---------------------------------------------------------------------------


def test_queue_json_validates_after_init(tmp_path, tq, schema):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    obj = json.loads((qd / "queue.json").read_text(encoding="utf-8"))
    jsonschema.validate(obj, schema)


def test_queue_item_validates_after_enqueue(tmp_path, tq, item_schema):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    item = tq.enqueue_item(
        queue_dir=qd,
        request_json=REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    p = qd / "pending" / (item["queue_item_id"] + ".json")
    obj = json.loads(p.read_text(encoding="utf-8"))
    jsonschema.validate(obj, item_schema)


def test_completed_item_after_run_once_validates(tmp_path, tq, item_schema):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    tq.enqueue_item(
        queue_dir=qd,
        request_json=REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    res = tq.run_once(qd)
    assert res["status"] == "completed", (
        "last_error: " + str(res.get("last_error"))
    )
    p = qd / "completed" / (res["queue_item_id"] + ".json")
    obj = json.loads(p.read_text(encoding="utf-8"))
    jsonschema.validate(obj, item_schema)
    # The completed item carries the audit fields populated.
    assert obj["governor_decisions_count"] == 7
    assert obj["watchdog_safety_status"] == "ok"
    assert obj["operator_run_path"] is not None
    assert obj["watchdog_report_path"] is not None
