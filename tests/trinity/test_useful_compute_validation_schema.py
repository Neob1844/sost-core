"""Trinity / Useful Compute validation schema — strict v0.1."""

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
    / "useful_compute_validation.schema.json"
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
        "ucw_val_schema", SCRIPTS_DIR / "useful_compute_worker.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_val_schema",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def validator_mod():
    return _load(
        "ucrv_schema",
        SCRIPTS_DIR / "useful_compute_replay_validator.py",
    )


def test_schema_id_is_v02(schema):
    assert schema["$id"] == "trinity-useful-compute-validation/v0.2"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "validation_id", "request_id", "mode",
        "min_workers", "workers_seen", "unique_workers",
        "accepted_compute_output_sha256",
        "accepted_backend_name", "accepted_backend_version",
        "validation_status",
        "matching_result_ids", "rejected_result_ids",
        "mismatch_groups", "manual_review_required",
        "safety_status",
    }
    assert set(schema["required"]) == expected


def test_safety_locks_governance_required(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_network_required",
        "no_onchain_registration",
        "governance_required_before_payment",
    ):
        assert ss["properties"][k]["const"] is True


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
            assert obj == schema["const"], (
                f"value {obj!r} != const {schema['const']!r}"
            )
        if "enum" in schema:
            assert obj in schema["enum"], (
                f"value {obj!r} not in enum {schema['enum']}"
            )
        if "pattern" in schema:
            assert isinstance(obj, str)
            assert re.match(schema["pattern"], obj), (
                f"value {obj!r} fails pattern {schema['pattern']!r}"
            )
        if "oneOf" in schema:
            ok = False
            for sub in schema["oneOf"]:
                try:
                    _validate_against_schema(obj, sub)
                    ok = True
                    break
                except AssertionError:
                    continue
            assert ok, f"oneOf failed for value {obj!r}"
        if schema.get("type") == "integer":
            assert isinstance(obj, int) and not isinstance(obj, bool)
        if schema.get("type") == "string":
            assert isinstance(obj, str)
        if schema.get("type") == "boolean":
            assert isinstance(obj, bool)


def _make_request(builder_mod):
    return builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-schema",
        input_bundle_bytes=b"schema-bundle",
        expected_output_schema="dft-result/v0",
        difficulty_class="high",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="schema val test",
    )


def test_validator_output_satisfies_schema(
    tmp_path, schema, worker_mod, builder_mod, validator_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "rd"
    rd.mkdir(parents=True)
    import copy
    for wid in ("miner-A", "miner-B"):
        worker_mod.run_worker(
            request=copy.deepcopy(req), worker_id=wid,
            out_dir=rd, pinned_time="2026-05-12T00:00:00+00:00",
        )
    rep = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    _validate_against_schema(rep, schema)


def test_validator_output_rejects_extra_fields(
    tmp_path, schema, worker_mod, builder_mod, validator_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "rd"
    rd.mkdir(parents=True)
    import copy
    for wid in ("miner-A", "miner-B"):
        worker_mod.run_worker(
            request=copy.deepcopy(req), worker_id=wid,
            out_dir=rd, pinned_time="2026-05-12T00:00:00+00:00",
        )
    rep = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    rep["surprise_field"] = 1
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(rep, schema)


def test_validation_status_enum_complete(schema):
    statuses = set(
        schema["properties"]["validation_status"]["enum"]
    )
    expected = {
        "accepted", "rejected", "insufficient_workers",
        "mismatch", "manual_review",
    }
    assert statuses == expected
