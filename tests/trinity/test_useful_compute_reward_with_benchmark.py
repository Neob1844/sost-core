"""Trinity / Useful Compute reward model × benchmark integration."""

from __future__ import annotations

import copy
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
def reward_mod():
    return _load(
        "ucrm_bench",
        SCRIPTS_DIR / "useful_compute_reward_model.py",
    )


@pytest.fixture(scope="module")
def bench_mod():
    return _load(
        "ucb_bench_for_reward",
        SCRIPTS_DIR / "useful_compute_benchmark.py",
    )


@pytest.fixture(scope="module")
def worker_mod():
    return _load(
        "ucw_bench", SCRIPTS_DIR / "useful_compute_worker.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_bench", SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


_BASE = dict(
    task_id="t-1", worker_id="w-1",
    benchmark_score=1.0, verified_compute_seconds=10.0,
    difficulty_class="medium", result_validated=True,
    duplicate_result=False, max_reward_stocks=1000000,
)


def test_no_benchmark_keeps_old_behaviour(reward_mod):
    out = reward_mod.compute_pending_reward(**_BASE)
    assert out["pending_reward_stocks"] > 0
    assert "placeholder backend benchmark" not in out["reason"]
    assert "sandbox_toy backend benchmark" not in out["reason"]


def test_placeholder_benchmark_zeroes_reward(reward_mod):
    out = reward_mod.compute_pending_reward(
        **_BASE,
        normalized_work_score=4.0,
        backend_kind="placeholder",
    )
    assert out["pending_reward_stocks"] == 0
    assert "placeholder backend benchmark" in out["reason"]
    assert "zeroed by policy" in out["reason"]


def test_sandbox_toy_benchmark_keeps_reward_but_manual_review(reward_mod):
    out = reward_mod.compute_pending_reward(
        **_BASE,
        normalized_work_score=2.5,
        backend_kind="sandbox_toy",
    )
    assert out["pending_reward_stocks"] > 0
    assert out["requires_manual_review"] is True
    assert "sandbox_toy backend benchmark" in out["reason"]
    assert "experimental" in out["reason"].lower()


def test_real_backend_benchmark_forces_manual_review(reward_mod):
    out = reward_mod.compute_pending_reward(
        **_BASE,
        normalized_work_score=3.0,
        backend_kind="real_backend",
    )
    assert out["requires_manual_review"] is True
    assert "real_backend" in out["reason"]


def test_unknown_backend_kind_forces_manual_review(reward_mod):
    out = reward_mod.compute_pending_reward(
        **_BASE,
        normalized_work_score=3.0,
        backend_kind="quantum_dream",
    )
    assert out["requires_manual_review"] is True
    assert "unknown benchmark backend_kind" in out["reason"]


def test_max_reward_cap_still_enforced_with_benchmark(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "max_reward_stocks": 1000},
        normalized_work_score=10.0,
        backend_kind="sandbox_toy",
    )
    assert out["pending_reward_stocks"] <= 1000
    assert "max_reward_stocks cap" in out["reason"]


def test_normalized_work_score_overrides_benchmark_score(reward_mod):
    """When normalized_work_score is supplied, it replaces the
    caller-provided benchmark_score input."""
    lo = reward_mod.compute_pending_reward(
        **{**_BASE, "benchmark_score": 0.5},
        normalized_work_score=1.0,
        backend_kind="sandbox_toy",
    )
    hi = reward_mod.compute_pending_reward(
        **{**_BASE, "benchmark_score": 0.5},
        normalized_work_score=4.0,
        backend_kind="sandbox_toy",
    )
    assert hi["pending_reward_stocks"] > lo["pending_reward_stocks"]


def test_invalid_result_still_zero_with_benchmark(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "result_validated": False},
        normalized_work_score=4.0,
        backend_kind="sandbox_toy",
    )
    assert out["pending_reward_stocks"] == 0


def test_duplicate_still_zero_with_benchmark(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "duplicate_result": True},
        normalized_work_score=4.0,
        backend_kind="sandbox_toy",
    )
    assert out["pending_reward_stocks"] == 0


# ---------------------------------------------------------------------------
# Worker end-to-end with --benchmark-report
# ---------------------------------------------------------------------------


def _make_request(builder_mod, task_type="scoring"):
    req = builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-bench",
        input_bundle_bytes=b"bench-bundle",
        expected_output_schema=f"{task_type}-result/v0",
        difficulty_class="medium",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="bench worker test",
    )
    req = dict(req)
    req["task_type"] = task_type
    return req


def test_worker_accepts_valid_benchmark_report(
    tmp_path, worker_mod, builder_mod, bench_mod,
):
    req = _make_request(builder_mod, "scoring")
    bench = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=10, worker_id="miner-bench",
    )
    res, pending = worker_mod.run_worker(
        request=req, worker_id="miner-bench",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
        benchmark_report=bench,
    )
    assert res["benchmark_source"] == "report"
    assert res["benchmark_id"] == bench["benchmark_id"]
    assert res["normalized_work_score"] == bench["normalized_work_score"]
    # placeholder backend with benchmark → reward zeroed
    assert pending["pending_reward_stocks"] == 0
    assert pending["benchmark_source"] == "report"


def test_worker_rejects_invalid_benchmark_report(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "scoring")
    bad_bench = {"schema": "not-a-benchmark/v0"}
    with pytest.raises(ValueError, match="benchmark"):
        worker_mod.run_worker(
            request=req, worker_id="m",
            out_dir=tmp_path,
            pinned_time="2026-05-12T00:00:00+00:00",
            benchmark_report=bad_bench,
        )


def test_worker_without_benchmark_marks_source_none(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "scoring")
    res, pending = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert res["benchmark_source"] == "none"
    assert res["benchmark_id"] is None
    assert res["normalized_work_score"] is None
    assert pending["benchmark_source"] == "none"


def test_worker_toy_backend_with_benchmark_experimental(
    tmp_path, worker_mod, builder_mod, bench_mod,
):
    req = _make_request(builder_mod, "scoring")
    bench = bench_mod.run_benchmark(
        backend_name="local_python_numeric_v01",
        task_type="scoring",
        iterations=100, worker_id="miner-toy",
    )
    res, pending = worker_mod.run_worker(
        request=req, worker_id="miner-toy",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
        backend_name="local_python_numeric_v01",
        allow_experimental_backends=True,
        benchmark_report=bench,
    )
    assert res["benchmark_source"] == "report"
    assert res["backend_kind"] == "sandbox_toy"
    assert pending["pending_reward_stocks"] > 0
    assert pending["requires_manual_review"] is True
    assert "experimental" in pending["reason"].lower()
