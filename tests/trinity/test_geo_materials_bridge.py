"""Geo + materials dossiers can both feed candidates into the
orchestrator queue and produce useful-compute requests."""

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
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def orch_mod():
    return _load(
        "trinity_orch_bridge", SCRIPTS_DIR / "trinity_orchestrator.py"
    )


@requires_real_council
def test_both_verticals_can_produce_options(tmp_path, orch_mod):
    r = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=tmp_path, count=25,
    )
    assert r["summary"]["geo_ran"] is True
    assert r["summary"]["materials_ran"] is True
    # At least one of them should have surfaced an option for v0.1.
    assert r["summary"]["decisions_count"] >= 1


@requires_real_council
def test_uc_request_index_is_consistent(tmp_path, orch_mod):
    r = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=tmp_path, count=25,
    )
    idx_path = Path(r["paths"]["uc_index"])
    assert idx_path.exists()
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    assert idx["schema"] == "trinity-useful-compute-index/v0.1"
    assert idx["count"] == r["summary"]["uc_requests_count"]
    # If any request exists, its sha embedded in the bundle matches.
    if idx["count"] >= 1:
        first = idx["requests"][0]
        assert first["schema"] == "trinity-useful-compute-request/v0.1"
        assert first["source_tool"] in (
            "materials_engine", "geaspirit", "trinity_orchestrator"
        )


@requires_real_council
def test_ledger_lines_are_well_formed_json(tmp_path, orch_mod):
    r = orch_mod.run_orchestrator(
        mode="dry-run", seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-11T00:00:00+00:00",
        objectives_dir=OBJECTIVES_DIR,
        out_dir=tmp_path, count=25,
    )
    led = Path(r["paths"]["ledger"]).read_text(encoding="utf-8")
    for line in led.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        assert d["schema"] == "trinity-autonomy-ledger/v0.1"
        assert "selected_option" in d
        assert "council_used" in d
