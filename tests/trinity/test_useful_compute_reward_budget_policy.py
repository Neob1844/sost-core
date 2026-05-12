"""Trinity / Useful Compute reward budget policy v0.1 — invariants."""

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
def budget_mod():
    return _load(
        "ucrbp", SCRIPTS_DIR / "useful_compute_reward_budget_policy.py",
    )


def _gov_batch(*, batch_id, request_id, approved_per_worker,
               worker_ids, validation_id="val-" + "b" * 16):
    return {
        "schema": "trinity-useful-compute-governance-batch/v0.1",
        "batch_id": batch_id,
        "mode": "local-dry-run",
        "reviewer_id": "reviewer-test",
        "policy": "conservative",
        "created_at": "2026-05-12T00:00:00+00:00",
        "approved_count": 1,
        "rejected_count": 0,
        "total_approved_reward_stocks":
            approved_per_worker * len(worker_ids),
        "approved_items": [{
            "request_id": request_id,
            "validation_id": validation_id,
            "accepted_compute_output_sha256": "a" * 64,
            "matching_result_ids": list(worker_ids),
            "unique_workers": len(worker_ids),
            "approved_pending_reward_stocks": approved_per_worker,
            "reason": "test",
        }],
        "rejected_items": [],
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_broadcast": True,
            "no_onchain_registration": True,
            "governance_review_only": True,
            "requires_separate_payment_sprint": True,
        },
    }


def _write_gov(tmp_path: Path, batch: dict) -> Path:
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir(parents=True, exist_ok=True)
    fp = gov_dir / (
        f"TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_{batch['batch_id']}.json"
    )
    fp.write_text(
        json.dumps(batch, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return gov_dir


# ---------------------------------------------------------------------------
# Effective budget math
# ---------------------------------------------------------------------------


def test_daily_budget_is_min_of_fraction_and_fixed_cap(
    tmp_path, budget_mod,
):
    """Pool=10**12 stocks * 0.0001 = 10**8 = fixed cap."""
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=1000,
        worker_ids=["c" * 16, "d" * 16],
    ))
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    assert plan["effective_daily_budget_stocks"] == 100_000_000
    assert plan["effective_epoch_budget_stocks"] == 1_000_000_000


def test_small_pool_shrinks_daily_budget(tmp_path, budget_mod):
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=1000,
        worker_ids=["c" * 16, "d" * 16],
    ))
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=100_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    # 100_000 * 0.0001 = 10
    assert plan["effective_daily_budget_stocks"] == 10
    # 100_000 * 0.001 = 100
    assert plan["effective_epoch_budget_stocks"] == 100


# ---------------------------------------------------------------------------
# Cap stack
# ---------------------------------------------------------------------------


def test_worker_cap_limits_per_worker_reward(tmp_path, budget_mod):
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        # 5_000_000 / worker is above the 2_000_000 default.
        approved_per_worker=5_000_000,
        worker_ids=["c" * 16],
    ))
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    a = plan["allocation_items"][0]
    assert a["allocated_stocks"] == 2_000_000
    assert "capped_by_worker" in a["cap_reason"]
    assert a["allocation_status"] in (
        "capped_by_worker", "capped_by_job",
    )


def test_job_cap_limits_total_per_request(tmp_path, budget_mod):
    """3 workers × 2_000_000 = 6_000_000 > max_job_reward_stocks
    (5_000_000) → scaled down."""
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=2_000_000,
        worker_ids=["c" * 16, "d" * 16, "e" * 16],
    ))
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    a = plan["allocation_items"][0]
    assert a["allocated_stocks"] <= 5_000_000
    assert "capped_by_job" in a["cap_reason"]


def test_daily_cap_defers_excess(tmp_path, budget_mod):
    """Pool=100_000 → daily=10. Requested=135_000 → most deferred."""
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=45_000,
        worker_ids=["c" * 16, "d" * 16, "e" * 16],
    ))
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=100_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    a = plan["allocation_items"][0]
    assert a["allocated_stocks"] < a["requested_stocks"]
    assert a["deferred_stocks"] > 0
    assert "capped_by_daily" in a["cap_reason"]


