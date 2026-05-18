"""Schema tests for the Trinity Daily Report v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity" / "daily_report.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_report():
    return {
        "schema": "trinity-daily-report/v0.1",
        "report_id": "tdr-0123456789abcdef",
        "pinned_time": "2026-05-18T00:00:00+00:00",
        "source_dashboard_basename":
            "TRINITY_TASK_QUEUE_DASHBOARD_dsh-0123456789abcdef.json",
        "queue_dir_basename": "demo-queue",
        "source_dashboard_id": "dsh-0123456789abcdef",
        "counts": {
            "pending": 0, "running": 0,
            "completed": 2, "failed": 0, "batches": 1,
        },
        "completed_items": [
            {
                "queue_item_id": "qit-aaaa111122223333",
                "top_material": "PrOx",
                "materials_engine_known_count": 2,
                "materials_engine_unknown_count": 0,
                "materials_project_cache_hits": 2,
                "materials_project_cache_misses": 0,
                "workers_seen": 2,
            },
            {
                "queue_item_id": "qit-bbbb222233334444",
                "top_material": "CeO2",
                "materials_engine_known_count": 2,
                "materials_engine_unknown_count": 0,
                "materials_project_cache_hits": 2,
                "materials_project_cache_misses": 0,
                "workers_seen": 2,
            },
        ],
        "failed_items": [],
        "top_materials": ["CeO2", "PrOx"],
        "cache_hits_total": 4,
        "cache_misses_total": 0,
        "workers_seen_total": 4,
        "worker_ids": ["worker-A", "worker-B"],
        "warnings": [],
        "drafts_proposals_count": 0,
        "drafts_proposals_basenames": [],
        "safety_status": "ok",
        "safety_flags": {
            "no_wallet": True,
            "no_private_key": True,
            "no_signing": True,
            "no_broadcast": True,
            "no_autonomous_payment": True,
            "no_network": True,
        },
        "latest_batches_count": 1,
    }


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-daily-report/v0.1"


def test_good_report_validates(schema, good_report):
    jsonschema.validate(good_report, schema)


def test_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    for sub in (
        "counts",
        "safety_flags",
    ):
        assert schema["properties"][sub]["additionalProperties"] is False
    ci = schema["properties"]["completed_items"]["items"]
    assert ci["additionalProperties"] is False
    fi = schema["properties"]["failed_items"]["items"]
    assert fi["additionalProperties"] is False


def test_report_id_pattern(schema):
    assert schema["properties"]["report_id"]["pattern"] == (
        "^tdr-[0-9a-f]{16}$"
    )


def test_safety_flags_all_const_true(schema):
    flags = schema["properties"]["safety_flags"]["properties"]
    for flag in (
        "no_wallet",
        "no_private_key",
        "no_signing",
        "no_broadcast",
        "no_autonomous_payment",
        "no_network",
    ):
        assert flags[flag]["const"] is True, "flag " + flag


def test_safety_status_enum(schema):
    assert sorted(schema["properties"]["safety_status"]["enum"]) == [
        "failed", "ok", "warning",
    ]


def test_completed_items_max_50(schema):
    assert schema["properties"]["completed_items"]["maxItems"] == 50


def test_failed_items_max_50(schema):
    assert schema["properties"]["failed_items"]["maxItems"] == 50


def test_extra_top_level_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["extra"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_safety_flag_flipped_false_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"]["no_broadcast"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_report_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["report_id"] = "tdr-XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_safety_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_status"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_watchdog_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["failed_items"] = [{
        "queue_item_id": "qit-aaaa111122223333",
        "watchdog_safety_status": "panic",
    }]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
