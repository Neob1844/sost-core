"""Schema tests for the V13 RC1 release manual checklist schema."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_rc1_release_manual_checklist.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _good_report():
    return {
        "schema": "trinity-v13-rc1-release-manual-checklist/v0.1",
        "checklist_id": "v13rc1cl-" + ("a" * 16),
        "pinned_time": "2026-05-18T16:30:00+00:00",
        "rc_id": "v13-rc1",
        "activation_height": 12000,
        "bundle_dir_basename": "sost-v13-rc1-artifact-bundle",
        "repo_root_basename": "sost-core",
        "bundle_checks": {
            "all_ok": True,
            "binaries_present": [
                {"name": "sost-node",  "present": True},
                {"name": "sost-miner", "present": True},
                {"name": "sost-cli",   "present": True},
            ],
            "sha256sums_present": True,
            "sha256sums_lines": [
                {"name": "sost-node",  "sha256": "f" * 64},
                {"name": "sost-miner", "sha256": "e" * 64},
                {"name": "sost-cli",   "sha256": "d" * 64},
            ],
            "manifest_json_present":   True,
            "manifest_md_present":     True,
            "verify_commands_present": True,
            "tarball_present":         True,
        },
        "public_metadata_state": {
            "release_status_current": (
                "metadata_only_not_signed_not_uploaded"
            ),
            "release_status_expected": (
                "metadata_only_not_signed_not_uploaded"
            ),
            "matches": True,
        },
        "manual_steps": [
            {"id": "A1", "stage": "A_preverify",
             "title": "Re-run preflight",
             "description": "Re-run binary preflight against the bundle.",
             "command_template": "python3 scripts/...",
             "uses_release_key": False, "uses_network": False,
             "must_be_done_by_operator": True},
            {"id": "A2", "stage": "A_preverify",
             "title": "Diff SHA256SUMS",
             "description": "Diff bundle SHA256SUMS vs. published.",
             "command_template": "diff -u ...",
             "uses_release_key": False, "uses_network": False,
             "must_be_done_by_operator": True},
            {"id": "A3", "stage": "A_preverify",
             "title": "Confirm release key",
             "description": "Make sure operator release key is available.",
             "command_template": "gpg --list-secret-keys ...",
             "uses_release_key": True, "uses_network": False,
             "must_be_done_by_operator": True},
            {"id": "B1", "stage": "B_sign",
             "title": "Sign SHA256SUMS (template)",
             "description": "Detached ASCII-armored signature template.",
             "command_template": "<gpg-detach-sign-template>",
             "uses_release_key": True, "uses_network": False,
             "must_be_done_by_operator": True},
            {"id": "C1", "stage": "C_upload",
             "title": "Upload artifacts (template)",
             "description": "Operator-driven release upload template.",
             "command_template": "<gh-release-template>",
             "uses_release_key": False, "uses_network": True,
             "must_be_done_by_operator": True},
            {"id": "D1", "stage": "D_update_metadata",
             "title": "Bump release_status",
             "description": "Update public manifest release_status.",
             "command_template": "<edit-website-template>",
             "uses_release_key": False, "uses_network": False,
             "must_be_done_by_operator": True},
            {"id": "E1", "stage": "E_announce",
             "title": "Post announcement",
             "description": "Post on BitcoinTalk / Telegram / web.",
             "command_template": "<announcement-template>",
             "uses_release_key": False, "uses_network": True,
             "must_be_done_by_operator": True},
        ],
        "safety_status": "ok",
        "safety_flags": {
            "no_private_key_access": True,
            "no_signing_executed":   True,
            "no_release_upload":     True,
            "no_github_api":         True,
            "no_wallet_access":      True,
            "no_broadcast":          True,
            "no_network_required":   True,
            "no_subprocess":         True,
            "no_shell_true":         True,
            "no_ethereum_deploy":    True,
            "no_gpg_invocation":     True,
        },
    }


def test_schema_loads(schema):
    assert schema["$id"] == "trinity-v13-rc1-release-manual-checklist/v0.1"


def test_good_report_validates(schema):
    jsonschema.validate(_good_report(), schema)


def test_rejects_wrong_schema_value(schema):
    bad = _good_report()
    bad["schema"] = "trinity-wrong/v0.1"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_bad_checklist_id(schema):
    bad = _good_report()
    bad["checklist_id"] = "v13rc1cl-NOT-HEX-XX"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_bad_rc_id(schema):
    bad = _good_report()
    bad["rc_id"] = "v14-rc1"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_wrong_activation_height(schema):
    bad = _good_report()
    bad["activation_height"] = 11999
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_unknown_release_status_current(schema):
    bad = _good_report()
    bad["public_metadata_state"]["release_status_current"] = "yolo"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_wrong_release_status_expected(schema):
    bad = _good_report()
    bad["public_metadata_state"]["release_status_expected"] = (
        "signed_and_published"
    )
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_unknown_stage(schema):
    bad = _good_report()
    bad["manual_steps"][0]["stage"] = "F_party"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_bad_step_id_pattern(schema):
    bad = _good_report()
    bad["manual_steps"][0]["id"] = "1A"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_must_be_done_by_operator_false(schema):
    bad = _good_report()
    bad["manual_steps"][0]["must_be_done_by_operator"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_additional_property_top_level(schema):
    bad = _good_report()
    bad["extra_field"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_additional_property_in_step(schema):
    bad = _good_report()
    bad["manual_steps"][0]["extra"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_additional_property_in_bundle_checks(schema):
    bad = _good_report()
    bad["bundle_checks"]["extra"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_bad_safety_status(schema):
    bad = _good_report()
    bad["safety_status"] = "ok!"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


@pytest.mark.parametrize("flag", [
    "no_private_key_access", "no_signing_executed",
    "no_release_upload", "no_github_api", "no_wallet_access",
    "no_broadcast", "no_network_required", "no_subprocess",
    "no_shell_true", "no_ethereum_deploy", "no_gpg_invocation",
])
def test_all_safety_flags_must_be_const_true(schema, flag):
    bad = _good_report()
    bad["safety_flags"][flag] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_missing_safety_flag(schema):
    bad = _good_report()
    del bad["safety_flags"]["no_gpg_invocation"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_bad_sha256_in_sha256sums_lines(schema):
    bad = _good_report()
    bad["bundle_checks"]["sha256sums_lines"][0]["sha256"] = "nothex"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_too_few_manual_steps(schema):
    bad = _good_report()
    bad["manual_steps"] = bad["manual_steps"][:2]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_rejects_unknown_binary_name(schema):
    bad = _good_report()
    bad["bundle_checks"]["binaries_present"][0]["name"] = "sost-bogus"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_deepcopy_does_not_change_validity(schema):
    cl = _good_report()
    cl2 = copy.deepcopy(cl)
    jsonschema.validate(cl2, schema)
