"""Functional tests for V13 Release Candidate check script."""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_release_candidate_check.py"
CONFIG = REPO_ROOT / "config" / "v13_release_candidate.json"
PUBLIC_MIRROR = (
    REPO_ROOT / "website" / "api" / "v13_release_candidate.json"
)
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_release_candidate_report.schema.json"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v13_release_candidate_check", str(SCRIPT),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def srr():
    return _import_script()


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def test_script_exists():
    assert SCRIPT.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_config_exists():
    assert CONFIG.is_file()


def test_public_mirror_exists():
    assert PUBLIC_MIRROR.is_file()


def test_config_schema_id():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["schema"] == "sost-v13-release-candidate/v0.1"


def test_public_mirror_schema_id():
    pub = json.loads(PUBLIC_MIRROR.read_text(encoding="utf-8"))
    assert pub["schema"] == "sost-v13-release-candidate-public/v0.1"


def test_config_activation_heights():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["v13_activation_height"]               == 12000
    assert cfg["v15_fallback_height"]                 == 15000
    assert cfg["dtd_lottery_decision_height"]         == 12100


def test_config_ntp_and_drift_and_cooldown():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["ntp_required"]                              is True
    assert cfg["future_timestamp_drift_seconds_post_v13"]   == 30
    assert cfg["dtd_lottery_cooldown_post_v13"]             == 6


def test_config_confirmed_items_present():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    ids = sorted(c["id"] for c in cfg["confirmed_items"])
    assert ids == sorted([
        "casert_all_profiles_e7_h35",
        "dtd_cooldown_6",
        "timestamp_drift_30s",
        "beacon_phase_ii_a",
    ])


def test_config_fallback_items_present():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    ids = sorted(f["id"] for f in cfg["fallback_v15_items"])
    assert ids == sorted([
        "popc_model_a_b",
        "beacon_phase_ii_b",
        "beacon_phase_iii",
        "memory_lock_per_instance",
    ])


def test_config_operator_actions_six_steps():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert len(cfg["operator_actions"]) == 6
    steps = [a["step"] for a in cfg["operator_actions"]]
    assert steps == [1, 2, 3, 4, 5, 6]


def test_config_safety_all_const_true():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
        "no_auto_restart",
        "no_consensus_auto_toggle",
    ):
        assert cfg["safety"][flag] is True, "config flag: " + flag


def test_public_mirror_safety_all_const_true():
    pub = json.loads(PUBLIC_MIRROR.read_text(encoding="utf-8"))
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
        "no_auto_restart",
        "no_consensus_auto_toggle",
    ):
        assert pub["safety"][flag] is True, "public flag: " + flag


def test_public_mirror_matches_required_fields():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    pub = json.loads(PUBLIC_MIRROR.read_text(encoding="utf-8"))
    for field in (
        "v13_activation_height",
        "v15_fallback_height",
        "dtd_lottery_decision_height",
        "min_commit",
        "required_binary_label",
        "ntp_required",
        "future_timestamp_drift_seconds_post_v13",
        "dtd_lottery_cooldown_post_v13",
    ):
        assert cfg[field] == pub[field], (
            "field " + field + " differs: cfg="
            + repr(cfg[field]) + " pub=" + repr(pub[field])
        )


def test_public_mirror_confirmed_items_ids_match():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    pub = json.loads(PUBLIC_MIRROR.read_text(encoding="utf-8"))
    cfg_ids = sorted(c["id"] for c in cfg["confirmed_items"])
    pub_ids = sorted(pub["confirmed_items_ids"])
    assert cfg_ids == pub_ids


def test_public_mirror_fallback_ids_match():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    pub = json.loads(PUBLIC_MIRROR.read_text(encoding="utf-8"))
    cfg_ids = sorted(f["id"] for f in cfg["fallback_v15_items"])
    pub_ids = sorted(pub["fallback_v15_items_ids"])
    assert cfg_ids == pub_ids


def test_report_validates_against_schema(srr, schema):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    jsonschema.validate(report, schema)


