"""Schema tests for the Trinity Governor Watchdog v0.1 report.

Validates:
  - the report schema is a valid draft-07 schema
  - the schema declares the v0.1 id and the safety_status enum
  - decision_ids items match ^[a-f0-9]{32}$
  - threat_refs_seen items match ^T[0-9]{2}$
  - webhook_sent is locked const false in v0.1
  - reports produced by scripts/trinity/governor_watchdog.py
    validate against the schema in all four safety_status states
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "governor_watchdog_report.schema.json"
)
EXAMPLE_POLICY = (
    REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"
)


def _load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def wd():
    return _load_mod(
        "governor_watchdog_sch", SCRIPTS_DIR / "governor_watchdog.py",
    )


@pytest.fixture(scope="module")
def gov():
    return _load_mod(
        "autonomy_governor_sch", SCRIPTS_DIR / "autonomy_governor.py",
    )


# ---------------------------------------------------------------------------
# Schema self-consistency
# ---------------------------------------------------------------------------


def test_report_schema_loads_as_valid_draft07(schema):
    jsonschema.Draft7Validator.check_schema(schema)


def test_report_schema_declares_v01_id(schema):
    assert schema.get("$id") == "trinity-governor-watchdog-report/v0.1"


def test_report_schema_safety_status_enum_has_four_values(schema):
    enum = schema["properties"]["safety_status"]["enum"]
    assert set(enum) == {"ok", "warning", "stale", "critical"}


def test_report_schema_webhook_sent_locked_false(schema):
    """v0.1 must never claim to have sent a webhook. The const lock
    fails CI the moment somebody flips webhook_sent=true without
    bumping the schema to v0.2."""
    assert schema["properties"]["webhook_sent"]["const"] is False


def test_report_schema_decision_ids_pattern_is_32hex(schema):
    item = schema["properties"]["decision_ids"]["items"]
    assert item["pattern"] == "^[a-f0-9]{32}$"


def test_report_schema_threat_refs_pattern_is_T_pattern(schema):
    item = schema["properties"]["threat_refs_seen"]["items"]
    assert item["pattern"] == "^T[0-9]{2}$"


def test_report_schema_webhook_status_enum(schema):
    enum = schema["properties"]["webhook_status"]["enum"]
    assert set(enum) == {
        "not_configured", "skipped_no_send", "sent_skipped_v01",
    }


# ---------------------------------------------------------------------------
# End-to-end: real watchdog reports validate
# ---------------------------------------------------------------------------


def _emit(gov, policy_path, out_dir, steps, pinned):
    for step in steps:
        gov.evaluate_decision(
            policy_path=policy_path,
            action="pipeline_step",
            action_params={"step_name": step},
            pinned_time=pinned,
            out_dir=out_dir,
        )


def _write_policy_copy(tmp_path):
    p = tmp_path / "policy.json"
    p.write_text(EXAMPLE_POLICY.read_text(encoding="utf-8"), encoding="utf-8")
    return p


def test_ok_report_validates(schema, gov, wd, tmp_path):
    policy = _write_policy_copy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit(gov, policy, dec_dir, ["task_builder", "worker"],
          "2026-05-16T00:00:00+00:00")
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time="2026-05-16T00:00:00+00:00",
        max_age_seconds=3600,
    )
    jsonschema.validate(report, schema)
    assert report["safety_status"] == "ok"


def test_critical_report_validates(schema, gov, wd, tmp_path):
    halt = tmp_path / "HALT"
    halt.write_text("stop")
    base = json.loads(EXAMPLE_POLICY.read_text(encoding="utf-8"))
    base["kill_switch"]["halt_file"] = str(halt)
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(base, indent=2), encoding="utf-8")
    dec_dir = tmp_path / "governor_decisions"
    _emit(gov, policy, dec_dir, ["task_builder"],
          "2026-05-16T00:00:00+00:00")
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time="2026-05-16T00:00:00+00:00",
        max_age_seconds=3600,
    )
    jsonschema.validate(report, schema)
    assert report["safety_status"] == "critical"


def test_warning_report_validates(schema, wd, tmp_path):
    dec_dir = tmp_path / "governor_decisions"
    dec_dir.mkdir()
    (dec_dir / "TRINITY_AUTONOMY_GOVERNOR_DECISION_bad.json").write_text(
        "{not json", encoding="utf-8",
    )
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time="2026-05-17T00:00:00+00:00",
        max_age_seconds=3600,
    )
    jsonschema.validate(report, schema)
    assert report["safety_status"] == "warning"


def test_stale_report_validates(schema, gov, wd, tmp_path):
    policy = _write_policy_copy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit(gov, policy, dec_dir, ["task_builder"],
          "2026-05-16T00:00:00+00:00")
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time="2026-05-17T00:00:00+00:00",
        max_age_seconds=3600,
    )
    jsonschema.validate(report, schema)
    assert report["safety_status"] == "stale"


def test_webhook_redacted_validates(schema, gov, wd, tmp_path):
    policy = _write_policy_copy(tmp_path)
    dec_dir = tmp_path / "governor_decisions"
    _emit(gov, policy, dec_dir, ["task_builder"],
          "2026-05-16T00:00:00+00:00")
    report = wd.scan_decisions(
        decisions_dir=dec_dir,
        pinned_time="2026-05-16T00:00:00+00:00",
        max_age_seconds=3600,
        webhook_url="https://wd.example.com/secret?t=AAA",
        send=False,
    )
    jsonschema.validate(report, schema)
    assert report["webhook_url_redacted"] == "https://wd.example.com"
    assert report["webhook_sent"] is False
