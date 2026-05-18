"""Schema tests for the Trinity Task Queue Autopilot Report v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "task_queue_autopilot_report.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_report():
    return {
        "schema": "trinity-task-queue-autopilot-report/v0.1",
        "autopilot_id": "tap-0123456789abcdef",
        "pinned_time": "2026-05-18T00:00:00+00:00",
        "queue_dir_basename": "demo-queue",
        "max_batches": 4,
        "max_items_per_batch": 8,
        "stop_on_failure": False,
        "batches_attempted": 2,
        "batches_succeeded": 2,
        "batches_failed": 0,
        "items_completed": 5,
        "items_failed": 0,
        "final_queue_counts": {
            "pending": 0, "running": 0,
            "completed": 5, "failed": 0, "total": 5,
        },
        "per_batch": [
            {
                "batch_index": 0,
                "batch_id": "tqr-0123456789abcdef",
                "attempted_count": 3,
                "completed_count": 3,
                "failed_count": 0,
                "safety_status": "ok",
            },
            {
                "batch_index": 1,
                "batch_id": "tqr-fedcba9876543210",
                "attempted_count": 2,
                "completed_count": 2,
                "failed_count": 0,
                "safety_status": "ok",
            },
        ],
        "dashboard_paths": [
            "TRINITY_TASK_QUEUE_DASHBOARD_dsh-0123456789abcdef.json",
            "TRINITY_TASK_QUEUE_DASHBOARD_dsh-fedcba9876543210.json",
        ],
        "latest_dashboard_basename":
            "TRINITY_TASK_QUEUE_DASHBOARD_dsh-fedcba9876543210.json",
        "stopped_reason": "queue_empty",
        "safety_status": "ok",
        "warnings": [],
        "safety_flags": {
            "no_wallet": True,
            "no_private_key": True,
            "no_signing": True,
            "no_broadcast": True,
            "no_autonomous_payment": True,
            "no_network": True,
            "local_dry_run_only": True,
        },
    }


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-task-queue-autopilot-report/v0.1"


def test_good_report_validates(schema, good_report):
    jsonschema.validate(good_report, schema)


def test_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    per_batch = schema["properties"]["per_batch"]["items"]
    assert per_batch["additionalProperties"] is False
    fcc = schema["properties"]["final_queue_counts"]
    assert fcc["additionalProperties"] is False
    safety = schema["properties"]["safety_flags"]
    assert safety["additionalProperties"] is False


def test_max_batches_cap(schema):
    assert schema["properties"]["max_batches"]["maximum"] == 24
    assert schema["properties"]["batches_attempted"]["maximum"] == 24


def test_per_batch_capped_at_24(schema):
    assert schema["properties"]["per_batch"]["maxItems"] == 24


def test_safety_flags_all_const_true(schema):
    flags = schema["properties"]["safety_flags"]["properties"]
    for flag in (
        "no_wallet",
        "no_private_key",
        "no_signing",
        "no_broadcast",
        "no_autonomous_payment",
        "no_network",
        "local_dry_run_only",
    ):
        assert flags[flag]["const"] is True, "flag " + flag


def test_max_batches_above_24_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["max_batches"] = 25
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_per_batch_25_entries_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    item = bad["per_batch"][0]
    bad["per_batch"] = [
        dict(item, batch_index=i) for i in range(25)
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_safety_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_status"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_stopped_reason_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["stopped_reason"] = "operator_decided_to_quit"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_safety_flag_flipped_false_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"]["no_broadcast"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_autopilot_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["autopilot_id"] = "tap-XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_extra_top_level_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["extra_field"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
