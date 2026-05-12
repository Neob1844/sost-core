"""Worker × backends — CLI flags, defaults, refusals."""

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
def worker_mod():
    return _load("ucw_be", SCRIPTS_DIR / "useful_compute_worker.py")


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_be", SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


def _make_request(builder_mod, task_type="scoring"):
    req = builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-be",
        input_bundle_bytes=b"be-bundle",
        expected_output_schema=f"{task_type}-result/v0",
        difficulty_class="medium",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="worker backend test",
    )
    req = dict(req)
    req["task_type"] = task_type
    return req


def test_default_backend_remains_placeholder(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "dft")
    res, pending = worker_mod.run_worker(
        request=req, worker_id="miner-default",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert res["backend_kind"] == "placeholder"
    assert res["backend_name"] == "placeholder_dft"
    assert res["backend_version"] == "v0.1"
    assert pending["backend_kind"] == "placeholder"
    assert pending["backend_name"] == "placeholder_dft"


def test_experimental_backend_rejected_by_default(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "dft")
    with pytest.raises(ValueError, match="experimental"):
        worker_mod.run_worker(
            request=req, worker_id="miner-x",
            out_dir=tmp_path,
            pinned_time="2026-05-12T00:00:00+00:00",
            backend_name="local_dft_toy_v01",
            allow_experimental_backends=False,
        )


def test_experimental_backend_accepted_with_flag(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "dft")
    res, pending = worker_mod.run_worker(
        request=req, worker_id="miner-x",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
        backend_name="local_dft_toy_v01",
        allow_experimental_backends=True,
    )
    assert res["backend_kind"] == "sandbox_toy"
    assert res["backend_name"] == "local_dft_toy_v01"
    assert pending["backend_kind"] == "sandbox_toy"


def test_compute_hash_worker_independent_with_toy_backend(
    tmp_path, worker_mod, builder_mod,
):
    """Sprint 5.8 invariant must survive the toy backend swap."""
    req = _make_request(builder_mod, "structure_relaxation")
    ra, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-A",
        out_dir=tmp_path / "a",
        pinned_time="2026-05-12T00:00:00+00:00",
        backend_name="local_structure_relaxation_toy_v01",
        allow_experimental_backends=True,
    )
    rb, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-B",
        out_dir=tmp_path / "b",
        pinned_time="2026-05-12T00:00:00+00:00",
        backend_name="local_structure_relaxation_toy_v01",
        allow_experimental_backends=True,
    )
    assert ra["compute_output_sha256"] == rb["compute_output_sha256"]
    assert ra["worker_result_id"] != rb["worker_result_id"]
    assert ra["backend_name"] == rb["backend_name"]
    assert ra["backend_version"] == rb["backend_version"]


def test_compute_hash_differs_between_placeholder_and_toy(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "structure_relaxation")
    placeholder, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-1",
        out_dir=tmp_path / "p",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    toy, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-1",
        out_dir=tmp_path / "t",
        pinned_time="2026-05-12T00:00:00+00:00",
        backend_name="local_structure_relaxation_toy_v01",
        allow_experimental_backends=True,
    )
    # Different implementations almost certainly produce different
    # bytes. If this ever coincides, it is a one-in-2^256 event we
    # want to know about.
    assert placeholder["compute_output_sha256"] != \
        toy["compute_output_sha256"]


def test_result_carries_backend_runtime_seconds_field(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "scoring")
    res, _ = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert "backend_runtime_seconds" in res
    assert isinstance(res["backend_runtime_seconds"], (int, float))
    # placeholder runtime is pinned to 0.0
    assert res["backend_runtime_seconds"] == 0.0


def test_pending_reward_v02_carries_backend(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "scoring")
    _, pending = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert pending["schema"] == \
        "trinity-useful-compute-pending-reward/v0.3"
    assert "backend_name" in pending
    assert "backend_version" in pending
    assert "backend_kind" in pending
    assert "worker_result_id" in pending


def test_cli_default_backend_runs_clean(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--worker-id", "miner-cli-default",
        "--out-dir", str(tmp_path),
        "--pinned-time", "2026-05-12T00:00:00+00:00",
    ])
    assert rc == 0


def test_cli_experimental_without_flag_returns_2(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "scoring")
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--worker-id", "miner-cli-toy",
        "--out-dir", str(tmp_path),
        "--pinned-time", "2026-05-12T00:00:00+00:00",
        "--backend", "local_python_numeric_v01",
    ])
    assert rc == 2


def test_cli_experimental_with_flag_returns_0(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "scoring")
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--worker-id", "miner-cli-toy-ok",
        "--out-dir", str(tmp_path),
        "--pinned-time", "2026-05-12T00:00:00+00:00",
        "--backend", "local_python_numeric_v01",
        "--allow-experimental-backends",
    ])
    assert rc == 0


def test_result_disclaimer_present(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "dft")
    res, _ = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
        backend_name="local_dft_toy_v01",
        allow_experimental_backends=True,
    )
    low = res["backend_disclaimer"].lower()
    assert "not a real" in low or "not real" in low
    # Worker result MUST NOT claim scientific validation in
    # public_summary either.
    assert "not real scientific" in res["public_summary"].lower() \
        or "deterministic" in res["public_summary"].lower()
