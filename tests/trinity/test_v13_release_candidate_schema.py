"""Schema tests for trinity-v13-release-candidate-report/v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_release_candidate_report.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_report():
    return {
        "schema": "trinity-v13-release-candidate-report/v0.1",
        "report_id": "v13rc-0123456789abcdef",
        "pinned_time": "2026-05-18T13:00:00+00:00",
        "repo_root_basename": "sost-core",
        "config_loaded": True,
        "public_mirror_loaded": True,
        "rc_id": "v13-rc1",
        "activation_heights": {
            "v13_activation_height": 12000,
            "v15_fallback_height": 15000,
            "dtd_lottery_decision_height": 12100,
        },
        "min_commit": "e87fb78b3c7a1609ee6cdb4dc237feacf9ff4e2a",
        "required_binary_label": "v13-rc1",
        "ntp_required": False,
        "ntp_recommended": True,
        "future_timestamp_drift_cap_seconds": 30,
        "dtd_lottery_cooldown_post_v13": 6,
        "confirmed_items_ready": {
            "casert_all_profiles_e7_h35": True,
            "dtd_cooldown_6": True,
            "timestamp_drift_30s": True,
            "beacon_phase_ii_a": True,
            "all_ready": True,
        },
        "fallback_v15_items": [
            "popc_model_a_b",
            "beacon_phase_ii_b",
            "beacon_phase_iii",
            "memory_lock_per_instance",
        ],
        "docs_present": {
            "release_candidate_md": True,
            "miner_operator_checklist_md": True,
            "activation_plan_md": True,
            "readiness_gates_md": True,
        },
        "docs_mention_block_12000": True,
        "docs_mention_ntp_10s": True,
        "docs_mention_dtd_decision_12100": True,
        "docs_mention_fallback_v15": True,
        "public_mirror_matches_safe_fields": True,
        "rc_ready": True,
        "warnings": [],
        "safety_status": "ok",
        "safety_flags": {
            "no_wallet_access": True,
            "no_private_key_access": True,
            "no_signing": True,
            "no_broadcast": True,
            "no_network_required": True,
            "no_github_api": True,
            "no_shell_true": True,
            "no_destructive_git": True,
            "no_auto_push_merge_tag": True,
            "no_subprocess": True,
            "no_ethereum_deploy": True,
        },
    }


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-v13-release-candidate-report/v0.1"


def test_good_report_validates(schema, good_report):
    jsonschema.validate(good_report, schema)


def test_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    for sub in (
        "activation_heights",
        "confirmed_items_ready",
        "docs_present",
        "safety_flags",
    ):
        assert schema["properties"][sub]["additionalProperties"] is False


def test_activation_heights_const_locked(schema):
    h = schema["properties"]["activation_heights"]["properties"]
    assert h["v13_activation_height"]["const"]       == 12000
    assert h["v15_fallback_height"]["const"]         == 15000
    assert h["dtd_lottery_decision_height"]["const"] == 12100


def test_ntp_drift_cooldown_const_locked(schema):
    assert schema["properties"]["ntp_required"]["const"] is False
    assert schema["properties"]["ntp_recommended"]["const"] is True
    assert (
        schema["properties"]["future_timestamp_drift_cap_seconds"]["const"]
        == 30
    )
    assert (
        schema["properties"]["dtd_lottery_cooldown_post_v13"]["const"]
        == 6
    )


def test_safety_flags_all_const_true(schema):
    flags = schema["properties"]["safety_flags"]["properties"]
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
        "no_github_api",
        "no_shell_true",
        "no_destructive_git",
        "no_auto_push_merge_tag",
        "no_subprocess",
        "no_ethereum_deploy",
    ):
        assert flags[flag]["const"] is True, "flag " + flag


def test_safety_status_enum(schema):
    assert sorted(schema["properties"]["safety_status"]["enum"]) == [
        "failed", "ok", "warning",
    ]


def test_report_id_pattern(schema):
    assert schema["properties"]["report_id"]["pattern"] == (
        "^v13rc-[0-9a-f]{16}$"
    )


def test_rc_id_pattern(schema):
    assert schema["properties"]["rc_id"]["pattern"] == (
        "^v13-rc[0-9]+$"
    )


def test_min_commit_pattern(schema):
    assert schema["properties"]["min_commit"]["pattern"] == (
        "^[0-9a-f]{7,40}$"
    )


def test_fallback_v15_items_capped(schema):
    assert schema["properties"]["fallback_v15_items"]["maxItems"] == 8


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
    bad["safety_flags"].pop("no_subprocess")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_extra_safety_flag_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"]["rogue_flag"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_activation_height_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["activation_heights"]["v13_activation_height"] = 13000
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_fallback_height_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["activation_heights"]["v15_fallback_height"] = 14000
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_ntp_required_rejected(schema, good_report):
    """Schema locks ntp_required const to False post-V13 (NTP is strongly
    recommended, not consensus-mandatory). Any True must be rejected."""
    bad = copy.deepcopy(good_report)
    bad["ntp_required"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_ntp_recommended_rejected(schema, good_report):
    """ntp_recommended const True locks the operational recommendation.
    A False must be rejected — that would silently flip the operator advice."""
    bad = copy.deepcopy(good_report)
    bad["ntp_recommended"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_drift_seconds_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["future_timestamp_drift_cap_seconds"] = 60
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_cooldown_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["dtd_lottery_cooldown_post_v13"] = 5
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_report_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["report_id"] = "v13rc-XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_rc_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["rc_id"] = "rc1-final"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_min_commit_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["min_commit"] = "ZZZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_safety_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_status"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
