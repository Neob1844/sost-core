"""Schema tests for trinity-v13-binary-preflight-report/v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_binary_preflight_report.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_report():
    return {
        "schema": "trinity-v13-binary-preflight-report/v0.1",
        "report_id": "v13bpf-0123456789abcdef",
        "pinned_time": "2026-05-18T14:00:00+00:00",
        "preflight_id": "v13-rc1-preflight-v01",
        "rc_id": "v13-rc1",
        "repo_root_basename": "sost-core",
        "build_dir_basename": "build-v13-rc1",
        "git": {
            "head_commit": "d604aafafd65dcb90c34fa5845bedee8038daffc",
            "head_commit_short": "d604aafafd65dcb9",
            "min_commit": "d604aafafd65dcb90c34fa5845bedee8038daffc",
            "min_commit_short": "d604aafafd65dcb9",
            "head_matches_min_commit": True,
            "current_branch": "main",
            "tracked_dirty": False,
        },
        "configs": {
            "v13_binary_preflight_loaded":  True,
            "v13_activation_loaded":        True,
            "v13_release_candidate_loaded": True,
        },
        "binaries": [
            {"name": "sost-node",  "present": True,  "size_bytes": 12345,
             "sha256": "a" * 64},
            {"name": "sost-miner", "present": True,  "size_bytes": 12346,
             "sha256": "b" * 64},
            {"name": "sost-cli",   "present": False, "size_bytes": None,
             "sha256": None},
        ],
        "tests": {
            "pytest": {
                "ran": True,
                "target": "tests/trinity/",
                "returncode": 0,
                "passed": 1642,
                "failed": 0,
                "skipped": 38,
                "errors": 0,
                "summary": "1642 passed, 38 skipped",
            },
            "ctest": {
                "ran": True,
                "tests": [
                    {
                        "id": "casert_v13_ceiling",
                        "name": "casert-v13-ceiling",
                        "ran": True,
                        "returncode": 0,
                        "status": "pass",
                    },
                ],
            },
        },
        "options": {
            "require_binaries":  True,
            "run_tests":         True,
            "run_ctest":         True,
            "write_sha256sums":  True,
        },
        "sha256sums_written": True,
        "ready_to_build":     True,
        "ready_to_release":   False,
        "warnings":           [],
        "safety_status":      "ok",
        "safety_flags": {
            "no_wallet_access":      True,
            "no_private_key_access": True,
            "no_signing":            True,
            "no_broadcast":          True,
            "no_release_upload":     True,
            "no_network_required":   True,
            "no_auto_restart":       True,
            "no_ethereum_deploy":    True,
            "no_destructive_git":    True,
            "no_shell_true":         True,
            "no_make_invocation":    True,
            "no_cmake_invocation":   True,
        },
    }


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-v13-binary-preflight-report/v0.1"


def test_good_report_validates(schema, good_report):
    jsonschema.validate(good_report, schema)


def test_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    for sub in (
        "git",
        "configs",
        "options",
        "safety_flags",
    ):
        assert schema["properties"][sub]["additionalProperties"] is False
    bins = schema["properties"]["binaries"]["items"]
    assert bins["additionalProperties"] is False
    p = schema["properties"]["tests"]["properties"]["pytest"]
    assert p["additionalProperties"] is False
    c = schema["properties"]["tests"]["properties"]["ctest"]
    assert c["additionalProperties"] is False
    ct = c["properties"]["tests"]["items"]
    assert ct["additionalProperties"] is False


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
        "no_ethereum_deploy",
        "no_destructive_git",
        "no_shell_true",
        "no_make_invocation",
        "no_cmake_invocation",
    ):
        assert flags[flag]["const"] is True, "flag " + flag


def test_safety_status_enum(schema):
    assert sorted(schema["properties"]["safety_status"]["enum"]) == [
        "failed", "ok", "warning",
    ]


def test_report_id_pattern(schema):
    assert schema["properties"]["report_id"]["pattern"] == (
        "^v13bpf-[0-9a-f]{16}$"
    )


def test_preflight_id_pattern(schema):
    assert schema["properties"]["preflight_id"]["pattern"] == (
        "^v13-rc[0-9]+-preflight-v[0-9]+$"
    )


def test_rc_id_pattern(schema):
    assert schema["properties"]["rc_id"]["pattern"] == (
        "^v13-rc[0-9]+$"
    )


def test_binaries_exactly_three(schema):
    p = schema["properties"]["binaries"]
    assert p["minItems"] == 3 and p["maxItems"] == 3


def test_binary_name_enum(schema):
    item = schema["properties"]["binaries"]["items"]
    assert sorted(item["properties"]["name"]["enum"]) == sorted([
        "sost-cli", "sost-miner", "sost-node",
    ])


def test_ctest_status_enum(schema):
    item = schema["properties"]["tests"]["properties"]["ctest"]\
        ["properties"]["tests"]["items"]
    assert sorted(item["properties"]["status"]["enum"]) == sorted([
        "fail", "missing", "pass", "skipped",
    ])


def test_head_commit_pattern(schema):
    assert schema["properties"]["git"]["properties"]["head_commit"]\
        ["pattern"] == "^[0-9a-f]{40}$"


def test_min_commit_pattern(schema):
    assert schema["properties"]["git"]["properties"]["min_commit"]\
        ["pattern"] == "^[0-9a-f]{7,40}$"


def test_extra_top_level_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["extra"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_safety_flag_flipped_false_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"]["no_broadcast"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_missing_safety_flag_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"].pop("no_make_invocation")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_extra_safety_flag_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"]["rogue_flag"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_binaries_count_must_be_three(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["binaries"] = bad["binaries"][:2]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_binary_name_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["binaries"][0]["name"] = "rogue-bin"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_ctest_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["tests"]["ctest"]["tests"][0]["status"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_safety_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_status"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_report_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["report_id"] = "v13bpf-XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_preflight_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["preflight_id"] = "preflight-rc1"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_rc_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["rc_id"] = "rc1"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_head_commit_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["git"]["head_commit"] = "NOTHEX"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_sha256_in_binary_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["binaries"][0]["sha256"] = "XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
