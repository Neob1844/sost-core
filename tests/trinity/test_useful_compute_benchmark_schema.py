"""Trinity / Useful Compute benchmark schema — strict v0.1."""

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
    / "useful_compute_benchmark.schema.json"
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
def bench_mod():
    return _load(
        "ucb_schema_bench",
        SCRIPTS_DIR / "useful_compute_benchmark.py",
    )


def test_schema_id_is_v01(schema):
    assert schema["$id"] == "trinity-useful-compute-benchmark/v0.1"


def test_schema_is_strict(schema):
    assert schema["additionalProperties"] is False
    expected = {
        "schema", "benchmark_id", "mode",
        "backend_name", "backend_version", "backend_kind",
        "task_type", "iterations",
        "wall_time_seconds", "operations_count",
        "deterministic_work_units", "normalized_work_score",
        "machine_fingerprint_hash", "worker_id_hash",
        "safety_status",
    }
    assert set(schema["required"]) == expected


def test_safety_status_locks_five_flags(schema):
    ss = schema["properties"]["safety_status"]
    assert ss["additionalProperties"] is False
    for k in (
        "no_wallet_access", "no_private_keys",
        "no_network_required", "no_automatic_payout",
        "benchmark_only",
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


def test_benchmark_output_validates_against_schema(schema, bench_mod):
    report = bench_mod.run_benchmark(
        backend_name="local_python_numeric_v01",
        task_type="scoring",
        iterations=100,
        worker_id="miner-schema-1",
    )
    _validate_against_schema(report, schema)


def test_benchmark_output_rejects_extra_fields(schema, bench_mod):
    report = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=10, worker_id="m",
    )
    report["sneaky_extra"] = 1
    with pytest.raises(AssertionError, match="extra fields"):
        _validate_against_schema(report, schema)


def test_benchmark_id_pattern(schema):
    bid_schema = schema["properties"]["benchmark_id"]
    assert bid_schema["pattern"] == r"^bench-[0-9a-f]{16}$"
