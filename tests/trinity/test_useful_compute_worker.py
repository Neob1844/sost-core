"""Trinity / Useful Compute local-dry-run worker v0.1 — invariants."""

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
    return _load("ucw", SCRIPTS_DIR / "useful_compute_worker.py")


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_worker_test",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


def _make_request(builder_mod, *, task_type="scoring",
                  difficulty="medium", max_reward=100000):
    req = builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-test-1",
        input_bundle_bytes=b"hello-bundle",
        expected_output_schema=f"{task_type}-result/v0",
        difficulty_class=difficulty,
        max_reward_stocks=max_reward,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="test request",
    )
    # Force task_type after build (builder maps source→task by default).
    req = dict(req)
    req["task_type"] = task_type
    return req


def test_worker_runs_end_to_end_and_writes_two_files(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    result, pending = worker_mod.run_worker(
        request=req, worker_id="miner-test-001",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    rid = req["request_id"]
    wrid = result["worker_result_id"]
    res_path = (
        tmp_path / f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{wrid}.json"
    )
    rew_path = (
        tmp_path
        / f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.json"
    )
    assert res_path.exists()
    assert rew_path.exists()
    assert result["schema"] == "trinity-useful-compute-result/v0.3"
    assert pending["schema"] == \
        "trinity-useful-compute-pending-reward/v0.2"


def test_worker_output_byte_identical_across_runs(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    a = tmp_path / "a"
    b = tmp_path / "b"
    ra, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-x",
        out_dir=a, pinned_time="2026-05-12T00:00:00+00:00",
    )
    rb, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-x",
        out_dir=b, pinned_time="2026-05-12T00:00:00+00:00",
    )
    rid = req["request_id"]
    wrid_a = ra["worker_result_id"]
    wrid_b = rb["worker_result_id"]
    assert wrid_a == wrid_b
    assert (a / f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{wrid_a}.json").read_bytes() == \
           (b / f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{wrid_b}.json").read_bytes()
    assert (a / f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid_a}.json").read_bytes() == \
           (b / f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid_b}.json").read_bytes()


def test_worker_compute_output_sha_is_worker_independent(
    tmp_path, worker_mod, builder_mod,
):
    """Two honest workers running the same task on the same input
    MUST produce the same compute_output_sha256. This is the v0.2
    invariant that makes cross-worker replay possible."""
    req = _make_request(builder_mod)
    ra, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-A",
        out_dir=tmp_path / "a",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    rb, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-B",
        out_dir=tmp_path / "b",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert ra["compute_output_sha256"] == rb["compute_output_sha256"]


def test_worker_result_id_does_depend_on_worker_id(
    tmp_path, worker_mod, builder_mod,
):
    """worker_result_id is the per-submission id and MUST differ
    between two workers on the same task — that is how the network
    distinguishes their submissions."""
    req = _make_request(builder_mod)
    ra, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-A",
        out_dir=tmp_path / "a",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    rb, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-B",
        out_dir=tmp_path / "b",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert ra["worker_result_id"] != rb["worker_result_id"]


def test_worker_rejects_unknown_mode_via_cli(tmp_path, worker_mod):
    # argparse choices rejects `live` and calls sys.exit(2).
    with pytest.raises(SystemExit) as excinfo:
        worker_mod.main([
            "--mode", "live",
            "--request", str(tmp_path / "nope.json"),
            "--worker-id", "x",
            "--out-dir", str(tmp_path),
        ])
    assert excinfo.value.code != 0


def test_worker_rejects_payout_flag_via_cli(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--worker-id", "x",
        "--out-dir", str(tmp_path),
        "--payout",
    ])
    assert rc == 2


def test_worker_rejects_broadcast_flag_via_cli(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--worker-id", "x",
        "--out-dir", str(tmp_path),
        "--broadcast",
    ])
    assert rc == 2


def test_worker_rejects_wallet_flag_via_cli(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--worker-id", "x",
        "--out-dir", str(tmp_path),
        "--wallet", "/dev/null",
    ])
    assert rc == 2


