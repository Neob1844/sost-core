"""Schema tests for the Trinity Autonomy Governor v0.1 (Sprint 5.23).

Validates:
  - the example policy matches the policy JSON schema
  - decisions emitted by the script validate against the decision schema
  - both schemas declare the v0.1 string id, the mode enum, the
    required allowed/blocked fields, and the 64-hex policy_sha256 patterns
  - threat_refs is an array of T## strings
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_SCHEMA = REPO_ROOT / "schemas" / "trinity" / "autonomy_governor_policy.schema.json"
DECISION_SCHEMA = REPO_ROOT / "schemas" / "trinity" / "autonomy_governor_decision.schema.json"
EXAMPLE_POLICY = REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(p: Path):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def gov():
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        import autonomy_governor  # type: ignore
        yield autonomy_governor
    finally:
        try:
            sys.path.remove(str(SCRIPTS_DIR))
        except ValueError:
            pass


# ---------------------------------------------------------------------------
# Policy schema
# ---------------------------------------------------------------------------

def test_policy_schema_loads_as_valid_json():
    schema = _load(POLICY_SCHEMA)
    # Must self-validate against the draft we chose (draft-07).
    jsonschema.Draft7Validator.check_schema(schema)


def test_policy_schema_declares_v01_id():
    schema = _load(POLICY_SCHEMA)
    # The schema's $id MUST carry the same versioned identifier the
    # code expects so a future v0.2 cannot be silently swapped in.
    assert schema.get("$id") == "trinity-autonomy-governor-policy/v0.1"


def test_policy_schema_has_mode_enum_with_three_values():
    schema = _load(POLICY_SCHEMA)
    mode_def = schema["properties"]["mode"]
    assert mode_def["type"] == "string"
    assert set(mode_def["enum"]) == {"observe", "propose", "execute_bounded"}


def test_policy_schema_requires_all_top_level_keys():
    schema = _load(POLICY_SCHEMA)
    required = set(schema["required"])
    for key in ("schema", "version", "mode", "caps_per_day", "caps_per_hour",
                "allowlists", "require_human_approval", "kill_switch", "audit"):
        assert key in required, "policy schema missing required key: " + key


def test_example_policy_validates_against_policy_schema():
    schema = _load(POLICY_SCHEMA)
    policy = _load(EXAMPLE_POLICY)
    jsonschema.validate(policy, schema)


def test_policy_schema_forbids_nonzero_autonomous_sost_stocks():
    schema = _load(POLICY_SCHEMA)
    policy = _load(EXAMPLE_POLICY)
    policy["caps_per_day"]["autonomous_sost_stocks"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(policy, schema)


def test_policy_schema_rejects_unknown_mode():
    schema = _load(POLICY_SCHEMA)
    policy = _load(EXAMPLE_POLICY)
    policy["mode"] = "yolo"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(policy, schema)


# ---------------------------------------------------------------------------
# Decision schema
# ---------------------------------------------------------------------------

def test_decision_schema_loads_as_valid_json():
    schema = _load(DECISION_SCHEMA)
    jsonschema.Draft7Validator.check_schema(schema)


def test_decision_schema_declares_v01_id():
    schema = _load(DECISION_SCHEMA)
    assert schema.get("$id") == "trinity-autonomy-governor-decision/v0.1"


def test_decision_schema_requires_allowed_and_blocked_reason():
    schema = _load(DECISION_SCHEMA)
    required = set(schema["required"])
    assert "allowed" in required
    assert "blocked_reason" in required


def test_decision_schema_policy_sha_patterns_are_64hex():
    schema = _load(DECISION_SCHEMA)
    for key in ("policy_sha256", "policy_runtime_sha256"):
        prop = schema["properties"][key]
        assert prop["type"] == "string"
        assert prop["pattern"] == "^[a-f0-9]{64}$", (
            "schema for " + key + " must require 64 lowercase hex chars"
        )


def test_decision_schema_threat_refs_is_array_of_T_pattern():
    schema = _load(DECISION_SCHEMA)
    refs = schema["properties"]["threat_refs"]
    assert refs["type"] == "array"
    assert refs["items"]["pattern"] == "^T[0-9]{2}$"


def test_decision_output_validates(gov, tmp_path):
    """End-to-end: run the script's decide() and validate the JSON
    against the decision schema."""
    schema = _load(DECISION_SCHEMA)
    p = tmp_path / "policy.json"
    p.write_text(EXAMPLE_POLICY.read_text(encoding="utf-8"), encoding="utf-8")
    boot = gov._sha256_file(p)
    with open(p, "r", encoding="utf-8") as f:
        policy = json.load(f)
    d = gov.decide(
        policy=policy,
        policy_path=p,
        boot_policy_sha256=boot,
        action="create_request",
        action_params={"source_tool": "trinity_scientific_prompt_intake"},
        pinned_time="2026-05-16T00:00:00+00:00",
    )
    jsonschema.validate(d, schema)


def test_blocked_decision_also_validates(gov, tmp_path):
    """A decision with allowed=false (blocked_reason set) must still
    validate against the schema."""
    schema = _load(DECISION_SCHEMA)
    p = tmp_path / "policy.json"
    p.write_text(EXAMPLE_POLICY.read_text(encoding="utf-8"), encoding="utf-8")
    boot = gov._sha256_file(p)
    with open(p, "r", encoding="utf-8") as f:
        policy = json.load(f)
    d = gov.decide(
        policy=policy,
        policy_path=p,
        boot_policy_sha256=boot,
        action="broadcast_signed_transaction",
        action_params={},
        pinned_time="2026-05-16T00:00:00+00:00",
    )
    assert d["allowed"] is False
    jsonschema.validate(d, schema)


# ---------------------------------------------------------------------------
# Sprint 5.24 — pipeline_step action coverage in the schema layer
# ---------------------------------------------------------------------------

def test_pipeline_step_decision_validates(gov, tmp_path):
    """The decision schema accepts the action='pipeline_step' decision
    emitted by the operator_loop observe hook."""
    schema = _load(DECISION_SCHEMA)
    p = tmp_path / "policy.json"
    p.write_text(EXAMPLE_POLICY.read_text(encoding="utf-8"), encoding="utf-8")
    boot = gov._sha256_file(p)
    with open(p, "r", encoding="utf-8") as f:
        policy = json.load(f)
    d = gov.decide(
        policy=policy,
        policy_path=p,
        boot_policy_sha256=boot,
        action="pipeline_step",
        action_params={"step_name": "task_builder"},
        pinned_time="2026-05-16T00:00:00+00:00",
    )
    assert d["action"] == "pipeline_step"
    assert d["threat_refs"] == ["T15", "T16", "T17"]
    jsonschema.validate(d, schema)


def test_pipeline_step_present_in_known_actions(gov):
    """Belt-and-braces: the in-code KNOWN_ACTIONS tuple includes
    pipeline_step. If a refactor drops it, this test catches it."""
    assert "pipeline_step" in gov.KNOWN_ACTIONS


def test_pipeline_step_threats_align_with_security_md(gov):
    """T15/T16/T17 are the SECURITY.md entries that cover log/proof
    tampering, governance bypass and budget cap bypass — the three
    things a per-step audit hook is designed to surface."""
    refs = gov.THREAT_REFS["pipeline_step"]
    assert set(refs) == {"T15", "T16", "T17"}
