"""Trinity / Useful Compute result schema — strict v0.1 invariants."""

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
    / "useful_compute_result.schema.json"
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
    return _load("ucw_schema", SCRIPTS_DIR / "useful_compute_worker.py")


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_schema",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


def test_schema_id_is_v02(schema):
    assert schema["$id"] == "trinity-useful-compute-result/v0.2"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "request_id", "worker_id", "task_type",
        "input_bundle_sha256",
        "compute_output_sha256", "worker_result_id",
        "started_at", "finished_at", "elapsed_seconds",
        "result_validated", "duplicate_result",
        "public_summary", "safety_status",
    }
    assert set(schema["required"]) == expected


def test_safety_status_subschema_locks_all_flags_true(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in ("no_wallet_access", "no_private_keys",
              "no_automatic_payout", "no_network_required",
              "manual_review_required"):
        assert ss["properties"][k]["const"] is True


def _validate_against_schema(obj, schema):
    """Tiny validator: required keys, no extras, enums, regex
    patterns, type constraints. Enough to enforce the v0.1 contract
    without adding a jsonschema dependency."""
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
        if schema.get("type") == "integer":
            assert isinstance(obj, int) and not isinstance(obj, bool)
        if schema.get("type") == "number":
            assert isinstance(obj, (int, float)) and not isinstance(obj, bool)
        if schema.get("type") == "string":
            assert isinstance(obj, str)
        if schema.get("type") == "boolean":
            assert isinstance(obj, bool)


def _make_request(builder_mod):
    return builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-schema-1",
        input_bundle_bytes=b"some-bundle",
        expected_output_schema="dft-result/v0",
        difficulty_class="high",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="schema test request",
    )


def test_worker_output_validates_against_result_schema(
    tmp_path, schema, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    res, _ = worker_mod.run_worker(
        request=req, worker_id="miner-schema-1",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    _validate_against_schema(res, schema)


def test_result_rejects_unknown_fields(schema, worker_mod, builder_mod,
                                       tmp_path):
    req = _make_request(builder_mod)
    res, _ = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    res["bogus_field"] = 1
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(res, schema)


def test_result_rejects_safety_false(schema, worker_mod, builder_mod,
                                     tmp_path):
    req = _make_request(builder_mod)
    res, _ = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    res["safety_status"]["no_automatic_payout"] = False
    with pytest.raises(AssertionError):
        _validate_against_schema(res, schema)
