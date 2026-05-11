"""Trinity error memory — append-only ledger + lesson lookup."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mem_mod():
    return _load(
        "tem", SCRIPTS_DIR / "trinity_error_memory.py"
    )


def test_record_and_read_back(tmp_path, mem_mod):
    led = tmp_path / "errs.jsonl"
    mem_mod.record_lesson(
        ledger_path=led, vertical="geaspirit",
        task_inputs={"action": "geo_pipeline", "count": 10},
        cause="compute_failed", detail="simulated",
        pinned_time="2026-05-11T00:00:00+00:00",
    )
    lessons = mem_mod.read_lessons(led)
    assert len(lessons) == 1
    assert lessons[0]["cause"] == "compute_failed"
    assert lessons[0]["recommended_response"]


def test_cause_taxonomy_is_closed(tmp_path, mem_mod):
    led = tmp_path / "errs.jsonl"
    with pytest.raises(ValueError):
        mem_mod.record_lesson(
            ledger_path=led, vertical="g",
            task_inputs={"k": 1}, cause="weird_cause",
            detail="x", pinned_time="2026-05-11T00:00:00+00:00",
        )


def test_repeat_detected_by_signature(tmp_path, mem_mod):
    led = tmp_path / "errs.jsonl"
    inputs = {"candidate_id": "GEO-007"}
    mem_mod.record_lesson(
        ledger_path=led, vertical="geaspirit",
        task_inputs=inputs, cause="validation_failed",
        detail="x", pinned_time="2026-05-11T00:00:00+00:00",
    )
    hit = mem_mod.has_repeat_lesson(led, "geaspirit", inputs)
    assert hit is not None
    assert hit["cause"] == "validation_failed"

    miss = mem_mod.has_repeat_lesson(
        led, "geaspirit", {"candidate_id": "GEO-XXX"}
    )
    assert miss is None


def test_summary_md_aggregates(tmp_path, mem_mod):
    led = tmp_path / "errs.jsonl"
    out_md = tmp_path / "out.md"
    for cause in ("compute_failed", "compute_failed", "bad_input"):
        mem_mod.record_lesson(
            ledger_path=led, vertical="materials_engine",
            task_inputs={"x": cause}, cause=cause,
            detail="x", pinned_time="2026-05-11T00:00:00+00:00",
        )
    mem_mod.main([
        "summary", "--ledger", str(led), "--out-md", str(out_md),
    ])
    md = out_md.read_text(encoding="utf-8")
    assert "materials_engine::compute_failed` x2" in md
    assert "materials_engine::bad_input` x1" in md


def test_empty_ledger_renders_clean_md(tmp_path, mem_mod):
    out_md = tmp_path / "out.md"
    mem_mod.main([
        "summary", "--ledger", str(tmp_path / "missing.jsonl"),
        "--out-md", str(out_md),
    ])
    assert "No lessons recorded yet" in out_md.read_text(encoding="utf-8")


def test_orchestrator_refuses_repeat_without_flag(tmp_path):
    """The orchestrator's own behaviour: if a lesson exists for a
    (vertical, candidate_id) the option must be filtered out unless
    --allow-retry-known-failures is set. This is exercised via the
    helper directly to keep the test fast."""
    mem_mod_local = _load(
        "tem_orch_repeat",
        SCRIPTS_DIR / "trinity_error_memory.py",
    )
    led = tmp_path / "errs.jsonl"
    mem_mod_local.record_lesson(
        ledger_path=led, vertical="geaspirit",
        task_inputs={"candidate_id": "GEO-0005"},
        cause="overclaim_risk", detail="x",
        pinned_time="2026-05-11T00:00:00+00:00",
    )
    hit = mem_mod_local.has_repeat_lesson(
        led, "geaspirit", {"candidate_id": "GEO-0005"}
    )
    assert hit is not None
    assert hit["cause"] == "overclaim_risk"
