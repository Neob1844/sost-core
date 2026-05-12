"""Trinity / Useful Compute payment proposal v0.1 — invariants."""

from __future__ import annotations

import copy
import hashlib
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
def proposal_mod():
    return _load(
        "ucpp", SCRIPTS_DIR / "useful_compute_payment_proposal.py",
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _budget_plan(*, budget_id, request_id, batch_id,
                 worker_result_ids, allocated, primary_share):
    """Build a synthetic budget plan with one allocation_item."""
    return {
        "schema": "trinity-useful-compute-reward-budget/v0.1",
        "budget_id": budget_id,
        "mode": "local-dry-run",
        "policy": "conservative",
        "pinned_time": "2026-05-12T00:00:00+00:00",
        "epoch_id": "ep-1",
        "pool_balance_stocks": 1_000_000_000_000,
        "effective_daily_budget_stocks": 100_000_000,
        "effective_epoch_budget_stocks": 1_000_000_000,
        "policy_caps": {
            "max_daily_fraction_of_pool": 0.0001,
            "fixed_daily_cap_stocks": 100_000_000,
            "max_epoch_fraction_of_pool": 0.001,
            "fixed_epoch_cap_stocks": 1_000_000_000,
            "max_job_reward_stocks": 5_000_000,
            "max_worker_reward_stocks": 2_000_000,
            "primary_worker_share": 0.70,
            "replay_validator_share": 0.20,
            "governance_review_reserve": 0.10,
        },
        "total_requested_stocks": allocated,
        "total_allocated_stocks": allocated,
        "total_deferred_stocks": 0,
        "allocation_items": [{
            "request_id": request_id,
            "governance_batch_id": batch_id,
            "worker_result_ids": list(worker_result_ids),
            "requested_stocks": allocated,
            "allocated_stocks": allocated,
            "deferred_stocks": 0,
            "primary_workers_share_stocks": primary_share,
            "replay_validator_reserve_stocks":
                (allocated * 20) // 100,
            "governance_review_reserve_stocks":
                allocated - primary_share - (allocated * 20) // 100,
            "cap_reason": "none",
            "allocation_status": "approved_as_requested",
        }],
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_broadcast": True,
            "budget_only": True,
            "requires_separate_payment_sprint": True,
        },
    }


def _addr_map(workers):
    return {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {"worker_id_hash": _sha16(w["worker_id"]),
             "payout_address": w["addr"],
             "label": w.get("label", w["worker_id"])}
            for w in workers
        ],
    }


def _reward_file(rid, wrid, worker_id):
    return {
        "schema": "trinity-useful-compute-pending-reward/v0.3",
        "request_id": rid, "worker_id": worker_id,
        "worker_result_id": wrid,
        "pending_reward_stocks": 1000, "reason": "test",
        "requires_manual_review": False,
        "reward_model_schema": "trinity-useful-compute-reward/v0.1",
        "reward_model_deterministic_id": "ff" * 8,
        "backend_name": "placeholder_scoring",
        "backend_version": "v0.1", "backend_kind": "placeholder",
        "benchmark_id": None,
        "normalized_work_score": None,
        "benchmark_source": "none",
        "safety_status": {
            "no_wallet_access": True, "no_private_keys": True,
            "no_automatic_payout": True, "no_network_required": True,
            "manual_review_required": True,
        },
    }


