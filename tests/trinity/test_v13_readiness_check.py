"""Functional tests for Sprint V13 readiness check script."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_readiness_check.py"
CONFIG = REPO_ROOT / "config" / "v13_activation.json"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_readiness_report.schema.json"
)


def _import_script():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v13_readiness_check", str(SCRIPT),
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


def test_config_schema_id():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["schema"] == "trinity-v13-activation-config/v0.1"


def test_config_activation_heights():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    h = cfg["activation_heights"]
    assert h["v13_activation_height"]       == 12000
    assert h["v15_fallback_height"]         == 15000
    assert h["dtd_lottery_decision_height"] == 12100


def test_config_confirmed_items_present():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    ids = sorted(c["id"] for c in cfg["confirmed_items"])
    assert ids == sorted([
        "casert_all_profiles_e7_h35",
        "dtd_cooldown_6",
        "timestamp_drift_10s",
        "beacon_phase_ii_a",
    ])


def test_config_gated_items_present():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    ids = sorted(g["id"] for g in cfg["gated_items"])
    assert ids == sorted([
        "popc_model_a_b",
        "beacon_phase_ii_b",
        "beacon_phase_iii",
        "memory_lock_per_instance",
    ])


def test_popc_has_seven_gates():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    popc = next(g for g in cfg["gated_items"] if g["id"] == "popc_model_a_b")
    assert len(popc["gates"]) == 7
    ids = sorted(x["id"] for x in popc["gates"])
    assert ids == sorted([
        "popc_a_audit_daemon",
        "popc_b_auto_slash",
        "popc_c_auto_settlement",
        "popc_d_escrow_deployment",
        "popc_e_event_listener",
        "popc_f_consensus_gate",
        "popc_g_e2e_test",
    ])


def test_config_safety_invariants():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    sa = cfg["safety_invariants"]
    # Beacon invariants.
    b = sa["beacon"]
    assert b["may_inform"] is True
    assert b["may_restart"] is False
    assert b["may_block"] is False
    assert b["may_change_consensus"] is False
    assert b["may_execute_commands"] is False
    # Script invariants.
    s = sa["readiness_check_script"]
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
    ):
        assert s[flag] is True, "flag: " + flag


def test_report_validates_against_schema(srr, schema):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    jsonschema.validate(report, schema)


def test_report_top_level_shape(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    assert report["schema"] == "trinity-v13-readiness-report/v0.1"
    assert re.match(r"^v13rr-[0-9a-f]{16}$", report["report_id"])
    assert report["activation_heights"]["v13_activation_height"] == 12000
    assert report["activation_heights"]["v15_fallback_height"]   == 15000
    assert (
        report["activation_heights"]["dtd_lottery_decision_height"] == 12100
    )


def test_safety_flags_all_const_true(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
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
        assert report["safety_flags"][flag] is True, "flag: " + flag


def test_confirmed_items_inspected(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    ids = sorted(c["id"] for c in report["confirmed_items"])
    assert ids == sorted([
        "casert_all_profiles_e7_h35",
        "dtd_cooldown_6",
        "timestamp_drift_10s",
        "beacon_phase_ii_a",
    ])


def test_casert_all_profiles_is_wired(srr):
    """After the V13 cASERT wire commit, the checker must detect
    the validator_profile_ceiling_at / effective_profile_ceiling_at
    helpers or the CASERT_MAX_ACTIVE_PROFILE_V13 constant."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    by_id = {c["id"]: c for c in report["confirmed_items"]}
    assert by_id["casert_all_profiles_e7_h35"]["wired_in_code"] is True


def test_v13_ready_for_confirmed_items_is_true(srr):
    """All four confirmed items must be wired in code after the
    V13 cASERT commit. This is the gating boolean for cutting the
    V13 binary."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    assert report["v13_ready_for_confirmed_items"] is True


def test_dtd_cooldown_is_wired(srr):
    """The DTD cooldown 5->6 helper is already in params.h on the
    current commit. The checker must detect it."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    by_id = {c["id"]: c for c in report["confirmed_items"]}
    assert by_id["dtd_cooldown_6"]["wired_in_code"] is True


