"""Schema tests for trinity-v13-readiness-report/v0.1 and
trinity-v13-activation-config/v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_readiness_report.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_report():
    return {
        "schema": "trinity-v13-readiness-report/v0.1",
        "report_id": "v13rr-0123456789abcdef",
        "pinned_time": "2026-05-18T00:30:00+00:00",
        "repo_root_basename": "sost-core",
        "config_loaded": True,
        "activation_heights": {
            "v13_activation_height": 12000,
            "v15_fallback_height": 15000,
            "dtd_lottery_decision_height": 12100,
            "current_height_estimate": 7700,
        },
        "confirmed_items": [
            {
                "id": "casert_all_profiles_e7_h35",
                "label": "All cASERT equalizer profiles E7-H35 active",
                "wired_in_code": False,
                "evidence": "no V13-gated profile-ceiling expansion found",
                "ready": False,
                "blocker_note":
                    "Add effective_profile_ceiling_at(height) helper",
            },
            {
                "id": "dtd_cooldown_6",
                "label": "DTD lottery cooldown 5 -> 6 blocks",
                "wired_in_code": True,
                "evidence":
                    "include/sost/params.h: lottery_exclusion_window_at",
                "ready": True,
            },
            {
                "id": "timestamp_drift_30s",
                "label": "Future-drift cap 60s -> 30s",
                "wired_in_code": True,
                "evidence": "include/sost/params.h: max_future_drift_at",
                "ready": True,
            },
            {
                "id": "beacon_phase_ii_a",
                "label": "Beacon Phase II-A",
                "wired_in_code": True,
                "evidence":
                    "BEACON_PHASE2A_ACTIVATION_HEIGHT = V13_HEIGHT",
                "ready": True,
            },
        ],
        "gated_items": [
            {
                "id": "popc_model_a_b",
                "label": "PoPC Model A + B",
                "target_height": 12000,
                "fallback_height": 15000,
                "gates": [
                    {
                        "id": "popc_a_audit_daemon",
                        "rule": "Audit daemon exists",
                        "status": "fail",
                        "evidence": "no daemon",
                        "blocker_note": "build the daemon",
                    },
                ],
                "v13_ready": False,
                "resolved_activation_height": 15000,
            },
            {
                "id": "beacon_phase_ii_b",
                "label": "Beacon Phase II-B",
                "target_height": 12000,
                "fallback_height": 15000,
                "gates": [{
                    "id": "beacon_iib_design_closed",
                    "rule": "Design closed",
                    "status": "fail",
                    "evidence": "no doc",
                }],
                "v13_ready": False,
                "resolved_activation_height": 15000,
            },
            {
                "id": "beacon_phase_iii",
                "label": "Beacon Phase III",
                "target_height": 12000,
                "fallback_height": 15000,
                "gates": [{
                    "id": "beacon_iii_p2p_implementation",
                    "rule": "P2P implementation",
                    "status": "pass",
                    "evidence": "scaffold present",
                }],
                "v13_ready": False,
                "resolved_activation_height": 15000,
            },
            {
                "id": "memory_lock_per_instance",
                "label": "Memory-Lock per-instance",
                "target_height": 12000,
                "fallback_height": 15000,
                "gates": [{
                    "id": "memlock_design_doc",
                    "rule": "Design doc exists",
                    "status": "fail",
                    "evidence": "no doc",
                }],
                "v13_ready": False,
                "resolved_activation_height": 15000,
            },
        ],
        "decision_at_12100": {
            "subject": "DTD lottery: keep or remove",
            "decision_window_opens_at_height": 12100,
        },
        "v13_ready_for_confirmed_items": False,
        "popc_v13_ready": False,
        "beacon_iib_v13_ready": False,
        "beacon_iii_v13_ready": False,
        "memory_lock_v13_ready": False,
        "fallback_to_v15_items": [
            "popc_model_a_b",
            "beacon_phase_ii_b",
            "beacon_phase_iii",
            "memory_lock_per_instance",
        ],
        "warnings": [],
        "overall_decision": "v13_confirmed_items_not_ready_block_fork",
        "safety_status": "warning",
        "safety_flags": {
            "no_wallet_access": True,
            "no_private_key_access": True,
            "no_signing": True,
            "no_broadcast": True,
            "no_network_calls": True,
            "no_github_api": True,
            "no_shell_true": True,
            "no_destructive_git": True,
            "no_auto_push_merge_tag": True,
            "ntp_mandatory_post_v13": True,
            "half_enabled_items_forbidden": True,
        },
    }


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-v13-readiness-report/v0.1"


def test_good_report_validates(schema, good_report):
    jsonschema.validate(good_report, schema)


def test_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    for sub in (
        "activation_heights",
        "decision_at_12100",
        "safety_flags",
    ):
        assert schema["properties"][sub]["additionalProperties"] is False
    ci = schema["properties"]["confirmed_items"]["items"]
    assert ci["additionalProperties"] is False
    gi = schema["properties"]["gated_items"]["items"]
    assert gi["additionalProperties"] is False
    ga = gi["properties"]["gates"]["items"]
    assert ga["additionalProperties"] is False


def test_activation_heights_const_locked(schema):
    h = schema["properties"]["activation_heights"]["properties"]
    assert h["v13_activation_height"]["const"]       == 12000
    assert h["v15_fallback_height"]["const"]         == 15000
    assert h["dtd_lottery_decision_height"]["const"] == 12100


def test_safety_flags_all_const_true(schema):
    flags = schema["properties"]["safety_flags"]["properties"]
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_calls",
        "no_github_api",
        "no_shell_true",
        "no_destructive_git",
        "no_auto_push_merge_tag",
        "ntp_mandatory_post_v13",
        "half_enabled_items_forbidden",
    ):
        assert flags[flag]["const"] is True, "flag: " + flag


def test_gate_status_enum(schema):
    g = schema["properties"]["gated_items"]["items"]\
        ["properties"]["gates"]["items"]
    assert sorted(g["properties"]["status"]["enum"]) == [
        "fail", "pass", "unknown",
    ]


def test_overall_decision_enum(schema):
    od = schema["properties"]["overall_decision"]
    assert sorted(od["enum"]) == sorted([
        "v13_confirmed_items_ready_gated_items_fallback_to_v15",
        "v13_all_ready",
        "v13_confirmed_items_not_ready_block_fork",
        "indeterminate",
    ])


def test_resolved_activation_height_enum(schema):
    g = schema["properties"]["gated_items"]["items"]
    assert sorted(g["properties"]["resolved_activation_height"]["enum"]) \
        == [12000, 15000]


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
    bad["safety_flags"].pop("ntp_mandatory_post_v13")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_v13_activation_height_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["activation_heights"]["v13_activation_height"] = 13000
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_v15_fallback_height_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["activation_heights"]["v15_fallback_height"] = 14000
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_resolved_height_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["gated_items"][0]["resolved_activation_height"] = 13000
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_gate_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["gated_items"][0]["gates"][0]["status"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_overall_decision_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["overall_decision"] = "do_the_fork_anyway"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_report_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["report_id"] = "v13rr-XYZ"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_decision_at_12100_height_const(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["decision_at_12100"]["decision_window_opens_at_height"] = 12200
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
