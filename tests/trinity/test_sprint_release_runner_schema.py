"""Schema tests for Trinity Sprint Release Report v0.1."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "sprint_release_report.schema.json"
)


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good_report():
    return {
        "schema": "trinity-sprint-release-report/v0.1",
        "report_id": "tsr-0123456789abcdef",
        "pinned_time": "2026-05-18T00:10:00+00:00",
        "sprint_id": "sprint-5.40",
        "branch": "trinity/sprint-release-runner-v01",
        "current_branch": "trinity/sprint-release-runner-v01",
        "branch_match": True,
        "base_ref": "main",
        "head_commit": "a" * 40,
        "head_commit_short": "a" * 16,
        "base_commit": "b" * 40,
        "base_commit_short": "b" * 16,
        "repo_root_basename": "sost-core",
        "tree_status": {
            "tracked_dirty": False,
            "untracked_count": 0,
            "untracked_allowed": False,
        },
        "changed_files": [
            {
                "path": "scripts/trinity/sprint_release_runner.py",
                "status": "modified",
                "additions": 500,
                "deletions": 0,
            },
        ],
        "changed_files_count": 1,
        "additions_total": 500,
        "deletions_total": 0,
        "commits_ahead": [
            {
                "sha_short": "abcdef0123456789",
                "subject": "trinity: release runner",
            },
        ],
        "commits_ahead_count": 1,
        "pytest": {
            "ran": True,
            "target": "tests/trinity/",
            "returncode": 0,
            "passed": 1474,
            "failed": 0,
            "skipped": 38,
            "errors": 0,
            "summary": "1474 passed, 38 skipped in 8.81s",
        },
        "demo_artifacts": [
            {
                "artifact_type": "autopilot_report",
                "path_basename":
                    "TRINITY_TASK_QUEUE_AUTOPILOT_REPORT_tap-X.json",
                "schema": "trinity-task-queue-autopilot-report/v0.1",
                "summary": {"items_completed": 2},
            },
        ],
        "demo_artifacts_count": 1,
        "warnings": [],
        "ready_to_release": True,
        "require_clean_tracked_tree": False,
        "safety_status": "ok",
        "safety_flags": {
            "no_git_push":         True,
            "no_git_merge":        True,
            "no_git_tag":          True,
            "no_wallet_access":    True,
            "no_signing":          True,
            "no_broadcast":        True,
            "no_network_required": True,
        },
    }


def test_schema_is_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_v01_id(schema):
    assert schema["$id"] == "trinity-sprint-release-report/v0.1"


def test_good_report_validates(schema, good_report):
    jsonschema.validate(good_report, schema)


def test_additional_properties_locked(schema):
    assert schema["additionalProperties"] is False
    for sub in ("tree_status", "pytest", "safety_flags"):
        assert schema["properties"][sub]["additionalProperties"] is False
    cf = schema["properties"]["changed_files"]["items"]
    assert cf["additionalProperties"] is False
    ca = schema["properties"]["commits_ahead"]["items"]
    assert ca["additionalProperties"] is False
    da = schema["properties"]["demo_artifacts"]["items"]
    assert da["additionalProperties"] is False


def test_safety_flags_all_const_true(schema):
    flags = schema["properties"]["safety_flags"]["properties"]
    for f in (
        "no_git_push", "no_git_merge", "no_git_tag",
        "no_wallet_access", "no_signing", "no_broadcast",
        "no_network_required",
    ):
        assert flags[f]["const"] is True, "flag: " + f


def test_report_id_pattern(schema):
    assert schema["properties"]["report_id"]["pattern"] == (
        "^tsr-[0-9a-f]{16}$"
    )


def test_sprint_id_pattern(schema):
    assert schema["properties"]["sprint_id"]["pattern"] == (
        "^sprint-[0-9A-Za-z.-]+$"
    )


def test_head_commit_pattern(schema):
    assert schema["properties"]["head_commit"]["pattern"] == (
        "^[0-9a-f]{40}$"
    )


def test_artifact_type_enum(schema):
    da = schema["properties"]["demo_artifacts"]["items"]
    assert sorted(da["properties"]["artifact_type"]["enum"]) == sorted([
        "autopilot_report", "dashboard",
        "daily_report", "trial_pack_manifest",
    ])


def test_safety_status_enum(schema):
    assert sorted(schema["properties"]["safety_status"]["enum"]) == [
        "failed", "ok", "warning",
    ]


def test_demo_artifacts_capped_at_100(schema):
    assert schema["properties"]["demo_artifacts"]["maxItems"] == 100


def test_changed_files_capped_at_200(schema):
    assert schema["properties"]["changed_files"]["maxItems"] == 200


def test_extra_top_level_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["extra"] = 1
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_safety_flag_flipped_false_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"]["no_git_push"] = False
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_missing_safety_flag_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"].pop("no_broadcast")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_extra_safety_flag_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_flags"]["unknown_flag"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_sprint_id_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["sprint_id"] = "release-1.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_head_commit_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["head_commit"] = "NOTHEX"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_artifact_type_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["demo_artifacts"][0]["artifact_type"] = "rogue"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_bad_safety_status_rejected(schema, good_report):
    bad = copy.deepcopy(good_report)
    bad["safety_status"] = "panic"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
