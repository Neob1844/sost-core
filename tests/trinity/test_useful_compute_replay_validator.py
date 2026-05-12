"""Trinity / Useful Compute cross-worker replay validator v0.1."""

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
    return _load("ucw_rv", SCRIPTS_DIR / "useful_compute_worker.py")


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_rv", SCRIPTS_DIR / "useful_compute_task_builder.py"
    )


@pytest.fixture(scope="module")
def validator_mod():
    return _load(
        "ucrv", SCRIPTS_DIR / "useful_compute_replay_validator.py"
    )


def _make_request(builder_mod, task_type="scoring"):
    req = builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-rv-1",
        input_bundle_bytes=b"rv-bundle",
        expected_output_schema=f"{task_type}-result/v0",
        difficulty_class="medium",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="replay validator test request",
    )
    req = dict(req)
    req["task_type"] = task_type
    return req


def _run_workers(worker_mod, request, worker_ids, results_dir):
    results_dir.mkdir(parents=True, exist_ok=True)
    out = []
    for wid in worker_ids:
        res, _ = worker_mod.run_worker(
            request=copy.deepcopy(request),
            worker_id=wid,
            out_dir=results_dir,
            pinned_time="2026-05-12T00:00:00+00:00",
        )
        out.append(res)
    return out


def test_two_honest_workers_accepted(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    results_dir = tmp_path / "results"
    _run_workers(worker_mod, req, ["miner-A", "miner-B"], results_dir)
    report = validator_mod.run_validation(
        request=req,
        results_dir=results_dir,
        out_dir=tmp_path / "out",
        min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert report["validation_status"] == "accepted"
    assert report["accepted_compute_output_sha256"] is not None
    assert len(report["matching_result_ids"]) == 2
    assert report["manual_review_required"] is False


def test_one_worker_insufficient(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    results_dir = tmp_path / "results"
    _run_workers(worker_mod, req, ["miner-A"], results_dir)
    report = validator_mod.run_validation(
        request=req, results_dir=results_dir,
        out_dir=tmp_path / "out", min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert report["validation_status"] == "insufficient_workers"
    assert report["unique_workers"] == 1


def test_two_workers_disagree_mismatch(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    results_dir = tmp_path / "results"
    workers = _run_workers(
        worker_mod, req, ["miner-A", "miner-B"], results_dir,
    )
    # Tamper miner-B's result on disk.
    rid = req["request_id"]
    wrid_b = workers[1]["worker_result_id"]
    rp = results_dir / (
        f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{wrid_b}.json"
    )
    d = json.loads(rp.read_text(encoding="utf-8"))
    d["compute_output_sha256"] = "d" * 64
    rp.write_text(
        json.dumps(d, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    report = validator_mod.run_validation(
        request=req, results_dir=results_dir,
        out_dir=tmp_path / "out", min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert report["validation_status"] == "mismatch"
    assert report["accepted_compute_output_sha256"] is None
    assert report["manual_review_required"] is True
    assert len(report["mismatch_groups"]) == 2


def test_duplicate_worker_rejected(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    results_dir = tmp_path / "results"
    # Run miner-A twice into the same dir — filenames differ because
    # worker_result_id is identical for the same (rid, wid, ...).
    # To actually produce two files with the same worker_id we copy
    # the result file to a distinct worker_result_id placeholder.
    res_a, _ = worker_mod.run_worker(
        request=copy.deepcopy(req), worker_id="miner-A",
        out_dir=results_dir,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    rid = req["request_id"]
    wrid_a = res_a["worker_result_id"]
    # Duplicate file: same worker_id, different worker_result_id.
    src_path = results_dir / (
        f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{wrid_a}.json"
    )
    d = json.loads(src_path.read_text(encoding="utf-8"))
    fake_wrid = "0" * 16
    d["worker_result_id"] = fake_wrid
    (results_dir / (
        f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{fake_wrid}.json"
    )).write_text(
        json.dumps(d, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    # Add one honest second miner.
    _run_workers(worker_mod, req, ["miner-B"], results_dir)
    report = validator_mod.run_validation(
        request=req, results_dir=results_dir,
        out_dir=tmp_path / "out", min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert any(
        "duplicate_worker_result" in r["reason"]
        for r in report["rejected_result_ids"]
    )
    # The honest pair (miner-A real submission + miner-B) still
    # qualifies for accepted.
    assert report["validation_status"] == "accepted"
    assert report["unique_workers"] == 2


def test_wrong_request_id_rejected(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    other_req = _make_request(builder_mod, task_type="dft")
    results_dir = tmp_path / "results"
    _run_workers(
        worker_mod, other_req, ["miner-Z"], results_dir,
    )
    report = validator_mod.run_validation(
        request=req, results_dir=results_dir,
        out_dir=tmp_path / "out", min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    # The miner-Z result lives in results_dir but its filename
    # contains other_req.request_id, so glob does not even find it.
    # That is the same outcome as "insufficient_workers".
    assert report["unique_workers"] == 0
    assert report["validation_status"] == "insufficient_workers"


def test_invalid_schema_rejected(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    results_dir = tmp_path / "results"
    results_dir.mkdir(parents=True)
    rid = req["request_id"]
    # Write a structurally broken file with the right name prefix.
    bad = {
        "schema": "trinity-useful-compute-result/v0.1",
        "request_id": rid,
        "worker_result_id": "ff" * 8,
    }
    (results_dir / (
        f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{'ff' * 8}.json"
    )).write_text(
        json.dumps(bad, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    report = validator_mod.run_validation(
        request=req, results_dir=results_dir,
        out_dir=tmp_path / "out", min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert len(report["rejected_result_ids"]) == 1
    # Either "wrong schema" or "missing fields" — both indicate the
    # structural validator caught a broken result. Sprint 5.8 fires
    # the missing-fields check first because the bad result has v0.1
    # schema string but is also missing required fields.
    reason = report["rejected_result_ids"][0]["reason"]
    assert ("wrong schema" in reason
            or "missing fields" in reason), reason
    # No surviving valid result.
    assert report["unique_workers"] == 0


def test_validation_report_byte_identical_with_reordered_inputs(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    rd_a = tmp_path / "ra"
    rd_b = tmp_path / "rb"
    _run_workers(worker_mod, req, ["miner-A", "miner-B"], rd_a)
    # Re-create same files but write them in reverse order by
    # copying. The validator should still produce identical canonical
    # report bytes because it sorts internally.
    rd_b.mkdir(parents=True)
    files = sorted(rd_a.glob("TRINITY_USEFUL_COMPUTE_RESULT_*.json"))
    for f in reversed(files):
        (rd_b / f.name).write_text(
            f.read_text(encoding="utf-8"), encoding="utf-8",
        )
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    ra = validator_mod.run_validation(
        request=req, results_dir=rd_a, out_dir=out_a, min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    rb = validator_mod.run_validation(
        request=req, results_dir=rd_b, out_dir=out_b, min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert validator_mod.canonical_dumps(ra) == \
        validator_mod.canonical_dumps(rb)


def test_validator_rejects_non_local_mode(tmp_path, validator_mod):
    with pytest.raises(SystemExit):
        validator_mod.main([
            "--mode", "live",
            "--request", str(tmp_path / "x.json"),
            "--results-dir", str(tmp_path),
            "--out-dir", str(tmp_path),
        ])


def test_validator_rejects_payout_flag(
    tmp_path, validator_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = validator_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--results-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--payout",
    ])
    assert rc == 2


def test_validator_rejects_broadcast_flag(
    tmp_path, validator_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = validator_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--results-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--broadcast",
    ])
    assert rc == 2


def test_validator_rejects_wallet_flag(
    tmp_path, validator_mod, builder_mod,
):
    req = _make_request(builder_mod)
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    rc = validator_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--results-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--wallet", "/dev/null",
    ])
    assert rc == 2


def test_min_workers_below_two_rejected(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    results_dir = tmp_path / "results"
    _run_workers(
        worker_mod, req, ["miner-A", "miner-B"], results_dir,
    )
    with pytest.raises(ValueError, match="min_workers"):
        validator_mod.run_validation(
            request=req, results_dir=results_dir,
            out_dir=tmp_path / "out", min_workers=1,
            pinned_time="2026-05-12T00:00:00+00:00",
        )


def test_safety_status_complete(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "rd"
    _run_workers(worker_mod, req, ["miner-A", "miner-B"], rd)
    rep = validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
    )
    ss = rep["safety_status"]
    for key in (
        "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_network_required",
        "no_onchain_registration",
        "governance_required_before_payment",
    ):
        assert ss[key] is True


def test_validator_records_lesson_on_mismatch(
    tmp_path, validator_mod, worker_mod, builder_mod,
):
    req = _make_request(builder_mod)
    rd = tmp_path / "rd"
    workers = _run_workers(worker_mod, req, ["miner-A", "miner-B"], rd)
    rid = req["request_id"]
    wrid_b = workers[1]["worker_result_id"]
    rp = rd / f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{wrid_b}.json"
    d = json.loads(rp.read_text(encoding="utf-8"))
    d["compute_output_sha256"] = "e" * 64
    rp.write_text(
        json.dumps(d, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    ledger = tmp_path / "errs.jsonl"
    validator_mod.run_validation(
        request=req, results_dir=rd, out_dir=tmp_path / "out",
        min_workers=2, pinned_time="2026-05-12T00:00:00+00:00",
        error_memory_ledger=ledger,
    )
    assert ledger.exists()
    text = ledger.read_text(encoding="utf-8")
    assert "overclaim_risk" in text
    assert "cross_worker_mismatch" in text
