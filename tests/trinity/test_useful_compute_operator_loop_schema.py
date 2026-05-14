"""Trinity / Useful Compute operator-run schema — strict v0.1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_operator_run.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_schema_id_is_v01(schema):
    assert schema["$id"] == \
        "trinity-useful-compute-operator-run/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "operator_run_id", "mode", "pinned_time",
        "git_head", "max_total_stocks", "pool_balance_stocks",
        "allow_wallet_access", "allow_broadcast",
        "human_review_required",
        "request_source",
        "source_request_sha256",
        "source_request_path_basename",
        "steps_completed", "artifacts", "warnings",
    }
    assert set(schema["required"]) == expected


def test_request_source_enum_locked(schema):
    enum = schema["properties"]["request_source"]["enum"]
    assert set(enum) == {"built", "existing_request"}


def test_source_request_sha256_oneof_string_or_null(schema):
    one_of = schema["properties"]["source_request_sha256"]["oneOf"]
    assert any(
        s.get("pattern") == "^[0-9a-f]{64}$" for s in one_of
    )
    assert any(s.get("type") == "null" for s in one_of)


def test_source_request_basename_oneof_string_or_null(schema):
    one_of = schema["properties"][
        "source_request_path_basename"
    ]["oneOf"]
    assert any(
        s.get("type") == "string" and s.get("minLength") == 1
        and s.get("maxLength") == 256
        for s in one_of
    )
    assert any(s.get("type") == "null" for s in one_of)


def test_safety_const_flags_locked(schema):
    p = schema["properties"]
    assert p["allow_wallet_access"]["const"] is False
    assert p["allow_broadcast"]["const"] is False
    assert p["human_review_required"]["const"] is True


def test_mode_enum_locked(schema):
    assert schema["properties"]["mode"]["enum"] == ["local-dry-run"]


def test_steps_completed_enum(schema):
    items = schema["properties"]["steps_completed"]["items"]
    assert set(items["enum"]) == {
        "task_builder", "worker", "replay_validator",
        "governance_gate", "reward_budget_policy",
        "payment_proposal", "payment_draft",
    }


def test_operator_run_id_pattern(schema):
    p = schema["properties"]["operator_run_id"]
    assert p["pattern"] == "^oprun-[0-9a-f]{16}$"


def test_artifacts_object_only_allows_known_steps(schema):
    art = schema["properties"]["artifacts"]
    assert art["additionalProperties"] is False
    assert set(art["properties"].keys()) == {
        "task_builder", "worker", "replay_validator",
        "governance_gate", "reward_budget_policy",
        "payment_proposal", "payment_draft",
    }


def test_artifact_entry_shape(schema):
    entry = schema["$defs"]["artifact_entry"]
    assert entry["additionalProperties"] is False
    assert set(entry["required"]) == {"path", "sha256"}
    assert entry["properties"]["sha256"]["pattern"] == \
        "^[0-9a-f]{64}$"
