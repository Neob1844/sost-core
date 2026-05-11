"""Trinity Autonomous Orchestrator v0.1 — determinism + safety status."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from conftest import requires_real_council


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
OBJECTIVES_DIR = REPO_ROOT / "config" / "trinity" / "objectives"


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def orch_mod():
    return _load(
        "trinity_orch", SCRIPTS_DIR / "trinity_orchestrator.py"
    )


@requires_real_council
def test_orchestrator_byte_identical_across_runs(tmp_path, orch_mod):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=a, count=25,
    )
    rb = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=b, count=25,
    )
    assert ra["deterministic_run_id"] == rb["deterministic_run_id"]
    assert ra["shas"]["bundle"] == rb["shas"]["bundle"]
    assert ra["shas"]["ledger"] == rb["shas"]["ledger"]
    assert ra["shas"]["uc_request_idx"] == rb["shas"]["uc_request_idx"]
    assert ra["shas"]["objectives"] == rb["shas"]["objectives"]


@requires_real_council
def test_orchestrator_seed_change_changes_bundle(tmp_path, orch_mod):
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra = orch_mod.run_orchestrator(
        mode="dry-run", seed="seed-A",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR, out_dir=a, count=25,
    )
    rb = orch_mod.run_orchestrator(
        mode="dry-run", seed="seed-B",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR, out_dir=b, count=25,
    )
    assert ra["deterministic_run_id"] != rb["deterministic_run_id"]
    assert ra["shas"]["bundle"] != rb["shas"]["bundle"]


@requires_real_council
def test_bundle_carries_safety_status_invariants(tmp_path, orch_mod):
    r = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR, out_dir=tmp_path, count=25,
    )
    bundle = json.loads(
        Path(r["paths"]["bundle"]).read_text(encoding="utf-8")
    )
    ss = bundle["safety_status"]
    assert ss["dry_run"] is True
    assert ss["registered"] is False
    assert ss["ready_to_register"] is False
    assert ss["no_rewards_active"] is True
    assert ss["no_paid_providers"] is True
    assert ss["no_network_calls"] is True


def test_orchestrator_rejects_non_dry_run_mode(tmp_path, orch_mod):
    with pytest.raises(ValueError, match="dry-run"):
        orch_mod.run_orchestrator(
            mode="live", seed="x",
            pinned_time="2026-05-11T00:00:00+00:00",
            objectives_dir=OBJECTIVES_DIR, out_dir=tmp_path, count=5,
        )


def test_load_objectives_requires_all_four(tmp_path, orch_mod):
    # Empty dir → missing all four
    with pytest.raises(FileNotFoundError):
        orch_mod.load_objectives(tmp_path)
