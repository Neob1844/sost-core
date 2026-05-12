"""Trinity / Useful Compute reward model — v0.1 invariants."""

from __future__ import annotations

import importlib.util
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
        "ucrm", SCRIPTS_DIR / "useful_compute_reward_model.py"
    )


_BASE = dict(
    task_id="t-001", worker_id="w-001",
    benchmark_score=1.0, verified_compute_seconds=10.0,
    difficulty_class="medium", result_validated=True,
    duplicate_result=False, max_reward_stocks=1000000,
)


def test_invalid_result_zero(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "result_validated": False}
    )
    assert out["pending_reward_stocks"] == 0
    assert "not validated" in out["reason"]


def test_duplicate_zero_by_default(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "duplicate_result": True}
    )
    assert out["pending_reward_stocks"] == 0


def test_higher_benchmark_earns_more(reward_mod):
    low  = reward_mod.compute_pending_reward(
        **{**_BASE, "benchmark_score": 1.0}
    )
    high = reward_mod.compute_pending_reward(
        **{**_BASE, "benchmark_score": 4.0}
    )
    assert high["pending_reward_stocks"] > low["pending_reward_stocks"]


def test_cap_respected(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE,
           "benchmark_score": 9.0,
           "verified_compute_seconds": 3600.0,
           "difficulty_class": "extreme",
           "max_reward_stocks": 1000}
    )
    assert out["pending_reward_stocks"] == 1000


def test_deterministic(reward_mod):
    a = reward_mod.compute_pending_reward(**_BASE)
    b = reward_mod.compute_pending_reward(**_BASE)
    assert a == b


def test_zero_seconds_zero_stocks(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "verified_compute_seconds": 0.0}
    )
    assert out["pending_reward_stocks"] == 0


def test_compute_seconds_cap_triggers_manual_review(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "verified_compute_seconds": 100000.0}
    )
    assert out["requires_manual_review"] is True


def test_benchmark_above_ceiling_capped_and_flagged(reward_mod):
    out = reward_mod.compute_pending_reward(
        **{**_BASE, "benchmark_score": 99.0}
    )
    assert out["requires_manual_review"] is True


def test_invalid_difficulty_rejected(reward_mod):
    with pytest.raises(ValueError):
        reward_mod.compute_pending_reward(
            **{**_BASE, "difficulty_class": "nuclear"}
        )


def test_empty_ids_rejected(reward_mod):
    with pytest.raises(ValueError):
        reward_mod.compute_pending_reward(**{**_BASE, "task_id": ""})
    with pytest.raises(ValueError):
        reward_mod.compute_pending_reward(**{**_BASE, "worker_id": ""})


def test_negative_max_reward_rejected(reward_mod):
    with pytest.raises(ValueError):
        reward_mod.compute_pending_reward(
            **{**_BASE, "max_reward_stocks": -1}
        )
