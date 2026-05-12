"""Trinity / Useful Compute reward budget schema — strict v0.1."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_reward_budget.schema.json"
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
def budget_mod():
    return _load(
        "ucrbp_schema",
        SCRIPTS_DIR / "useful_compute_reward_budget_policy.py",
    )


def test_schema_id_is_v01(schema):
    assert schema["$id"] == \
        "trinity-useful-compute-reward-budget/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "budget_id", "mode", "policy",
        "pinned_time", "epoch_id",
        "pool_balance_stocks",
        "effective_daily_budget_stocks",
        "effective_epoch_budget_stocks",
        "policy_caps",
        "total_requested_stocks",
        "total_allocated_stocks",
        "total_deferred_stocks",
        "allocation_items",
        "safety_status",
    }
    assert set(schema["required"]) == expected


def test_safety_status_locks_six_flags(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_broadcast",
        "budget_only", "requires_separate_payment_sprint",
    ):
        assert ss["properties"][k]["const"] is True


def test_allocation_status_enum_complete(schema):
    enum = set(
        schema["properties"]["allocation_items"]["items"]
        ["properties"]["allocation_status"]["enum"]
    )
    expected = {
        "approved_as_requested",
        "capped_by_job", "capped_by_worker",
        "capped_by_daily", "capped_by_epoch",
        "deferred", "rejected",
    }
    assert enum == expected


def test_mode_and_policy_enums_locked(schema):
    assert schema["properties"]["mode"]["enum"] == ["local-dry-run"]
    assert schema["properties"]["policy"]["enum"] == ["conservative"]


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
        if schema.get("type") == "number":
            assert isinstance(obj, (int, float)) and not isinstance(obj, bool)
        if schema.get("type") == "string":
            assert isinstance(obj, str)
        if schema.get("type") == "boolean":
            assert isinstance(obj, bool)


def test_empty_plan_validates(schema, tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir()
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-empty",
    )
    _validate_against_schema(plan, schema)


def test_plan_with_one_item_validates(schema, tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir()
    batch = {
        "schema": "trinity-useful-compute-governance-batch/v0.1",
        "batch_id": "gov-" + "1" * 16,
        "mode": "local-dry-run",
        "reviewer_id": "rev",
        "policy": "conservative",
        "created_at": "2026-05-12T00:00:00+00:00",
        "approved_count": 1, "rejected_count": 0,
        "total_approved_reward_stocks": 2000,
        "approved_items": [{
            "request_id": "uc-" + "a" * 16,
            "validation_id": "val-" + "b" * 16,
            "accepted_compute_output_sha256": "a" * 64,
            "matching_result_ids": ["c" * 16, "d" * 16],
            "unique_workers": 2,
            "approved_pending_reward_stocks": 1000,
            "reason": "test",
        }],
        "rejected_items": [],
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_broadcast": True,
            "no_onchain_registration": True,
            "governance_review_only": True,
            "requires_separate_payment_sprint": True,
        },
    }
    (gov_dir / f"TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_{batch['batch_id']}.json").write_text(
        json.dumps(batch, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    _validate_against_schema(plan, schema)


def test_plan_rejects_extra_fields(schema, tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir()
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    plan["surprise"] = 1
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(plan, schema)
