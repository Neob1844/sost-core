"""Replay validator × backends — backend metadata enforcement."""

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
    return _load("ucw_be_rv", SCRIPTS_DIR / "useful_compute_worker.py")


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_be_rv", SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def validator_mod():
    return _load(
        "ucrv_be_rv",
        SCRIPTS_DIR / "useful_compute_replay_validator.py",
    )


def _make_request(builder_mod, task_type="scoring"):
    req = builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-be-rv",
        input_bundle_bytes=b"be-rv-bundle",
        expected_output_schema=f"{task_type}-result/v0",
        difficulty_class="medium",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="replay backend consistency test",
    )
    req = dict(req)
    req["task_type"] = task_type
    return req


def _run_workers(
    worker_mod, request, worker_ids, results_dir,
    backend_name="placeholder", allow_experimental=False,
):
    results_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for wid in worker_ids:
        res, _ = worker_mod.run_worker(
            request=copy.deepcopy(request),
            worker_id=wid,
            out_dir=results_dir,
            pinned_time="2026-05-12T00:00:00+00:00",
            backend_name=backend_name,
            allow_experimental_backends=allow_experimental,
        )
        out.append(res)
    return out


def test_two_workers_same_backend_accepted_with_backend_info(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "results"
    _run_workers(worker_mod, req, ["miner-A", "miner-B"], rd)
    report = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert report["validation_status"] == "accepted"
    assert report["accepted_backend_name"] == "placeholder_scoring"
    assert report["accepted_backend_version"] == "v0.1"


def test_two_workers_different_backends_become_mismatch(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    """Two workers using DIFFERENT backends produce DIFFERENT
    compute_output_sha256 — that already triggers mismatch through
    the existing path. This test confirms the validator does NOT
    accept that as a single backend group."""
    req = _make_request(builder_mod, "scoring")
    rd = tmp_path / "results"
    _run_workers(
        worker_mod, req, ["miner-A"], rd,
        backend_name="placeholder", allow_experimental=False,
    )
    _run_workers(
        worker_mod, req, ["miner-B"], rd,
        backend_name="local_python_numeric_v01",
        allow_experimental=True,
    )
    report = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert report["validation_status"] == "mismatch"
    assert report["accepted_backend_name"] is None
    assert report["accepted_backend_version"] is None
    assert report["manual_review_required"] is True


def test_three_workers_two_same_backend_one_different(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    """When a majority agrees on placeholder and one outlier uses
    a toy, the validator may declare mismatch (multiple
    compute_output_sha256 groups). The accepted_backend fields
    remain null."""
    req = _make_request(builder_mod, "scoring")
    rd = tmp_path / "results"
    _run_workers(
        worker_mod, req, ["miner-A", "miner-B"], rd,
        backend_name="placeholder",
    )
    _run_workers(
        worker_mod, req, ["miner-C"], rd,
        backend_name="local_python_numeric_v01",
        allow_experimental=True,
    )
    report = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    # Two groups by compute_output_sha256: validator's mismatch
    # branch fires before the backend-pair check.
    assert report["validation_status"] == "mismatch"


def test_accepted_validation_caches_first_matching_backend(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod, "structure_relaxation")
    rd = tmp_path / "results"
    _run_workers(
        worker_mod, req, ["miner-A", "miner-B", "miner-C"], rd,
        backend_name="local_structure_relaxation_toy_v01",
        allow_experimental=True,
    )
    report = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert report["validation_status"] == "accepted"
    assert report["accepted_backend_name"] == \
        "local_structure_relaxation_toy_v01"
    assert report["accepted_backend_version"] == "v0.1"


def test_v02_validation_schema_emitted(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "results"
    _run_workers(worker_mod, req, ["miner-A", "miner-B"], rd)
    report = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert report["schema"] == "trinity-useful-compute-validation/v0.2"


def test_governance_rejects_missing_backend(
    tmp_path, validator_mod,
):
    """If the validation report carries accepted=true but null
    backend fields, the governance gate rejects with
    governance_rejected_missing_backend."""
    gate_mod = _load(
        "ucg_be_rv",
        SCRIPTS_DIR / "useful_compute_governance_gate.py",
    )
    val_dir = tmp_path / "val"
    rewards_dir = tmp_path / "rew"
    val_dir.mkdir(); rewards_dir.mkdir()
    rid = "uc-" + "a" * 16
    vid = "val-" + "b" * 16
    val = {
        "schema": "trinity-useful-compute-validation/v0.2",
        "validation_id": vid,
        "request_id": rid,
        "mode": "local-dry-run",
        "min_workers": 2, "workers_seen": 2, "unique_workers": 2,
        "accepted_compute_output_sha256": "a" * 64,
        "accepted_backend_name": None,       # ← missing
        "accepted_backend_version": None,    # ← missing
        "validation_status": "accepted",
        "matching_result_ids": ["c" * 16, "d" * 16],
        "rejected_result_ids": [],
        "mismatch_groups": [],
        "manual_review_required": False,
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_network_required": True,
            "no_onchain_registration": True,
            "governance_required_before_payment": True,
        },
    }
    (val_dir / f"TRINITY_USEFUL_COMPUTE_VALIDATION_{rid}.json").write_text(
        json.dumps(val, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    reasons = [r["reason"] for r in batch["rejected_items"]]
    assert any("missing_backend" in r for r in reasons)


def test_governance_rejects_backend_mismatch_between_val_and_reward(
    tmp_path,
):
    """Hand-craft a v0.2 validation that declares one backend and a
    reward file that declares a different backend. The gate must
    reject with governance_rejected_backend_mismatch."""
    gate_mod = _load(
        "ucg_be_rv_mm",
        SCRIPTS_DIR / "useful_compute_governance_gate.py",
    )
    val_dir = tmp_path / "val"
    rewards_dir = tmp_path / "rew"
    val_dir.mkdir(); rewards_dir.mkdir()
    rid = "uc-" + "a" * 16
    vid = "val-" + "b" * 16
    wrid1 = "c" * 16
    wrid2 = "d" * 16
    val = {
        "schema": "trinity-useful-compute-validation/v0.2",
        "validation_id": vid, "request_id": rid,
        "mode": "local-dry-run",
        "min_workers": 2, "workers_seen": 2, "unique_workers": 2,
        "accepted_compute_output_sha256": "a" * 64,
        "accepted_backend_name":    "placeholder_dft",
        "accepted_backend_version": "v0.1",
        "validation_status": "accepted",
        "matching_result_ids": [wrid1, wrid2],
        "rejected_result_ids": [],
        "mismatch_groups": [],
        "manual_review_required": False,
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_network_required": True,
            "no_onchain_registration": True,
            "governance_required_before_payment": True,
        },
    }
    (val_dir / f"TRINITY_USEFUL_COMPUTE_VALIDATION_{rid}.json").write_text(
        json.dumps(val, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    # Two reward files: one with the right backend, one with a
    # different one.
    for wrid, bn in ((wrid1, "placeholder_dft"),
                     (wrid2, "local_dft_toy_v01")):
        rew = {
            "schema": "trinity-useful-compute-pending-reward/v0.3",
            "request_id": rid,
            "worker_id": "miner-" + wrid[:1],
            "worker_result_id": wrid,
            "pending_reward_stocks": 1000,
            "reason": "standard reward",
            "requires_manual_review": False,
            "reward_model_schema": "trinity-useful-compute-reward/v0.1",
            "reward_model_deterministic_id": "ff" * 8,
            "backend_name": bn,
            "backend_version": "v0.1",
            "backend_kind": "placeholder" if bn.startswith("placeholder")
                            else "sandbox_toy",
            "benchmark_id":          None,
            "normalized_work_score": None,
            "benchmark_source":      "none",
            "safety_status": {
                "no_wallet_access": True, "no_private_keys": True,
                "no_automatic_payout": True,
                "no_network_required": True,
                "manual_review_required": True,
            },
        }
        (rewards_dir / (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.json"
        )).write_text(
            json.dumps(rew, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    reasons = [r["reason"] for r in batch["rejected_items"]]
    assert any("backend_mismatch" in r for r in reasons)