def test_zero_pool_balance_rejected(tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir(parents=True)
    with pytest.raises(ValueError, match="pool_balance_stocks"):
        budget_mod.run_budget_policy(
            pool_balance_stocks=0,
            governance_dir=gov_dir,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            epoch_id="ep-1",
        )


def test_negative_pool_balance_rejected(tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir(parents=True)
    with pytest.raises(ValueError, match="pool_balance_stocks"):
        budget_mod.run_budget_policy(
            pool_balance_stocks=-1,
            governance_dir=gov_dir,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            epoch_id="ep-1",
        )


def test_unknown_policy_rejected(tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir(parents=True)
    with pytest.raises(ValueError, match="policy"):
        budget_mod.run_budget_policy(
            pool_balance_stocks=1_000_000_000_000,
            governance_dir=gov_dir,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            epoch_id="ep-1",
            policy="aggressive",
        )


# ---------------------------------------------------------------------------
# 70/20/10 split
# ---------------------------------------------------------------------------


def test_shares_sum_to_allocated(tmp_path, budget_mod):
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=1000,
        worker_ids=["c" * 16, "d" * 16, "e" * 16],
    ))
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    a = plan["allocation_items"][0]
    total = (
        a["primary_workers_share_stocks"]
        + a["replay_validator_reserve_stocks"]
        + a["governance_review_reserve_stocks"]
    )
    assert total == a["allocated_stocks"]


def test_full_allocation_split_70_20_10(tmp_path, budget_mod):
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=10_000,
        worker_ids=["c" * 16, "d" * 16, "e" * 16],
    ))
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    a = plan["allocation_items"][0]
    assert a["allocated_stocks"] == 30_000
    assert a["primary_workers_share_stocks"] == 21_000
    assert a["replay_validator_reserve_stocks"] == 6_000
    assert a["governance_review_reserve_stocks"] == 3_000


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_budget_id_byte_identical_across_runs(tmp_path, budget_mod):
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=1000,
        worker_ids=["c" * 16, "d" * 16],
    ))
    a = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out_a",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    b = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out_b",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    assert a["budget_id"] == b["budget_id"]
    assert budget_mod.canonical_dumps(a) == \
        budget_mod.canonical_dumps(b)


def test_epoch_change_changes_budget_id(tmp_path, budget_mod):
    gov_dir = _write_gov(tmp_path, _gov_batch(
        batch_id="gov-" + "1" * 16,
        request_id="uc-" + "a" * 16,
        approved_per_worker=1000,
        worker_ids=["c" * 16, "d" * 16],
    ))
    a = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out_a",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    b = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out_b",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-2",
    )
    assert a["budget_id"] != b["budget_id"]


# ---------------------------------------------------------------------------
# Bad input
# ---------------------------------------------------------------------------


def test_invalid_governance_schema_rejected(tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir(parents=True)
    (gov_dir / "TRINITY_USEFUL_COMPUTE_GOVERNANCE_BATCH_gov-bad.json").write_text(
        json.dumps({"schema": "wrong/v0", "batch_id": "gov-" + "0" * 16}),
        encoding="utf-8",
    )
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    statuses = [a["allocation_status"]
                for a in plan["allocation_items"]]
    assert "rejected" in statuses


def test_empty_governance_dir_yields_empty_plan(tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir(parents=True)
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    assert plan["allocation_items"] == []
    assert plan["total_allocated_stocks"] == 0


# ---------------------------------------------------------------------------
# CLI safety
# ---------------------------------------------------------------------------


def test_cli_rejects_non_local_mode(tmp_path, budget_mod):
    with pytest.raises(SystemExit):
        budget_mod.main([
            "--mode", "live",
            "--pool-balance-stocks", "1000000",
            "--governance-dir", str(tmp_path),
            "--out-dir", str(tmp_path),
        ])


def test_cli_rejects_payout(tmp_path, budget_mod):
    rc = budget_mod.main([
        "--mode", "local-dry-run",
        "--pool-balance-stocks", "1000000",
        "--governance-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--payout",
    ])
    assert rc == 2


def test_cli_rejects_broadcast(tmp_path, budget_mod):
    rc = budget_mod.main([
        "--mode", "local-dry-run",
        "--pool-balance-stocks", "1000000",
        "--governance-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--broadcast",
    ])
    assert rc == 2


def test_cli_rejects_wallet(tmp_path, budget_mod):
    rc = budget_mod.main([
        "--mode", "local-dry-run",
        "--pool-balance-stocks", "1000000",
        "--governance-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--wallet", "/dev/null",
    ])
    assert rc == 2


def test_cli_rejects_network(tmp_path, budget_mod):
    rc = budget_mod.main([
        "--mode", "local-dry-run",
        "--pool-balance-stocks", "1000000",
        "--governance-dir", str(tmp_path),
        "--out-dir", str(tmp_path),
        "--network",
    ])
    assert rc == 2


def test_cli_writes_budget_file(tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir()
    rc = budget_mod.main([
        "--mode", "local-dry-run",
        "--pool-balance-stocks", "1000000000000",
        "--governance-dir", str(gov_dir),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-12T00:00:00+00:00",
        "--epoch-id", "ep-cli",
    ])
    assert rc == 0
    files = list(
        (tmp_path / "out").glob(
            "TRINITY_USEFUL_COMPUTE_REWARD_BUDGET_*.json"
        )
    )
    assert len(files) == 1


# ---------------------------------------------------------------------------
# Safety status
# ---------------------------------------------------------------------------


def test_safety_status_const_true(tmp_path, budget_mod):
    gov_dir = tmp_path / "governance"
    gov_dir.mkdir()
    plan = budget_mod.run_budget_policy(
        pool_balance_stocks=1_000_000_000_000,
        governance_dir=gov_dir,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        epoch_id="ep-1",
    )
    for flag in (
        "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_broadcast",
        "budget_only", "requires_separate_payment_sprint",
    ):
        assert plan["safety_status"][flag] is True
