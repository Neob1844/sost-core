"""Schema tests for the Trinity Worker Trial Pack Manifest v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "worker_trial_pack_manifest.schema.json"
)
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "worker_trial_pack.py"
FIXTURE = (
    REPO_ROOT / "tests" / "trinity" / "fixtures"
    / "useful_compute" / "request_materials_engine.json"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "worker_trial_pack", str(SCRIPT),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_manifest(tmp_path):
    wtp = _import_script()
    manifest = wtp.build_trial_pack(
        worker_id="worker-D",
        pinned_time="2026-05-18T00:00:00+00:00",
        out_dir=tmp_path,
        request_fixture=FIXTURE,
        repo_commit="abc1234567",
        repo_tag="sprint-5.34-5.36",
    )
    # build_trial_pack adds _manifest_text_sha256 to the in-memory
    # dict; the on-disk manifest does NOT have it. Strip for schema.
    manifest = dict(manifest)
    manifest.pop("_manifest_text_sha256", None)
    return manifest


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-worker-trial-pack-manifest/v0.1"


def test_good_manifest_validates(schema, good_manifest):
    jsonschema.validate(good_manifest, schema)


def test_schema_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    files_item = schema["properties"]["files"]["items"]
    assert files_item["additionalProperties"] is False
    safety = schema["properties"]["safety_status"]
    assert safety["additionalProperties"] is False


def test_pack_id_pattern(schema):
    assert schema["properties"]["pack_id"]["pattern"] == (
        "^twtp-[0-9a-f]{16}$"
    )


def test_files_array_exactly_four(schema):
    p = schema["properties"]["files"]
    assert p["minItems"] == 4 and p["maxItems"] == 4


def test_safety_flags_const_true(schema):
    safety = schema["properties"]["safety_status"]["properties"]
    for flag in (
        "no_wallet_required",
        "no_private_key_required",
        "no_seed_phrase_required",
        "no_broadcast_capability",
        "no_network_in_worker_process",
        "pack_carries_no_secrets",
    ):
        assert safety[flag]["const"] is True, "flag " + flag


def test_bad_pack_id_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["pack_id"] = "twtp-XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_real_sost_address_in_pack_rejected_by_size(schema, good_manifest):
    """The schema doesn't directly inspect payload text; the
    address-rejection guarantee is enforced at the trial-pack
    builder + the static safety tests. Schema validates the
    structure; we re-assert here that the request_basename can
    only be 'sample_request.json'."""
    bad = copy.deepcopy(good_manifest)
    bad["request_basename"] = "evil.json"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_safety_status_flipped_to_false_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["safety_status"]["no_wallet_required"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_repo_commit_pattern_enforced(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["repo_commit"] = "NOTHEX"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_extra_top_level_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["extra"] = "field"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_extra_safety_flag_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["safety_status"]["unknown_extra_flag"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
