"""Schema tests for the Trinity Scientific Task Classification v0.1."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "scientific_task_classification.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_declares_v01_id(schema):
    assert schema.get("$id") == (
        "trinity-scientific-task-classification/v0.1"
    )


def test_schema_classification_id_pattern(schema):
    assert schema["properties"]["classification_id"]["pattern"] == (
        "^scl-[0-9a-f]{16}$"
    )


def test_schema_source_intake_id_pattern(schema):
    assert schema["properties"]["source_intake_id"]["pattern"] == (
        "^spi-[0-9a-f]{16}$"
    )


def test_schema_task_kind_enum(schema):
    assert set(schema["properties"]["task_kind"]["enum"]) == {
        "comparison", "extraction", "validation", "benchmark",
    }


def test_schema_confidence_enum(schema):
    assert set(schema["properties"]["confidence"]["enum"]) == {
        "low", "medium", "high",
    }


def test_schema_proposed_source_tool_enum(schema):
    assert set(
        schema["properties"]["proposed_source_tool"]["enum"]
    ) == {"materials_engine", "trinity_scientific_prompt_intake"}


def test_schema_difficulty_enum(schema):
    assert set(
        schema["properties"]["proposed_difficulty_class"]["enum"]
    ) == {"low", "medium", "high", "extreme"}


def test_schema_threat_refs_pattern(schema):
    assert schema["properties"]["threat_refs"]["items"]["pattern"] == (
        "^T[0-9]{2}$"
    )


def test_schema_evidence_item_size_capped(schema):
    item = schema["properties"]["evidence"]["items"]
    assert item["maxLength"] == 256


def test_schema_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False


def test_schema_required_set(schema):
    required = set(schema["required"])
    expected = {
        "schema", "classification_id", "source_intake_id",
        "source_intake_sha256", "combined_context_sha256",
        "documents_count", "reader_kind_counts",
        "reader_status_counts", "task_kind", "confidence",
        "candidate_materials", "candidate_metrics",
        "proposed_source_tool", "proposed_difficulty_class",
        "expected_output_schema", "public_description",
        "warnings", "evidence", "threat_refs", "pinned_time",
    }
    assert required == expected
