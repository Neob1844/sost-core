"""Trinity / Useful Compute manifest — schema + builder invariants."""

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
    REPO_ROOT / "schemas" / "trinity" / "useful_compute_request.schema.json"
)


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb", SCRIPTS_DIR / "useful_compute_task_builder.py"
    )


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _required(schema):
    return set(schema["required"])


def _props(schema):
    return schema["properties"]


def test_schema_has_expected_required_fields(schema):
    expected = {
        "schema", "request_id", "source_tool", "candidate_id",
        "task_type", "input_bundle_sha256", "expected_output_schema",
        "validation_method", "estimated_compute_cost",
        "max_reward_stocks", "deadline", "manual_review_required",
        "public_description",
    }
    assert _required(schema) == expected


def test_schema_const_matches_builder(schema, builder_mod):
    assert schema["properties"]["schema"]["const"] == builder_mod.SCHEMA


def test_builder_emits_well_formed_manifest(builder_mod):
    m = builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-xyz",
        input_bundle_bytes=b"hello-bundle",
        expected_output_schema="materials-dft-result/v0",
        difficulty_class="high",
        max_reward_stocks=50000,
        deadline="2026-05-12T00:00:00+00:00",
        public_description="dry-run DFT request for cand-xyz",
    )
    assert m["schema"] == "trinity-useful-compute-request/v0.1"
    assert re.match(r"^uc-[0-9a-f]{16,64}$", m["request_id"])
    assert re.match(r"^[0-9a-f]{64}$", m["input_bundle_sha256"])
    assert m["source_tool"] == "materials_engine"
    assert m["estimated_compute_cost"]["tier"] == "high"
    assert m["max_reward_stocks"] == 50000


def test_builder_rejects_unknown_source(builder_mod):
    with pytest.raises(ValueError):
        builder_mod.build_request(
            source_tool="evil_tool",
            candidate_id="x", input_bundle_bytes=b"x",
            expected_output_schema="y",
            difficulty_class="low",
            max_reward_stocks=1, deadline="2026-05-12T00:00:00+00:00",
            public_description="x",
        )


def test_builder_rejects_unknown_difficulty(builder_mod):
    with pytest.raises(ValueError):
        builder_mod.build_request(
            source_tool="geaspirit",
            candidate_id="x", input_bundle_bytes=b"x",
            expected_output_schema="y",
            difficulty_class="nuclear",
            max_reward_stocks=1, deadline="2026-05-12T00:00:00+00:00",
            public_description="x",
        )


def test_cli_rejects_emit_flag(builder_mod, tmp_path):
    p_in = tmp_path / "in.bin"
    p_in.write_bytes(b"x")
    rc = builder_mod.main([
        "--source-tool", "geaspirit",
        "--candidate-id", "GEO-x",
        "--input-bundle", str(p_in),
        "--expected-output-schema", "geo-followup/v0",
        "--difficulty-class", "low",
        "--deadline", "2026-05-12T00:00:00+00:00",
        "--public-description", "test",
        "--out-json", str(tmp_path / "out.json"),
        "--emit",
    ])
    assert rc == 2


def test_request_id_is_deterministic(builder_mod):
    kw = dict(
        source_tool="materials_engine",
        candidate_id="C-1",
        input_bundle_bytes=b"abc",
        expected_output_schema="schema/v0",
        difficulty_class="medium",
        max_reward_stocks=1000,
        deadline="2026-05-12T00:00:00+00:00",
        public_description="d",
    )
    a = builder_mod.build_request(**kw)
    b = builder_mod.build_request(**kw)
    assert a["request_id"] == b["request_id"]
