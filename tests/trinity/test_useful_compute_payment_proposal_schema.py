"""Trinity / Useful Compute payment proposal schema — strict v0.1."""

from __future__ import annotations

import hashlib
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
    / "useful_compute_payment_proposal.schema.json"
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
def proposal_mod():
    return _load(
        "ucpp_schema",
        SCRIPTS_DIR / "useful_compute_payment_proposal.py",
    )


def test_schema_id_is_v01(schema):
    assert schema["$id"] == \
        "trinity-useful-compute-payment-proposal/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "proposal_id", "mode", "pinned_time",
        "source_budget_id",
        "total_payable_stocks",
        "total_deferred_stocks",
        "total_unresolved_stocks",
        "payable_items", "unresolved_items",
        "deferred_items", "rejected_items",
        "capsule_summary", "safety_status",
    }
    assert set(schema["required"]) == expected


def test_safety_status_locks_seven_flags(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "no_private_keys", "no_wallet_access",
        "no_signature", "no_broadcast",
        "proposal_only",
        "requires_manual_signing",
        "requires_separate_broadcast",
    ):
        assert ss["properties"][k]["const"] is True


def test_mode_enum_locked(schema):
    assert schema["properties"]["mode"]["enum"] == ["local-dry-run"]


def test_capsule_summary_template_enum_locked(schema):
    enum = schema["properties"]["capsule_summary"]["properties"][
        "template"]["enum"]
    assert enum == ["useful_compute_reward_batch_v1"]


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


def _make_proposal_input(tmp_path):
    """Write a minimal valid budget + address map + reward so the
    proposal script can produce a v0.1 plan to validate."""
    rid = "uc-" + "a" * 16
    batch_id = "gov-" + "b" * 16
    budget_id = "bud-" + "1" * 16
    wrid = "c" * 16
    worker_id = "miner-alice"

    def sha16(s): return hashlib.sha256(s.encode()).hexdigest()[:16]

    budget = {
        "schema": "trinity-useful-compute-reward-budget/v0.1",
        "budget_id": budget_id, "mode": "local-dry-run",
        "policy": "conservative",
        "pinned_time": "2026-05-12T00:00:00+00:00",
        "epoch_id": "ep-1", "pool_balance_stocks": 1_000_000_000_000,
        "effective_daily_budget_stocks": 100_000_000,
        "effective_epoch_budget_stocks": 1_000_000_000,
        "policy_caps": {
            "max_daily_fraction_of_pool": 0.0001,
            "fixed_daily_cap_stocks": 100_000_000,
            "max_epoch_fraction_of_pool": 0.001,
            "fixed_epoch_cap_stocks": 1_000_000_000,
            "max_job_reward_stocks": 5_000_000,
            "max_worker_reward_stocks": 2_000_000,
            "primary_worker_share": 0.70,
            "replay_validator_share": 0.20,
            "governance_review_reserve": 0.10,
        },
        "total_requested_stocks": 90_000,
        "total_allocated_stocks": 90_000,
        "total_deferred_stocks": 0,
        "allocation_items": [{
            "request_id": rid,
            "governance_batch_id": batch_id,
            "worker_result_ids": [wrid],
            "requested_stocks": 90_000, "allocated_stocks": 90_000,
            "deferred_stocks": 0,
            "primary_workers_share_stocks": 63_000,
            "replay_validator_reserve_stocks": 18_000,
            "governance_review_reserve_stocks": 9_000,
            "cap_reason": "none",
            "allocation_status": "approved_as_requested",
        }],
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_broadcast": True,
            "budget_only": True,
            "requires_separate_payment_sprint": True,
        },
    }
    bpath = tmp_path / "b.json"
    bpath.write_text(
        json.dumps(budget, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    addr_map = {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [{
            "worker_id_hash": sha16(worker_id),
            "payout_address":
                "sost1aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }],
    }
    apath = tmp_path / "a.json"
    apath.write_text(
        json.dumps(addr_map, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )

    rewards = tmp_path / "rewards"
    rewards.mkdir()
    rew = {
        "schema": "trinity-useful-compute-pending-reward/v0.3",
        "request_id": rid, "worker_id": worker_id,
        "worker_result_id": wrid,
        "pending_reward_stocks": 1000, "reason": "ok",
        "requires_manual_review": False,
        "reward_model_schema": "trinity-useful-compute-reward/v0.1",
        "reward_model_deterministic_id": "ff" * 8,
        "backend_name": "placeholder_scoring",
        "backend_version": "v0.1", "backend_kind": "placeholder",
        "benchmark_id": None,
        "normalized_work_score": None,
        "benchmark_source": "none",
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_network_required": True,
            "manual_review_required": True,
        },
    }
    (rewards / (
        f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.json"
    )).write_text(
        json.dumps(rew, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return bpath, apath, rewards


def test_proposal_output_validates_against_schema(
    tmp_path, schema, proposal_mod,
):
    bp, ap, rd = _make_proposal_input(tmp_path)
    plan = proposal_mod.run_payment_proposal(
        budget_path=bp, address_map_path=ap,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rd,
    )
    _validate_against_schema(plan, schema)


def test_proposal_rejects_extra_fields(
    tmp_path, schema, proposal_mod,
):
    bp, ap, rd = _make_proposal_input(tmp_path)
    plan = proposal_mod.run_payment_proposal(
        budget_path=bp, address_map_path=ap,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rd,
    )
    plan["sneaky"] = 1
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(plan, schema)
