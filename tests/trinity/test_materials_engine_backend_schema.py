"""Schema tests for the Trinity Materials Engine Result v0.1."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "materials_engine_result.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_schema_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-materials-engine-result/v0.1"


def test_schema_const_locks(schema):
    """The four identifier const-fields must stay v0.1-pinned so a
    silent upgrade flips them and fails CI before bytes ship."""
    assert schema["properties"]["schema"]["const"] == (
        "trinity-materials-engine-result/v0.1"
    )
    assert schema["properties"]["backend"]["const"] == "materials_engine"
    assert schema["properties"]["backend_version"]["const"] == "v0.1"
    assert schema["properties"]["mode"]["const"] == "local-dry-run"


def test_schema_task_kind_enum(schema):
    assert set(schema["properties"]["task_kind"]["enum"]) == {
        "comparison", "extraction", "validation", "benchmark",
    }


def test_schema_direction_enum_on_resolved_metrics(schema):
    items = schema["properties"]["resolved_metrics"]["items"]
    assert set(items["properties"]["direction"]["enum"]) == {
        "higher_is_better", "lower_is_better",
    }


def test_schema_score_range(schema):
    score = schema["properties"]["ranking"]["items"]["properties"]["score"]
    assert score["minimum"] == 0.0
    assert score["maximum"] == 1.0


def test_schema_normalised_score_range(schema):
    items = (
        schema["properties"]["ranking"]["items"]
        ["properties"]["metric_breakdown"]["items"]
    )
    ns = items["properties"]["normalised_score"]
    assert ns["minimum"] == 0.0
    assert ns["maximum"] == 1.0


def test_schema_source_request_sha_pattern(schema):
    assert schema["properties"]["source_request_sha256"]["pattern"] == (
        "^[0-9a-f]{64}$"
    )


def test_schema_marker_hex_pattern(schema):
    assert schema["properties"]["marker_hex"]["pattern"] == (
        "^[0-9a-f]{16}$"
    )


def test_schema_classification_id_pattern_or_empty(schema):
    """classification_id is either the standard scl- form OR the
    empty string (the backend falls back to '' if the metadata
    is missing the field)."""
    branches = schema["properties"]["classification_id"]["oneOf"]
    patterns = [b.get("pattern") for b in branches if "pattern" in b]
    assert "^scl-[0-9a-f]{16}$" in patterns


def test_schema_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False


def test_schema_required_set(schema):
    expected = {
        "schema", "backend", "backend_version", "mode", "task_kind",
        "materials_compared", "metrics_requested",
        "known_materials", "unknown_materials", "resolved_metrics",
        "property_table", "ranking", "score_explanation",
        "limitations", "warnings", "source_request_sha256",
        "classification_id", "marker_hex",
        # Sprint 5.34 - Materials Project cache fields.
        "materials_project_cache_used",
        "materials_project_cache_version",
        "materials_project_cache_sha256",
        "materials_project_cache_hits",
        "materials_project_cache_misses",
    }
    assert set(schema["required"]) == expected
