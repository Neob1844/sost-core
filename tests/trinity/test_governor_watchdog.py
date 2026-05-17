"""Functional tests for the Trinity Governor Watchdog v0.1
(Sprint 5.25).

Strategy:
  - Use the real Autonomy Governor (Sprint 5.23 + 5.24) to produce
    decision JSONs in a tmp dir. No fixture files are committed
    under tests/trinity/fixtures/governor_decisions — the test
    builds the input from authoritative source on the fly so the
    decision schema and the watchdog parser cannot drift.
  - Run scripts/trinity/governor_watchdog.py over that dir and
    assert the report dict's counts, safety_status, redaction,
    and webhook double-gate behaviour.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
EXAMPLE_POLICY = REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gov():
    return _load(
        "autonomy_governor_wd", SCRIPTS_DIR / "autonomy_governor.py",
    )


@pytest.fixture(scope="module")
def wd():
    return _load(
        "governor_watchdog_wd", SCRIPTS_DIR / "governor_watchdog.py",
    )


PINNED = "2026-05-17T00:00:00+00:00"
EARLIER = "2026-05-16T00:00:00+00:00"


def _write_policy(tmp_path, mutate=None):
    base = json.loads(EXAMPLE_POLICY.read_text(encoding="utf-8"))
    if mutate is not None:
        base = mutate(base)
    p = tmp_path / "policy.json"
    p.write_text(json.dumps(base, indent=2), encoding="utf-8")
    return p


def _emit_decisions(gov, policy_path, out_dir, steps, pinned=EARLIER):
    """Use the Governor's evaluate_decision() helper to emit one
    pipeline_step decision per entry in `steps`."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for step in steps:
        d = gov.evaluate_decision(
            policy_path=policy_path,
            action="pipeline_step",
            action_params={"step_name": step},
            pinned_time=pinned,
            out_dir=out_dir,
        )
        paths.append(Path(d["_decision_path"]))
    return paths


# ---------------------------------------------------------------------------
# Happy path: 7 allowed decisions, safety_status=ok
# ---------------------------------------------------------------------------