def test_worker_rejects_invalid_request_schema(tmp_path, worker_mod):
    bad = {"schema": "other/v0", "request_id": "uc-deadbeefdeadbeef"}
    with pytest.raises(ValueError):
        worker_mod.run_worker(
            request=bad, worker_id="m",
            out_dir=tmp_path,
            pinned_time="2026-05-12T00:00:00+00:00",
        )


def test_worker_rejects_request_missing_required(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    del req["public_description"]
    with pytest.raises(ValueError):
        worker_mod.run_worker(
            request=req, worker_id="m",
            out_dir=tmp_path,
            pinned_time="2026-05-12T00:00:00+00:00",
        )


def test_worker_rejects_request_with_extra_keys(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req["secret_field"] = "x"
    with pytest.raises(ValueError, match="unknown"):
        worker_mod.run_worker(
            request=req, worker_id="m",
            out_dir=tmp_path,
            pinned_time="2026-05-12T00:00:00+00:00",
        )


def test_worker_reward_zero_when_duplicate(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    seen = tmp_path / "seen.txt"
    # First run records the output SHA.
    _, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="m",
        out_dir=tmp_path / "a",
        pinned_time="2026-05-12T00:00:00+00:00",
        seen_results=seen,
    )
    # Second run with the same (request, worker_id) hits the seen-set.
    _, pending = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="m",
        out_dir=tmp_path / "b",
        pinned_time="2026-05-12T00:00:00+00:00",
        seen_results=seen,
    )
    assert pending["pending_reward_stocks"] == 0
    assert "duplicate" in pending["reason"]


def test_worker_reward_respects_max_cap(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, difficulty="extreme",
                        max_reward=1000)
    _, pending = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert pending["pending_reward_stocks"] <= 1000


def test_worker_input_bundle_sha_mismatch_rejected(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    wrong = tmp_path / "wrong.bin"
    wrong.write_bytes(b"different-bytes")
    with pytest.raises(ValueError, match="sha256 mismatch"):
        worker_mod.run_worker(
            request=req, worker_id="m",
            out_dir=tmp_path,
            pinned_time="2026-05-12T00:00:00+00:00",
            input_bundle_path=wrong,
        )


def test_worker_handles_every_task_type(
    tmp_path, worker_mod, builder_mod,
):
    for tt in ("dft", "quantum", "structure_relaxation",
               "scoring", "simulation", "other"):
        req = _make_request(builder_mod, task_type=tt)
        res, _ = worker_mod.run_worker(
            request=req, worker_id="m",
            out_dir=tmp_path / tt,
            pinned_time="2026-05-12T00:00:00+00:00",
        )
        assert res["task_type"] == tt
        assert res["result_validated"] is True
        assert len(res["compute_output_sha256"]) == 64
        assert len(res["worker_result_id"]) == 16


def test_worker_cli_writes_files(tmp_path, worker_mod, builder_mod):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--worker-id", "miner-cli-001",
        "--out-dir", str(tmp_path),
        "--pinned-time", "2026-05-12T00:00:00+00:00",
    ])
    assert rc == 0
    rid = req["request_id"]
    res_files = list(
        tmp_path.glob(f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_*.json")
    )
    rew_files = list(
        tmp_path.glob(f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_*.json")
    )
    assert len(res_files) == 1
    assert len(rew_files) == 1


def test_worker_result_carries_all_safety_flags(
    tmp_path, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    res, _ = worker_mod.run_worker(
        request=req, worker_id="m",
        out_dir=tmp_path,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    ss = res["safety_status"]
    assert ss["no_wallet_access"] is True
    assert ss["no_private_keys"] is True
    assert ss["no_automatic_payout"] is True
    assert ss["no_network_required"] is True
    assert ss["manual_review_required"] is True


def test_worker_reward_zero_when_result_not_validated(worker_mod):
    """The reward model alone, exercised with result_validated=false,
    must return 0 regardless of the rest of the inputs."""
    reward_mod = _load(
        "ucrm_for_worker_test",
        SCRIPTS_DIR / "useful_compute_reward_model.py",
    )
    out = reward_mod.compute_pending_reward(
        task_id="t", worker_id="w",
        benchmark_score=9.0,
        verified_compute_seconds=3600.0,
        difficulty_class="extreme",
        result_validated=False,
        duplicate_result=False,
        max_reward_stocks=1000000,
    )
    assert out["pending_reward_stocks"] == 0
