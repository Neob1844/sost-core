"""Schema tests for trinity-v13-rc1-artifact-bundle-manifest/v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_rc1_artifact_bundle_manifest.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_manifest():
    return {
        "schema": "trinity-v13-rc1-artifact-bundle-manifest/v0.1",
        "bundle_id": "v13rc1bundle-0123456789abcdef",
        "pinned_time": "2026-05-18T15:30:00+00:00",
        "rc_id": "v13-rc1",
        "activation_height": 12000,
        "min_commit": "d604aafafd65dcb90c34fa5845bedee8038daffc",
        "min_commit_short": "d604aafafd65dcb9",
        "repo_root_basename": "sost-core",
        "preflight_was_ready": True,
        "binaries": [
            {
                "name": "sost-node",
                "basename_under_bin": "sost-node",
                "size_bytes": 12345,
                "sha256": "c" * 64,
            },
            {
                "name": "sost-miner",
                "basename_under_bin": "sost-miner",
                "size_bytes": 12346,
                "sha256": "5" * 64,
            },
            {
                "name": "sost-cli",
                "basename_under_bin": "sost-cli",
                "size_bytes": 12347,
                "sha256": "b" * 64,
            },
        ],
        "sha256sums_basename": "SHA256SUMS",
        "reports": [
            {
                "name": "report.json",
                "basename_under_reports": "preflight_report.json",
                "sha256": "a" * 64,
            },
            {
                "name": "report.md",
                "basename_under_reports": "preflight_report.md",
                "sha256": "f" * 64,
            },
        ],
        "configs": [
            {
                "name": "config/v13_release_candidate.json",
                "basename_under_config": "v13_release_candidate.json",
                "sha256": "1" * 64,
            },
            {
                "name": "config/v13_activation.json",
                "basename_under_config": "v13_activation.json",
                "sha256": "2" * 64,
            },
            {
                "name": "config/v13_binary_preflight.json",
                "basename_under_config": "v13_binary_preflight.json",
                "sha256": "3" * 64,
            },
        ],
        "has_tarball": False,
        "tarball": None,
        "no_copy_binaries_mode": False,
        "safety_flags": {
            "no_wallet_access":      True,
            "no_private_key_access": True,
            "no_signing":            True,
            "no_broadcast":          True,
            "no_release_upload":     True,
            "no_network_required":   True,
            "no_auto_restart":       True,
            "no_subprocess":         True,
            "no_shell_true":         True,
            "no_github_api":         True,
            "no_ethereum_deploy":    True,
        },
    }


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == (
        "trinity-v13-rc1-artifact-bundle-manifest/v0.1"
    )


def test_good_manifest_validates(schema, good_manifest):
    jsonschema.validate(good_manifest, schema)


def test_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    for sub in ("safety_flags",):
        assert schema["properties"][sub]["additionalProperties"] is False
    bins = schema["properties"]["binaries"]["items"]
    assert bins["additionalProperties"] is False
    rep = schema["properties"]["reports"]["items"]
    assert rep["additionalProperties"] is False
    cfg = schema["properties"]["configs"]["items"]
    assert cfg["additionalProperties"] is False


def test_activation_height_const_locked(schema):
    assert schema["properties"]["activation_height"]["const"] == 12000


def test_sha256sums_basename_const(schema):
    assert schema["properties"]["sha256sums_basename"]["const"] == (
        "SHA256SUMS"
    )


def test_safety_flags_all_const_true(schema):
    flags = schema["properties"]["safety_flags"]["properties"]
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_release_upload",
        "no_network_required",
        "no_auto_restart",
        "no_subprocess",
        "no_shell_true",
        "no_github_api",
        "no_ethereum_deploy",
    ):
        assert flags[flag]["const"] is True, "flag " + flag


def test_bundle_id_pattern(schema):
    assert schema["properties"]["bundle_id"]["pattern"] == (
        "^v13rc1bundle-[0-9a-f]{16}$"
    )


def test_rc_id_pattern(schema):
    assert schema["properties"]["rc_id"]["pattern"] == (
        "^v13-rc[0-9]+$"
    )


def test_binary_name_enum(schema):
    item = schema["properties"]["binaries"]["items"]
    assert sorted(item["properties"]["name"]["enum"]) == sorted([
        "sost-cli", "sost-miner", "sost-node",
    ])


def test_min_commit_pattern(schema):
    assert schema["properties"]["min_commit"]["pattern"] == (
        "^[0-9a-f]{7,40}$"
    )


def test_extra_top_level_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["extra"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_safety_flag_flipped_false_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["safety_flags"]["no_broadcast"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_missing_safety_flag_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["safety_flags"].pop("no_subprocess")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_extra_safety_flag_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["safety_flags"]["rogue_flag"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_activation_height_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["activation_height"] = 13000
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_bundle_id_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["bundle_id"] = "v13rc1bundle-XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_rc_id_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["rc_id"] = "rc1-final"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_min_commit_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["min_commit"] = "ZZZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_binary_name_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["binaries"][0]["name"] = "rogue-bin"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_sha256_in_binary_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["binaries"][0]["sha256"] = "XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_sha256sums_basename_rejected(schema, good_manifest):
    bad = copy.deepcopy(good_manifest)
    bad["sha256sums_basename"] = "checksums.txt"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_tarball_null_or_object_only(schema, good_manifest):
    # Null is allowed.
    bad_null = copy.deepcopy(good_manifest)
    bad_null["tarball"] = None
    bad_null["has_tarball"] = False
    jsonschema.validate(bad_null, schema)
    # Valid object.
    bad_obj = copy.deepcopy(good_manifest)
    bad_obj["has_tarball"] = True
    bad_obj["tarball"] = {
        "basename":   "v13-rc1-artifact-bundle-x.tar.gz",
        "size_bytes": 4096,
        "sha256":     "0" * 64,
    }
    jsonschema.validate(bad_obj, schema)
    # Invalid tarball basename (no .tar.gz).
    bad_bn = copy.deepcopy(good_manifest)
    bad_bn["has_tarball"] = True
    bad_bn["tarball"] = {
        "basename":   "v13.tgz",
        "size_bytes": 4096,
        "sha256":     "0" * 64,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad_bn, schema)