def test_scan_all_allowed_returns_ok(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    steps = [
        "task_builder", "worker", "replay_validator",
        "governance_gate", "reward_budget_policy",
        "payment_proposal", "payment_draft",
    ]
    _emit_decisions(gov, policy, dec_dir, steps)
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    assert report["schema"] == "trinity-governor-watchdog-report/v0.1"
    assert report["decisions_seen"] == 7
    assert report["allowed_count"] == 7
    assert report["blocked_count"] == 0
    assert report["malformed_count"] == 0
    assert report["policy_mutation_detected_count"] == 0
    assert report["halt_detected_count"] == 0
    assert report["safety_status"] == "ok"
    assert report["stale"] is False
    assert report["actions_seen"] == ["pipeline_step"]
    assert report["threat_refs_seen"] == ["T15", "T16", "T17"]
    assert len(report["decision_ids"]) == 7
    assert report["decision_ids"] == sorted(report["decision_ids"])


# ---------------------------------------------------------------------------
# Critical: halt_file present in one decision
# ---------------------------------------------------------------------------


def test_scan_halt_decision_is_critical(tmp_path, gov, wd):
    halt = tmp_path / "HALT"
    halt.write_text("stop")
    policy = _write_policy(
        tmp_path, lambda b: {**b, "kill_switch": {**b["kill_switch"],
        "halt_file": str(halt)}},
    )
    dec_dir = tmp_path / "governor_decisions"
    # Decisions emitted while HALT exists will all carry
    # blocked_reason=halt_file_present.
    _emit_decisions(gov, policy, dec_dir, ["task_builder", "worker"])
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    assert report["decisions_seen"] == 2
    assert report["halt_detected_count"] == 2
    assert report["blocked_count"] == 2
    assert report["allowed_count"] == 0
    assert report["safety_status"] == "critical"


# ---------------------------------------------------------------------------
# Critical: policy_mutated_at_runtime
# ---------------------------------------------------------------------------


def test_scan_policy_mutation_is_critical(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    boot_sha, _ = gov.pin_policy(policy)
    # Mutate the policy AFTER pinning, then ask the Governor to
    # decide with the original boot sha. The decision will be
    # blocked with policy_mutated_at_runtime.
    mutated = json.loads(policy.read_text(encoding="utf-8"))
    mutated["allowlists"]["rpc_methods"].append("getmempoolinfo")
    policy.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
    dec_dir = tmp_path / "governor_decisions"
    gov.evaluate_decision(
        policy_path=policy,
        action="pipeline_step",
        action_params={"step_name": "task_builder"},
        pinned_time=EARLIER,
        boot_policy_sha256=boot_sha,
        out_dir=dec_dir,
    )
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    assert report["decisions_seen"] == 1
    assert report["policy_mutation_detected_count"] == 1
    assert report["blocked_count"] == 1
    assert report["safety_status"] == "critical"
    # The watchdog warns about the mismatched policy_hashes_match.
    assert any(
        "policy_hashes_match=false" in w for w in report["warnings"]
    )


# ---------------------------------------------------------------------------
# Warning: malformed decision file
# ---------------------------------------------------------------------------


def test_scan_malformed_decision_is_warning(tmp_path, wd):
    dec_dir = tmp_path / "governor_decisions"
    dec_dir.mkdir()
    # Three malformed forms: invalid JSON, wrong schema, missing fields.
    (dec_dir / "TRINITY_AUTONOMY_GOVERNOR_DECISION_bad1.json").write_text(
        "{this is not json", encoding="utf-8",
    )
    (dec_dir / "TRINITY_AUTONOMY_GOVERNOR_DECISION_bad2.json").write_text(
        json.dumps({"schema": "trinity-other/v0.1"}), encoding="utf-8",
    )
    (dec_dir / "TRINITY_AUTONOMY_GOVERNOR_DECISION_bad3.json").write_text(
        json.dumps({
            "schema": "trinity-autonomy-governor-decision/v0.1",
            "decision_id": "abc",
        }),
        encoding="utf-8",
    )
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=PINNED,
        max_age_seconds=3600,
    )
    assert report["decisions_seen"] == 3
    assert report["malformed_count"] == 3
    assert report["allowed_count"] == 0
    assert report["safety_status"] == "warning"
    assert any("malformed" in w for w in report["warnings"])


# ---------------------------------------------------------------------------
# Stale: newest decision older than max_age_seconds
# ---------------------------------------------------------------------------


def test_scan_stale_when_newest_decision_too_old(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir, ["task_builder"], pinned=EARLIER)
    # PINNED is one day after EARLIER → 86400s. max_age=3600s ⇒ stale.
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=PINNED,
        max_age_seconds=3600,
    )
    assert report["decisions_seen"] == 1
    assert report["allowed_count"] == 1
    assert report["stale"] is True
    assert report["newest_decision_age_seconds"] == 86400
    assert report["safety_status"] == "stale"
    assert any("exceeds max_age_seconds" in w for w in report["warnings"])


def test_scan_empty_dir_is_stale(tmp_path, wd):
    dec_dir = tmp_path / "governor_decisions"
    dec_dir.mkdir()
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=PINNED,
        max_age_seconds=3600,
    )
    assert report["decisions_seen"] == 0
    assert report["stale"] is True
    assert report["safety_status"] == "stale"
    assert any("no decisions found" in w for w in report["warnings"])


# ---------------------------------------------------------------------------
# Hard refusal: denylisted path segments
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seg", ["wallets", "secrets", ".git", ".ssh"])
def test_scan_refuses_denylisted_decisions_dir(tmp_path, wd, seg):
    dec_dir = tmp_path / seg / "governor_decisions"
    dec_dir.mkdir(parents=True)
    with pytest.raises(wd.WatchdogError) as ei:
        wd.scan_decisions(
            decisions_dir=dec_dir,
            pinned_time=PINNED,
            max_age_seconds=3600,
        )
    assert "denylisted segment" in str(ei.value)


def test_write_refuses_denylisted_out_dir(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir, ["task_builder"])
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    bad_out = tmp_path / "wallets" / "out"
    with pytest.raises(wd.WatchdogError) as ei:
        wd.write_report(report, bad_out)
    assert "denylisted segment" in str(ei.value)


# ---------------------------------------------------------------------------
# Read-only: scan must not modify the input files
# ---------------------------------------------------------------------------


