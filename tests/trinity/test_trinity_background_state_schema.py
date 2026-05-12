"""Trinity background daemon state schema — strict v0.1."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
OBJECTIVES_DIR = REPO_ROOT / "config" / "trinity" / "objectives"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "trinity_background_state.schema.json"
)


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def daemon_mod():
    return _load(
        "trinity_bg_schema",
        SCRIPTS_DIR / "trinity_background_daemon.py",
    )


def test_schema_id_is_v01(schema):
    assert schema["$id"] == "trinity-background-daemon-state/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "mode", "workspace", "cycle_index",
        "started_at", "last_cycle_at",
        "requests_seen", "results_seen",
        "validations_seen", "governance_batches_seen",
        "pending_requests", "accepted_validations",
        "approved_batches", "errors_count", "lessons_count",
        "safety_status",
    }
    assert set(schema["required"]) == expected


def test_safety_status_locks_eight_flags(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "local_dry_run_only",
        "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_broadcast",
        "no_network_required", "no_consensus_changes",
        "human_review_required_before_payment",
    ):
        assert ss["properties"][k]["const"] is True


def test_mode_enum_only_local_dry_run(schema):
    assert schema["properties"]["mode"]["enum"] == ["local-dry-run"]


def _validate_against_schema(obj, schema):
    if schema.get("type") == "object":
        if not isinstance(obj, dict):
            raise AssertionError("not an object")
        required = set(schema.get("required", []))
        missing = required - set(obj.keys())
        if missing:
            raise AssertionError(f"missing fields: {sorted(missing)}")
        if schema.get("additionalProperties") is False:
            allowed = set(schema["properties"].keys())
            extra = set(obj.keys()) - allowed
            if extra:
                raise AssertionError(f"extra fields: {sorted(extra)}")
        for k, sub in schema["properties"].items():
            if k in obj:
                _validate_against_schema(obj[k], sub)
    elif schema.get("type") == "array":
        for item in obj:
            _validate_against_schema(item, schema.get("items", {}))
    else:
        if "const" in schema:
            assert obj == schema["const"]
        if "enum" in schema:
            assert obj in schema["enum"]
        if "pattern" in schema:
            assert isinstance(obj, str)
            assert re.match(schema["pattern"], obj)
        if schema.get("type") == "integer":
            assert isinstance(obj, int) and not isinstance(obj, bool)
        if schema.get("type") == "string":
            assert isinstance(obj, str)
        if schema.get("type") == "boolean":
            assert isinstance(obj, bool)


def test_state_validates_against_schema(tmp_path, schema, daemon_mod):
    state = daemon_mod.run_cycle(
        workspace=tmp_path / "ws",
        objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id=None, reviewer_id=None,
    )
    _validate_against_schema(state, schema)


def test_state_rejects_extra_fields(tmp_path, schema, daemon_mod):
    state = daemon_mod.run_cycle(
        workspace=tmp_path / "ws",
        objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id=None, reviewer_id=None,
    )
    state["sneaky_field"] = "x"
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(state, schema)


def test_state_rejects_safety_false(tmp_path, schema, daemon_mod):
    state = daemon_mod.run_cycle(
        workspace=tmp_path / "ws",
        objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id=None, reviewer_id=None,
    )
    state["safety_status"]["no_automatic_payout"] = False
    with pytest.raises(AssertionError):
        _validate_against_schema(state, schema)
