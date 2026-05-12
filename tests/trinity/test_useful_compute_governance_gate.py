"""Trinity / Useful Compute governance gate v0.1 — invariants."""

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
    return _load("ucw_gov", SCRIPTS_DIR / "useful_compute_worker.py")


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_gov", SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def validator_mod():
    return _load(
        "ucrv_gov", SCRIPTS_DIR / "useful_compute_replay_validator.py",
    )


@pytest.fixture(scope="module")
def gate_mod():
    return _load(
        "ucgov", SCRIPTS_DIR / "useful_compute_governance_gate.py",
    )


def _make_request(builder_mod, task_type="scoring"):
    req = builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-gov-test",
        input_bundle_bytes=b"gov-bundle",
        expected_output_schema=f"{task_type}-result/v0",
        difficulty_class="medium",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="governance gate test request",
    )
    req = dict(req)
    req["task_type"] = task_type
    return req


def _setup_full_pipeline(
    tmp_path, worker_mod, builder_mod, validator_mod,
    worker_ids=("miner-A", "miner-B"),
    tamper_last=False,
    drop_last_reward=False,
    duplicate_last_reward=False,
):
    """Generate a request, run N workers, run the validator, return
    (request, results_dir, validations_dir)."""
    req = _make_request(builder_mod)
    results_dir = tmp_path / "results"
    val_dir = tmp_path / "validations"
    val_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    workers = []
    for wid in worker_ids:
        res, _ = worker_mod.run_worker(
            request=copy.deepcopy(req), worker_id=wid,
            out_dir=results_dir,
            pinned_time="2026-05-12T00:00:00+00:00",
        )
        workers.append(res)

    if tamper_last:
        rid = req["request_id"]
        wrid = workers[-1]["worker_result_id"]
        rp = results_dir / (
            f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{wrid}.json"
        )
        d = json.loads(rp.read_text(encoding="utf-8"))
        d["compute_output_sha256"] = "d" * 64
        rp.write_text(
            json.dumps(d, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    if drop_last_reward:
        rid = req["request_id"]
        wrid = workers[-1]["worker_result_id"]
        (results_dir / (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.json"
        )).unlink()

    if duplicate_last_reward:
        rid = req["request_id"]
        wrid = workers[-1]["worker_result_id"]
        src = results_dir / (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.json"
        )
        dup_wrid = "0" * 16
        dup = results_dir / (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{dup_wrid}.json"
        )
        dup.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        # Also produce another file with the same (rid, wrid_actual)
        # so the duplicate detector fires for the *real* wrid.
        same = results_dir / (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.copy.json"
        )
        # Note: same filename pattern won't match the regex with .copy;
        # the strict duplicate case is two files matching the regex
        # with the same (rid, wrid). We achieve that by writing a second
        # file using exact same canonical name pretending another path:
        same_real = results_dir / (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{wrid}.json.dup"
        )
        same_real.write_text(src.read_text(encoding="utf-8"),
                             encoding="utf-8")

    validator_mod.run_validation(
        request=req, results_dir=results_dir,
        out_dir=val_dir, min_workers=2,
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    return req, results_dir, val_dir


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_accepted_validation_with_matching_rewards_approved(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B", "miner-C"),
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir,
        rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov",
        reviewer_id="reviewer-test-001",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert batch["approved_count"] == 1
    assert batch["rejected_count"] == 0
    assert batch["total_approved_reward_stocks"] > 0
    item = batch["approved_items"][0]
    assert item["request_id"] == req["request_id"]
    assert item["unique_workers"] == 3
    assert "conservative=min" in item["reason"]


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


def test_mismatch_validation_rejected(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
        tamper_last=True,
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert batch["approved_count"] == 0
    assert batch["rejected_count"] >= 1
    reasons = [r["reason"] for r in batch["rejected_items"]]
    assert any("governance_rejected_mismatch" in r for r in reasons)


def test_insufficient_workers_rejected(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A",),
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert batch["approved_count"] == 0
    reasons = [r["reason"] for r in batch["rejected_items"]]
    assert any(
        "insufficient_workers" in r for r in reasons
    )


def test_manual_review_required_rejected(
    tmp_path, gate_mod, builder_mod,
):
    """Build a hand-crafted validation report with
    manual_review_required=true and verify it is rejected."""
    val_dir = tmp_path / "validations"
    rewards_dir = tmp_path / "rewards"
    val_dir.mkdir()
    rewards_dir.mkdir()
    rid = "uc-" + "a" * 16
    vid = "val-" + "b" * 16
    val = {
        "schema": "trinity-useful-compute-validation/v0.2",
        "validation_id": vid,
        "request_id": rid,
        "mode": "local-dry-run",
        "min_workers": 2, "workers_seen": 2, "unique_workers": 2,
        "accepted_compute_output_sha256": "a" * 64,
        "accepted_backend_name":    "placeholder_other",
        "accepted_backend_version": "v0.1",
        "validation_status": "accepted",
        "matching_result_ids": ["c" * 16, "d" * 16],
        "rejected_result_ids": [],
        "mismatch_groups": [],
        "manual_review_required": True,  # ← forces rejection
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
    assert batch["approved_count"] == 0
    reasons = [r["reason"] for r in batch["rejected_items"]]
    assert any("manual_review" in r for r in reasons)


def test_missing_reward_rejected(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
        drop_last_reward=True,
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert batch["approved_count"] == 0
    reasons = [r["reason"] for r in batch["rejected_items"]]
    assert any("missing_reward" in r for r in reasons)


def test_extra_reward_not_in_matching_rejected(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    """Add a pending reward whose worker_result_id is NOT in the
    validation's matching_result_ids."""
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
    )
    # Synthesize an extra reward file with a fake wrid.
    rid = req["request_id"]
    fake_wrid = "f" * 16
    extra = {
        "schema": "trinity-useful-compute-pending-reward/v0.3",
        "request_id": rid,
        "worker_id": "miner-Z",
        "worker_result_id": "f" * 16,
        "pending_reward_stocks": 999999,
        "reason": "standard reward",
        "requires_manual_review": False,
        "reward_model_schema": "trinity-useful-compute-reward/v0.1",
        "reward_model_deterministic_id": "deadbeefcafebabe",
        "backend_name":    "placeholder_structure_relaxation",
        "backend_version": "v0.1",
        "backend_kind":    "placeholder",
        "benchmark_id":          None,
        "normalized_work_score": None,
        "benchmark_source":      "none",
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_network_required": True,
            "manual_review_required": True,
        },
    }
    (rewards_dir / (
        f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{fake_wrid}.json"
    )).write_text(
        json.dumps(extra, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    # The "honest" pair still gets approved because the extra reward
    # is for a different wrid.
    reasons = [r["reason"] for r in batch["rejected_items"]]
    assert any(
        "governance_rejected_extra_reward" in r for r in reasons
    )


# ---------------------------------------------------------------------------
# Policy + determinism + totals
# ---------------------------------------------------------------------------


def test_conservative_policy_uses_min(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    """Manually rewrite two reward files so they hold different
    pending_reward_stocks. Conservative policy must pick the minimum."""
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
    )
    rid = req["request_id"]
    # Find the two reward files and rewrite their stocks.
    rew_files = sorted(rewards_dir.glob(
        f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_*.json"
    ))
    assert len(rew_files) == 2
    stocks_values = [10000, 30000]  # min should win => 10000
    for p, s in zip(rew_files, stocks_values):
        d = json.loads(p.read_text(encoding="utf-8"))
        d["pending_reward_stocks"] = s
        p.write_text(
            json.dumps(d, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert batch["approved_count"] == 1
    assert batch["approved_items"][0]["approved_pending_reward_stocks"] == 10000
    assert batch["total_approved_reward_stocks"] == 10000


def test_total_approved_reward_stocks_correct(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    total = sum(
        i["approved_pending_reward_stocks"]
        for i in batch["approved_items"]
    )
    assert batch["total_approved_reward_stocks"] == total


def test_batch_byte_identical_across_input_orderings(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
    )
    # Run gate twice with two different out_dirs.
    ra = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "out_a", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    rb = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "out_b", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    assert gate_mod.canonical_dumps(ra) == gate_mod.canonical_dumps(rb)


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


def test_safety_status_complete(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
    )
    batch = gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    ss = batch["safety_status"]
    for k in (
        "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_broadcast",
        "no_onchain_registration", "governance_review_only",
        "requires_separate_payment_sprint",
    ):
        assert ss[k] is True


def test_gate_rejects_non_local_mode(tmp_path, gate_mod):
    with pytest.raises(SystemExit):
        gate_mod.main([
            "--mode", "live",
            "--validations-dir", str(tmp_path),
            "--rewards-dir", str(tmp_path),
            "--out-dir", str(tmp_path),
            "--reviewer-id", "x",
        ])


def test_gate_rejects_payout_flag(tmp_path, gate_mod):
    rc = gate_mod.main([
        "--mode", "local-dry-run",
        "--validations-dir", str(tmp_path),
        "--rewards-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--reviewer-id", "x",
        "--payout",
    ])
    assert rc == 2


def test_gate_rejects_broadcast_flag(tmp_path, gate_mod):
    rc = gate_mod.main([
        "--mode", "local-dry-run",
        "--validations-dir", str(tmp_path),
        "--rewards-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--reviewer-id", "x",
        "--broadcast",
    ])
    assert rc == 2


def test_gate_rejects_wallet_flag(tmp_path, gate_mod):
    rc = gate_mod.main([
        "--mode", "local-dry-run",
        "--validations-dir", str(tmp_path),
        "--rewards-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--reviewer-id", "x",
        "--wallet", "/dev/null",
    ])
    assert rc == 2


def test_gate_rejects_unknown_policy(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
    )
    with pytest.raises(ValueError, match="policy"):
        gate_mod.run_governance_gate(
            validations_dir=val_dir, rewards_dir=rewards_dir,
            out_dir=tmp_path / "gov", reviewer_id="r",
            policy="aggressive",  # not allowed in v0.1
            pinned_time="2026-05-12T00:00:00+00:00",
        )


def test_gate_records_lessons_into_error_memory(
    tmp_path, worker_mod, builder_mod, validator_mod, gate_mod,
):
    req, rewards_dir, val_dir = _setup_full_pipeline(
        tmp_path, worker_mod, builder_mod, validator_mod,
        worker_ids=("miner-A", "miner-B"),
        tamper_last=True,
    )
    ledger = tmp_path / "errs.jsonl"
    gate_mod.run_governance_gate(
        validations_dir=val_dir, rewards_dir=rewards_dir,
        out_dir=tmp_path / "gov", reviewer_id="r",
        policy="conservative",
        pinned_time="2026-05-12T00:00:00+00:00",
        error_memory_ledger=ledger,
    )
    assert ledger.exists()
    text = ledger.read_text(encoding="utf-8")
    assert "governance_rejected_mismatch" in text