def test_scan_does_not_modify_decision_files(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    paths = _emit_decisions(gov, policy, dec_dir,
                            ["task_builder", "worker", "replay_validator"])
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in paths}
    assert before == after


# ---------------------------------------------------------------------------
# Webhook double-gate: configured without --send is a no-op
# ---------------------------------------------------------------------------


def test_webhook_configured_without_send_does_not_dispatch(
    tmp_path, gov, wd,
):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir, ["task_builder"])
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
        webhook_url="https://watchdog.example.com/secret/path?token=AAA",
        send=False,
    )
    assert report["webhook_configured"] is True
    assert report["webhook_sent"] is False
    assert report["webhook_status"] == "skipped_no_send"
    # Path and query are redacted; only scheme+host survive.
    assert report["webhook_url_redacted"] == "https://watchdog.example.com"
    assert "secret" not in report["webhook_url_redacted"]
    assert "token" not in report["webhook_url_redacted"]


def test_webhook_send_v01_still_does_not_dispatch(tmp_path, gov, wd):
    """v0.1 contract: even with --send the watchdog does NOT fetch
    the URL. webhook_sent stays false; webhook_status records the
    deliberate v0.1 skip; a warning is appended."""
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir, ["task_builder"])
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
        webhook_url="https://watchdog.example.com/x",
        send=True,
    )
    assert report["webhook_configured"] is True
    assert report["webhook_sent"] is False
    assert report["webhook_status"] == "sent_skipped_v01"
    assert any(
        "v0.1 declines to fetch webhook" in w for w in report["warnings"]
    )


def test_webhook_not_configured(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir, ["task_builder"])
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    assert report["webhook_configured"] is False
    assert report["webhook_url_redacted"] is None
    assert report["webhook_status"] == "not_configured"


# ---------------------------------------------------------------------------
# Determinism: same input → same report_id
# ---------------------------------------------------------------------------


def test_report_id_deterministic_across_runs(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir,
                    ["task_builder", "worker"], pinned=EARLIER)
    r1 = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    r2 = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time=EARLIER,
        max_age_seconds=3600,
    )
    assert r1["report_id"] == r2["report_id"]
    assert r1["decision_ids"] == r2["decision_ids"]


# ---------------------------------------------------------------------------
# CLI integration: main() writes a report file and exits 0
# ---------------------------------------------------------------------------


def test_cli_main_happy_path(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir,
                    ["task_builder", "worker"], pinned=EARLIER)
    out_dir = tmp_path / "watchdog_out"
    rc = wd.main([
        "--decisions-dir", str(dec_dir),
        "--out-dir", str(out_dir),
        "--pinned-time", EARLIER,
    ])
    assert rc == 0
    files = list(out_dir.glob("TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json"))
    assert len(files) == 1
    report = json.loads(files[0].read_text(encoding="utf-8"))
    assert report["safety_status"] == "ok"
    assert report["decisions_seen"] == 2
    assert report["webhook_sent"] is False


def test_cli_main_missing_decisions_dir_returns_2(tmp_path, wd):
    rc = wd.main([
        "--decisions-dir", str(tmp_path / "does_not_exist"),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", PINNED,
    ])
    assert rc == 2


def test_cli_main_loads_config_file(tmp_path, gov, wd):
    policy = _write_policy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit_decisions(gov, policy, dec_dir, ["task_builder"], pinned=EARLIER)
    cfg = tmp_path / "wd.json"
    cfg.write_text(json.dumps({
        "max_age_seconds": 60,
    }), encoding="utf-8")
    out_dir = tmp_path / "watchdog_out"
    rc = wd.main([
        "--decisions-dir", str(dec_dir),
        "--out-dir", str(out_dir),
        "--pinned-time", PINNED,
        "--config", str(cfg),
    ])
    assert rc == 0
    files = list(out_dir.glob("TRINITY_GOVERNOR_WATCHDOG_REPORT_*.json"))
    assert len(files) == 1
    report = json.loads(files[0].read_text(encoding="utf-8"))
    # max_age_seconds from config applied → stale=True (>60s gap).
    assert report["max_age_seconds"] == 60
    assert report["stale"] is True
    assert report["safety_status"] == "stale"