def test_timestamp_drift_is_wired(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    by_id = {c["id"]: c for c in report["confirmed_items"]}
    assert by_id["timestamp_drift_10s"]["wired_in_code"] is True


def test_beacon_phase_ii_a_is_wired(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    by_id = {c["id"]: c for c in report["confirmed_items"]}
    assert by_id["beacon_phase_ii_a"]["wired_in_code"] is True


def test_popc_gates_block_if_anything_missing(srr):
    """PoPC must fall back to V15 if any of the 7 gates fails.
    On the current main, none of the daemons / event listeners /
    consensus gate / e2e tests are present, so popc_v13_ready
    must be false."""
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    popc = next(
        g for g in report["gated_items"] if g["id"] == "popc_model_a_b"
    )
    assert popc["v13_ready"] is False
    assert popc["resolved_activation_height"] == 15000
    # And it must show up in fallback list.
    assert "popc_model_a_b" in report["fallback_to_v15_items"]
    assert report["popc_v13_ready"] is False


def test_gated_resolved_height_is_either_12000_or_15000(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    for g in report["gated_items"]:
        assert g["resolved_activation_height"] in (12000, 15000)


def test_overall_decision_enum(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    assert report["overall_decision"] in (
        "v13_confirmed_items_ready_gated_items_fallback_to_v15",
        "v13_all_ready",
        "v13_confirmed_items_not_ready_block_fork",
        "indeterminate",
    )


def test_report_deterministic(srr):
    """Same inputs => same report_id (deterministic hash)."""
    r1 = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    r2 = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    assert r1["report_id"] == r2["report_id"]
    assert r1["v13_ready_for_confirmed_items"] == (
        r2["v13_ready_for_confirmed_items"]
    )


def test_cli_writes_json_and_md(srr, tmp_path):
    out_json = tmp_path / "v13.json"
    out_md   = tmp_path / "v13.md"
    rc = srr.main([
        "--repo-root", str(REPO_ROOT),
        "--out-json", str(out_json),
        "--out-md",   str(out_md),
        "--pinned-time", "2026-05-18T00:30:00+00:00",
    ])
    # rc is 0 or 1 depending on confirmed-items state; both are
    # acceptable here. We only require both output files exist
    # and json validates against the schema.
    assert rc in (0, 1)
    assert out_json.is_file()
    assert out_md.is_file()
    parsed = json.loads(out_json.read_text())
    assert parsed["schema"] == "trinity-v13-readiness-report/v0.1"


def test_cli_returns_2_on_missing_repo(srr, tmp_path):
    rc = srr.main([
        "--repo-root", str(tmp_path / "nope"),
        "--out-json",  str(tmp_path / "x.json"),
        "--out-md",    str(tmp_path / "x.md"),
        "--pinned-time", "2026-05-18T00:30:00+00:00",
    ])
    assert rc == 2


def test_render_markdown_has_all_sections(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    md = srr.render_markdown(report)
    for header in (
        "# Trinity V13 Activation Readiness Report",
        "## Activation heights",
        "## Confirmed V13 items",
        "## Gated items (V13 target, V15 fallback)",
        "## Item-level decisions",
        "## Fallback to V15",
        "## Warnings",
        "## Safety flags",
    ):
        assert header in md, "missing section: " + header
    assert "/tmp/" not in md


def test_markdown_no_html_no_js(srr):
    report = srr.build_report(
        repo_root=REPO_ROOT,
        pinned_time="2026-05-18T00:30:00+00:00",
    )
    md = srr.render_markdown(report)
    assert "<script" not in md
    assert "javascript:" not in md
    assert "<html" not in md
    assert "<style" not in md