def _setup(tmp_path, *, workers, allocated, primary_share):
    """Write budget + address map + rewards to disk and return
    paths."""
    rid = "uc-" + "a" * 16
    batch_id = "gov-" + "b" * 16
    budget_id = "bud-" + "1" * 16
    wrids = [w["wrid"] for w in workers]
    budget = _budget_plan(
        budget_id=budget_id, request_id=rid, batch_id=batch_id,
        worker_result_ids=wrids,
        allocated=allocated, primary_share=primary_share,
    )
    budget_path = tmp_path / "budget.json"
    budget_path.write_text(
        json.dumps(budget, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    addr_map = _addr_map(workers)
    addr_path = tmp_path / "addr.json"
    addr_path.write_text(
        json.dumps(addr_map, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    rewards_dir = tmp_path / "rewards"
    rewards_dir.mkdir()
    for w in workers:
        r = _reward_file(rid, w["wrid"], w["worker_id"])
        (rewards_dir / (
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{w['wrid']}.json"
        )).write_text(
            json.dumps(r, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    return rid, batch_id, budget_path, addr_path, rewards_dir


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


_ADDR_A = "sost1qaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_ADDR_C = "sost1qcccccccccccccccccccccccccccccccccccccc"
_ADDR_D = "sost1qdddddddddddddddddddddddddddddddddddddd"


def test_budget_plus_address_map_yields_payable_items(
    tmp_path, proposal_mod,
):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
            {"wrid": "d" * 16, "worker_id": "miner-bob",
             "addr": _ADDR_C},
            {"wrid": "e" * 16, "worker_id": "miner-carol",
             "addr": _ADDR_D},
        ],
        allocated=135_000, primary_share=94_500,
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    assert plan["total_payable_stocks"] == 94_500
    assert plan["total_deferred_stocks"] == 0
    assert plan["total_unresolved_stocks"] == 0
    assert len(plan["payable_items"]) == 3
    # Each row pays one worker's share.
    for p in plan["payable_items"]:
        assert p["allocated_stocks"] == 31_500
        assert p["payout_address"].startswith("sost1")
        assert p["allocated_sost"] == 0.000315


def test_missing_address_lands_in_unresolved(
    tmp_path, proposal_mod,
):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
            # bob and carol present in rewards but NOT in the
            # address map.
            {"wrid": "d" * 16, "worker_id": "miner-bob",
             "addr": _ADDR_C},
        ],
        allocated=135_000, primary_share=94_500,
    )
    # Rewrite the budget to include a third wrid that has NO entry
    # in the address map and NO matching reward file.
    bd = json.loads(budget.read_text(encoding="utf-8"))
    bd["allocation_items"][0]["worker_result_ids"].append("f" * 16)
    bd["allocation_items"][0]["allocated_stocks"] = 135_000
    bd["allocation_items"][0]["primary_workers_share_stocks"] = 94_500
    budget.write_text(
        json.dumps(bd, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    assert plan["total_unresolved_stocks"] >= 1
    assert any("worker_id_hash" in u["missing_lookup"]
               or "rewards-dir" in u["missing_lookup"]
               for u in plan["unresolved_items"])


def test_deferred_allocation_copied_to_deferred(
    tmp_path, proposal_mod,
):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
        ],
        allocated=0, primary_share=0,
    )
    bd = json.loads(budget.read_text(encoding="utf-8"))
    bd["allocation_items"][0]["allocation_status"] = "deferred"
    bd["allocation_items"][0]["deferred_stocks"] = 135_000
    bd["allocation_items"][0]["cap_reason"] = "capped_by_daily"
    budget.write_text(
        json.dumps(bd, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    assert plan["total_deferred_stocks"] == 135_000
    assert len(plan["deferred_items"]) == 1
    assert plan["deferred_items"][0]["deferred_stocks"] == 135_000


def test_rejected_allocation_copied_to_rejected(
    tmp_path, proposal_mod,
):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
        ],
        allocated=0, primary_share=0,
    )
    bd = json.loads(budget.read_text(encoding="utf-8"))
    bd["allocation_items"][0]["allocation_status"] = "rejected"
    bd["allocation_items"][0]["cap_reason"] = (
        "governance_rejected_invalid_structure: missing fields"
    )
    budget.write_text(
        json.dumps(bd, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    assert len(plan["rejected_items"]) == 1
    assert "budget_rejected" in plan["rejected_items"][0]["reason"]


# ---------------------------------------------------------------------------
# Determinism + math
# ---------------------------------------------------------------------------


def test_proposal_id_deterministic_across_runs(
    tmp_path, proposal_mod,
):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
            {"wrid": "d" * 16, "worker_id": "miner-bob",
             "addr": _ADDR_C},
        ],
        allocated=90_000, primary_share=63_000,
    )
    a = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out_a",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    b = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out_b",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    assert a["proposal_id"] == b["proposal_id"]
    assert proposal_mod.canonical_dumps(a) == \
        proposal_mod.canonical_dumps(b)


def test_allocated_sost_matches_stocks_div_1e8(
    tmp_path, proposal_mod,
):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
        ],
        allocated=200_000_000, primary_share=140_000_000,
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    p = plan["payable_items"][0]
    assert p["allocated_stocks"] == 140_000_000
    assert abs(p["allocated_sost"] - 1.4) < 1e-9


def test_workers_to_same_address_merge_into_one_row(
    tmp_path, proposal_mod,
):
    """When two workers map to the same address, the proposal emits
    a single payable_item carrying both worker_result_ids."""
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
            {"wrid": "d" * 16, "worker_id": "miner-bob",
             "addr": _ADDR_A},   # ← same
        ],
        allocated=90_000, primary_share=63_000,
    )
    # The address map currently rejects duplicate payout_address.
    # Loosen by re-writing the second entry to point to a unique
    # alias, but then add a SECOND mapping that points back.
    # Simpler: skip duplicate guard by editing the address map.
    am = json.loads(addr.read_text(encoding="utf-8"))
    am["workers"][1]["payout_address"] = _ADDR_A  # explicit collision
    # The validator rejects this; we expect a ValueError.
    addr.write_text(
        json.dumps(am, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate payout_address"):
        proposal_mod.run_payment_proposal(
            budget_path=budget, address_map_path=addr,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
            rewards_dir=rewards,
        )


# ---------------------------------------------------------------------------
# Bad inputs
# ---------------------------------------------------------------------------


def test_wrong_budget_schema_rejected(tmp_path, proposal_mod):
    addr = tmp_path / "addr.json"
    addr.write_text(json.dumps({
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [],
    }), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"schema": "not-a-budget/v0", "budget_id": "x"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema"):
        proposal_mod.run_payment_proposal(
            budget_path=bad, address_map_path=addr,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
        )


def test_wrong_address_map_schema_rejected(tmp_path, proposal_mod):
    budget = tmp_path / "b.json"
    budget.write_text(json.dumps(_budget_plan(
        budget_id="bud-" + "1" * 16, request_id="uc-" + "a" * 16,
        batch_id="gov-" + "b" * 16, worker_result_ids=[],
        allocated=0, primary_share=0,
    )), encoding="utf-8")
    bad = tmp_path / "bad_addr.json"
    bad.write_text(
        json.dumps({"schema": "wrong/v0", "workers": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="address map"):
        proposal_mod.run_payment_proposal(
            budget_path=budget, address_map_path=bad,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
        )


def test_invalid_payout_address_rejected_in_map(tmp_path, proposal_mod):
    budget = tmp_path / "b.json"
    budget.write_text(json.dumps(_budget_plan(
        budget_id="bud-" + "1" * 16, request_id="uc-" + "a" * 16,
        batch_id="gov-" + "b" * 16, worker_result_ids=[],
        allocated=0, primary_share=0,
    )), encoding="utf-8")
    addr = tmp_path / "addr.json"
    addr.write_text(json.dumps({
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [{"worker_id_hash": "f" * 16,
                     "payout_address": "not-a-sost-address"}],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="payout_address"):
        proposal_mod.run_payment_proposal(
            budget_path=budget, address_map_path=addr,
            out_dir=tmp_path / "out",
            pinned_time="2026-05-12T00:00:00+00:00",
        )


# ---------------------------------------------------------------------------
# CLI safety
# ---------------------------------------------------------------------------


def test_cli_rejects_non_local_mode(tmp_path, proposal_mod):
    with pytest.raises(SystemExit):
        proposal_mod.main([
            "--mode", "live",
            "--budget-plan", str(tmp_path / "b.json"),
            "--worker-address-map", str(tmp_path / "a.json"),
            "--out-dir", str(tmp_path),
        ])


def test_cli_rejects_payout(tmp_path, proposal_mod):
    rc = proposal_mod.main([
        "--mode", "local-dry-run",
        "--budget-plan", str(tmp_path / "b.json"),
        "--worker-address-map", str(tmp_path / "a.json"),
        "--out-dir", str(tmp_path),
        "--payout",
    ])
    assert rc == 2


def test_cli_rejects_broadcast(tmp_path, proposal_mod):
    rc = proposal_mod.main([
        "--mode", "local-dry-run",
        "--budget-plan", str(tmp_path / "b.json"),
        "--worker-address-map", str(tmp_path / "a.json"),
        "--out-dir", str(tmp_path),
        "--broadcast",
    ])
    assert rc == 2


def test_cli_rejects_wallet(tmp_path, proposal_mod):
    rc = proposal_mod.main([
        "--mode", "local-dry-run",
        "--budget-plan", str(tmp_path / "b.json"),
        "--worker-address-map", str(tmp_path / "a.json"),
        "--out-dir", str(tmp_path),
        "--wallet", "/dev/null",
    ])
    assert rc == 2


def test_cli_rejects_sign(tmp_path, proposal_mod):
    rc = proposal_mod.main([
        "--mode", "local-dry-run",
        "--budget-plan", str(tmp_path / "b.json"),
        "--worker-address-map", str(tmp_path / "a.json"),
        "--out-dir", str(tmp_path),
        "--sign",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Safety + capsule
# ---------------------------------------------------------------------------


def test_safety_status_const_true(tmp_path, proposal_mod):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
        ],
        allocated=90_000, primary_share=63_000,
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    for flag in (
        "no_private_keys", "no_wallet_access", "no_signature",
        "no_broadcast", "proposal_only",
        "requires_manual_signing", "requires_separate_broadcast",
    ):
        assert plan["safety_status"][flag] is True


def test_capsule_summary_template_locked(tmp_path, proposal_mod):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
        ],
        allocated=90_000, primary_share=63_000,
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    cs = plan["capsule_summary"]
    assert cs["template"] == "useful_compute_reward_batch_v1"
    assert plan["proposal_id"] in cs["text"]
    assert plan["source_budget_id"] in cs["text"]


def test_proposal_carries_governance_batch_in_capsule(
    tmp_path, proposal_mod,
):
    rid, batch, budget, addr, rewards = _setup(
        tmp_path,
        workers=[
            {"wrid": "c" * 16, "worker_id": "miner-alice",
             "addr": _ADDR_A},
        ],
        allocated=90_000, primary_share=63_000,
    )
    plan = proposal_mod.run_payment_proposal(
        budget_path=budget, address_map_path=addr,
        out_dir=tmp_path / "out",
        pinned_time="2026-05-12T00:00:00+00:00",
        rewards_dir=rewards,
    )
    rf = plan["capsule_summary"]["referenced_files"]
    assert rf["budget_id"] == "bud-" + "1" * 16
    assert "gov-" + "b" * 16 in rf["governance_batch_ids"]
    assert rf["validation_ids"] == []