def test_report_top_level_shape(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    assert report["schema"] == "trinity-v13-release-candidate-report/v0.1"
    assert re.match(r"^v13rc-[0-9a-f]{16}$", report["report_id"])
    assert report["rc_id"] == "v13-rc1"
    assert report["activation_heights"]["v13_activation_height"] == 12000
    assert report["activation_heights"]["v15_fallback_height"]   == 15000
    assert (
        report["activation_heights"]["dtd_lottery_decision_height"]
        == 12100
    )
    assert report["ntp_required"]                            is True
    assert report["future_timestamp_drift_seconds_post_v13"] == 30
    assert report["dtd_lottery_cooldown_post_v13"]           == 6


def test_all_confirmed_items_ready(srr):
    """At this commit the V13 readiness branch has already wired
    all four confirmed items. The RC check must reflect that."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    cir = report["confirmed_items_ready"]
    assert cir["casert_all_profiles_e7_h35"] is True
    assert cir["dtd_cooldown_6"]             is True
    assert cir["timestamp_drift_30s"]        is True
    assert cir["beacon_phase_ii_a"]          is True
    assert cir["all_ready"]                  is True


def test_fallback_v15_items_listed(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    assert sorted(report["fallback_v15_items"]) == sorted([
        "popc_model_a_b",
        "beacon_phase_ii_b",
        "beacon_phase_iii",
        "memory_lock_per_instance",
    ])


def test_docs_present(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    for k, v in report["docs_present"].items():
        assert v is True, "doc missing: " + k


def test_docs_mention_required_tokens(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    assert report["docs_mention_block_12000"]        is True
    assert report["docs_mention_ntp_10s"]            is True
    assert report["docs_mention_dtd_decision_12100"] is True
    assert report["docs_mention_fallback_v15"]       is True


def test_public_mirror_matches_safe_fields(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    assert report["public_mirror_matches_safe_fields"] is True


def test_rc_ready_true_at_this_commit(srr):
    """The headline boolean: after the V13 readiness wire, the
    RC must be ready to ship at block 12,000."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    assert report["rc_ready"] is True
    assert report["safety_status"] in ("ok", "warning")


def test_safety_flags_all_const_true(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
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
        assert report["safety_flags"][flag] is True, "flag: " + flag


def test_report_deterministic(srr):
    r1 = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    r2 = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    assert r1["report_id"] == r2["report_id"]
    assert r1["rc_ready"]  == r2["rc_ready"]


def test_cli_writes_json_and_md(srr, tmp_path):
    out_json = tmp_path / "rc.json"
    out_md   = tmp_path / "rc.md"
    rc = srr.main([
        "--repo-root", str(REPO_ROOT),
        "--out-json", str(out_json),
        "--out-md",   str(out_md),
        "--pinned-time", "2026-05-18T13:00:00+00:00",
    ])
    assert rc in (0, 1)
    assert out_json.is_file()
    assert out_md.is_file()
    parsed = json.loads(out_json.read_text())
    assert parsed["schema"] == "trinity-v13-release-candidate-report/v0.1"


def test_cli_returns_0_when_rc_ready(srr, tmp_path):
    out_json = tmp_path / "rc.json"
    out_md   = tmp_path / "rc.md"
    rc = srr.main([
        "--repo-root", str(REPO_ROOT),
        "--out-json", str(out_json),
        "--out-md",   str(out_md),
        "--pinned-time", "2026-05-18T13:00:00+00:00",
    ])
    parsed = json.loads(out_json.read_text())
    if parsed["rc_ready"]:
        assert rc == 0
    else:
        assert rc == 1


def test_cli_returns_2_on_missing_repo(srr, tmp_path):
    rc = srr.main([
        "--repo-root", str(tmp_path / "nope"),
        "--out-json", str(tmp_path / "x.json"),
        "--out-md", str(tmp_path / "x.md"),
        "--pinned-time", "2026-05-18T13:00:00+00:00",
    ])
    assert rc == 2


def test_render_markdown_has_all_sections(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    md = srr.render_markdown(report)
    for header in (
        "# Trinity V13 Release Candidate Report",
        "## Activation heights",
        "## Binary",
        "## Confirmed V13 items",
        "## Fallback V15 items",
        "## Docs present",
        "## Docs content checks",
        "## Public mirror",
        "## Warnings",
        "## Safety flags",
    ):
        assert header in md, "missing section: " + header
    assert "/tmp/" not in md


def test_markdown_no_html_no_js(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T13:00:00+00:00",
    )
    md = srr.render_markdown(report)
    assert "<script" not in md
    assert "javascript:" not in md
    assert "<html" not in md
    assert "<style" not in md
