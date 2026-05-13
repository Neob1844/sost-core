"""Trinity scientific prompt intake schema — strict v0.1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "scientific_prompt_intake.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_id_is_v01(schema):
    assert schema["$id"] == \
        "trinity-scientific-prompt-intake/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "intake_id", "mode", "pinned_time",
        "prompt_sha256", "prompt_preview",
        "documents_count", "documents",
        "combined_context_sha256",
        "safety_status", "warnings",
    }
    assert set(schema["required"]) == expected


def test_safety_status_all_const_true(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    expected_keys = {
        "local_only", "no_network", "no_llm_call",
        "no_wallet_access", "no_broadcast", "no_private_keys",
        "deterministic_output",
    }
    assert set(ss["required"]) == expected_keys
    for k in expected_keys:
        assert ss["properties"][k]["const"] is True, (
            f"safety_status.{k} must be const-true"
        )


def test_intake_id_pattern(schema):
    assert schema["properties"]["intake_id"]["pattern"] == \
        "^spi-[0-9a-f]{16}$"


def test_mode_enum_locked(schema):
    assert schema["properties"]["mode"]["enum"] == [
        "local-dry-run",
    ]


def test_sha256_field_patterns(schema):
    for field in ("prompt_sha256", "combined_context_sha256"):
        assert schema["properties"][field]["pattern"] == \
            "^[0-9a-f]{64}$"


def test_documents_item_shape(schema):
    items = schema["properties"]["documents"]["items"]
    assert items["additionalProperties"] is False
    assert set(items["required"]) == {
        "path_basename", "sha256", "bytes", "text_preview",
    }
    assert items["properties"]["sha256"]["pattern"] == \
        "^[0-9a-f]{64}$"
    assert items["properties"]["bytes"]["minimum"] == 0


def test_previews_have_size_caps(schema):
    """Prompt preview and per-document preview are both capped at
    1024 chars to keep audit artifacts small."""
    assert schema["properties"]["prompt_preview"]["maxLength"] == 1024
    items = schema["properties"]["documents"]["items"]
    assert items["properties"]["text_preview"]["maxLength"] == 1024
