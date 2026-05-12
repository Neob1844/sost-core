"""Trinity / Useful Compute governance batch schema — strict v0.1."""

from __future__ import annotations

import copy
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
    / "useful_compute_governance_batch.schema.json"
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
def worker_mod():
    return _load(
        "ucw_gov_schema", SCRIPTS_DIR / "useful_compute_worker.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_gov_schema",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def validator_mod():
    return _load(
        "ucrv_gov_schema",
        SCRIPTS_DIR / "useful_compute_replay_validator.py",
    )


@pytest.fixture(scope="module")
def gate_mod():
    return _load(
        "ucgov_schema",
        SCRIPTS_DIR / "useful_compute_governance_gate.py",
    )


def test_schema_id_is_v01(schema):
    assert schema["$id"] == "trinity-useful-compute-governance-batch/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "batch_id", "mode", "reviewer_id", "policy",
        "created_at", "approved_count", "rejected_count",
        "total_approved_reward_stocks", "approved_items",
        "rejected_items", "safety_status",
    }
    assert set(schema["required"]) == expected


def test_safety_status_locks_governance_review_only(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_broadcast",
        "no_onchain_registration",
        "governance_review_only",
        "requires_separate_payment_sprint",
    ):
        assert ss["properties"][k]["const"] is True


def test_policy_enum_only_conservative(schema):
    assert schema["properties"]["policy"]["enum"] == ["conservative"]


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


def _make_request(builder_mod):
    return builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-gov-schema",
        input_bundle_bytes=b"gov-schema-bundle",
        expected_output_schema="dft-result/v0",
        difficulty_class="medium",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="gov schema test",
    )


def test_gate_output_validates_against_schema(
    tmp_path, schema, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "rd"
    vd = tmp_path / "vd"
    rd.mkdir(parents=True); vd.mkdir(parents=True)
    for wid in ("miner-A", "miner-B"):
        worker_mod.run_worker(
            request=copy.deepcopy(req), worker_id=wid,
            out_dir=rd, pinned_time="2026-05-12T00:00:00+00:00",
        )
    validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=vd, min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=vd, rewards_dir=rd,
        out_dir=tmp_path / "out", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    _validate_against_schema(batch, schema)


def test_gate_output_rejects_extra_fields(
    tmp_path, schema, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "rd"
    vd = tmp_path / "vd"
    rd.mkdir(parents=True); vd.mkdir(parents=True)
    for wid in ("miner-A", "miner-B"):
        worker_mod.run_worker(
            request=copy.deepcopy(req), worker_id=wid,
            out_dir=rd, pinned_time="2026-05-12T00:00:00+00:00",
        )
    validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=vd, min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=vd, rewards_dir=rd,
        out_dir=tmp_path / "out", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    batch["sneaky_field"] = "x"
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(batch, schema)
