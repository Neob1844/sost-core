"""Trinity / Background Autonomy Daemon v0.1 — invariants."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
OBJECTIVES_DIR = REPO_ROOT / "config" / "trinity" / "objectives"


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def daemon_mod():
    return _load(
        "trinity_bg", SCRIPTS_DIR / "trinity_background_daemon.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_bg", SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def worker_mod():
    return _load("ucw_bg", SCRIPTS_DIR / "useful_compute_worker.py")


def _make_request(builder_mod):
    return builder_mod.build_request(
        source_tool="materials_engine",
        candidate_id="cand-daemon-1",
        input_bundle_bytes=b"daemon-bundle",
        expected_output_schema="dft-result/v0",
        difficulty_class="medium",
        max_reward_stocks=100000,
        deadline="2026-05-13T00:00:00+00:00",
        public_description="daemon test request",
    )


def _seed_inbox(daemon_mod, workspace, builder_mod, worker_mod=None):
    """Populate inbox/requests with a hand-built request so tests do
    not depend on materials-engine-private being installed."""
    paths = daemon_mod._prepare_workspace(workspace)
    req = _make_request(builder_mod)
    p = paths["inbox_requests"] / (
        f"TRINITY_USEFUL_COMPUTE_REQUEST_{req['request_id']}.json"
    )
    p.write_text(
        json.dumps(req, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return req


# ---------------------------------------------------------------------------
# run_once
# ---------------------------------------------------------------------------


def test_run_once_creates_workspace_structure(tmp_path, daemon_mod):
    state = daemon_mod.run_cycle(
        workspace=tmp_path / "ws",
        objectives_dir=OBJECTIVES_DIR,
        seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-12T00:00:00+00:00",
        count=10,
        worker_id=None,
        reviewer_id=None,
    )
    ws = tmp_path / "ws"
    for sub in (
        "inbox/requests", "work/results", "work/rewards",
        "validation", "governance", "summaries", "lessons",
        "orchestrator",
    ):
        assert (ws / sub).is_dir(), f"missing subdir: {sub}"
    assert (ws / "TRINITY_BACKGROUND_DAEMON_STATE.json").exists()
    assert (ws / "TRINITY_BACKGROUND_DAEMON_SUMMARY.md").exists()
    assert state["schema"] == "trinity-background-daemon-state/v0.1"


def test_state_json_is_strict_and_carries_safety(tmp_path, daemon_mod):
    state = daemon_mod.run_cycle(
        workspace=tmp_path / "ws",
        objectives_dir=OBJECTIVES_DIR,
        seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-12T00:00:00+00:00",
        count=10,
        worker_id=None, reviewer_id=None,
    )
    ss = state["safety_status"]
    for flag in (
        "local_dry_run_only", "no_wallet_access", "no_private_keys",
        "no_automatic_payout", "no_broadcast",
        "no_network_required", "no_consensus_changes",
        "human_review_required_before_payment",
    ):
        assert ss[flag] is True
    assert state["mode"] == "local-dry-run"
    assert state["cycle_index"] == 1


def test_workspace_field_is_basename_only(tmp_path, daemon_mod):
    ws = tmp_path / "trinity-daemon-test"
    state = daemon_mod.run_cycle(
        workspace=ws,
        objectives_dir=OBJECTIVES_DIR,
        seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-12T00:00:00+00:00",
        count=10,
        worker_id=None, reviewer_id=None,
    )
    assert state["workspace"] == "trinity-daemon-test"
    assert "/" not in state["workspace"]


def test_state_byte_identical_with_same_inputs(
    tmp_path, daemon_mod, builder_mod, worker_mod,
):
    """Two workspaces with the same basename, same seeded inbox and
    pinned_time must produce byte-identical state JSON."""
    ws_a = tmp_path / "a" / "trinity-bg"
    ws_b = tmp_path / "b" / "trinity-bg"
    ws_a.mkdir(parents=True)
    ws_b.mkdir(parents=True)
    _seed_inbox(daemon_mod, ws_a, builder_mod)
    _seed_inbox(daemon_mod, ws_b, builder_mod)

    state_a = daemon_mod.run_cycle(
        workspace=ws_a, objectives_dir=OBJECTIVES_DIR,
        seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-12T00:00:00+00:00",
        count=10, worker_id="miner-byte", reviewer_id="reviewer-byte",
    )
    state_b = daemon_mod.run_cycle(
        workspace=ws_b, objectives_dir=OBJECTIVES_DIR,
        seed="trinity-autonomy-v0.1",
        pinned_time="2026-05-12T00:00:00+00:00",
        count=10, worker_id="miner-byte", reviewer_id="reviewer-byte",
    )
    assert daemon_mod.canonical_dumps(state_a) == \
        daemon_mod.canonical_dumps(state_b)


def test_inbox_request_promotes_to_pending(
    tmp_path, daemon_mod, builder_mod,
):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    req = _seed_inbox(daemon_mod, ws, builder_mod)
    state = daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id=None, reviewer_id=None,
    )
    assert req["request_id"] in state["pending_requests"]


def test_worker_id_writes_result_and_reward(
    tmp_path, daemon_mod, builder_mod,
):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    req = _seed_inbox(daemon_mod, ws, builder_mod)
    daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id=None,
    )
    rid = req["request_id"]
    res_files = list(
        (ws / "work" / "results").glob(
            f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_*.json"
        )
    )
    rew_files = list(
        (ws / "work" / "rewards").glob(
            f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_*.json"
        )
    )
    assert len(res_files) == 1
    assert len(rew_files) == 1


def test_two_workers_trigger_validation_accepted(
    tmp_path, daemon_mod, builder_mod,
):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    req = _seed_inbox(daemon_mod, ws, builder_mod)
    daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id="reviewer-x",
    )
    state = daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-B", reviewer_id="reviewer-x",
    )
    assert state["validations_seen"] >= 1
    assert state["accepted_validations"], (
        "expected at least one accepted validation"
    )


def test_two_workers_trigger_governance_batch_approved(
    tmp_path, daemon_mod, builder_mod,
):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    req = _seed_inbox(daemon_mod, ws, builder_mod)
    daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id="reviewer-x",
    )
    state = daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-B", reviewer_id="reviewer-x",
    )
    assert state["governance_batches_seen"] >= 1
    assert state["approved_batches"], (
        "expected at least one approved batch"
    )


# ---------------------------------------------------------------------------
# Error handling + lessons
# ---------------------------------------------------------------------------


def test_malformed_inbox_request_is_skipped_and_does_not_crash(
    tmp_path, daemon_mod,
):
    ws = tmp_path / "ws"
    paths = daemon_mod._prepare_workspace(ws)
    bad = paths["inbox_requests"] / (
        "TRINITY_USEFUL_COMPUTE_REQUEST_uc-deadbeefdeadbeef.json"
    )
    bad.write_text(
        json.dumps({"schema": "wrong/v0"}), encoding="utf-8",
    )
    state = daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id=None,
    )
    # Daemon did not crash. The bad file is in the inbox, the worker
    # raised, and the lesson was recorded.
    assert state["lessons_count"] >= 1


def test_repeated_known_failure_is_skipped_without_flag(
    tmp_path, daemon_mod, builder_mod,
):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    req = _seed_inbox(daemon_mod, ws, builder_mod)
    # Pre-seed the error ledger with a lesson for THIS (rid, wid).
    paths = daemon_mod._prepare_workspace(ws)
    error_ledger = (
        paths["lessons"] / "TRINITY_AUTONOMY_ERROR_LEDGER.jsonl"
    )
    em_mod = _load(
        "tem_bg_repeat", SCRIPTS_DIR / "trinity_error_memory.py",
    )
    em_mod.record_lesson(
        ledger_path=error_ledger,
        vertical="useful_compute",
        task_inputs={
            "request_id": req["request_id"],
            "worker_id": "miner-A",
        },
        cause="compute_failed",
        detail="seeded",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    # Run with default (no --allow-known-failures). Worker should
    # skip the request.
    state = daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id=None,
        allow_known_failures=False,
    )
    rid = req["request_id"]
    res_files = list(
        (ws / "work" / "results").glob(
            f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_*.json"
        )
    )
    assert res_files == []


def test_allow_known_failures_retries(
    tmp_path, daemon_mod, builder_mod,
):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    req = _seed_inbox(daemon_mod, ws, builder_mod)
    paths = daemon_mod._prepare_workspace(ws)
    error_ledger = (
        paths["lessons"] / "TRINITY_AUTONOMY_ERROR_LEDGER.jsonl"
    )
    em_mod = _load(
        "tem_bg_allow", SCRIPTS_DIR / "trinity_error_memory.py",
    )
    em_mod.record_lesson(
        ledger_path=error_ledger,
        vertical="useful_compute",
        task_inputs={
            "request_id": req["request_id"],
            "worker_id": "miner-A",
        },
        cause="compute_failed",
        detail="seeded",
        pinned_time="2026-05-12T00:00:00+00:00",
    )
    daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id=None,
        allow_known_failures=True,
    )
    rid = req["request_id"]
    res_files = list(
        (ws / "work" / "results").glob(
            f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_*.json"
        )
    )
    assert len(res_files) == 1


# ---------------------------------------------------------------------------
# Summary content
# ---------------------------------------------------------------------------


def test_summary_md_mentions_requests_and_safety(
    tmp_path, daemon_mod, builder_mod,
):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    req = _seed_inbox(daemon_mod, ws, builder_mod)
    daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id="r",
    )
    md = (ws / "TRINITY_BACKGROUND_DAEMON_SUMMARY.md").read_text(
        encoding="utf-8"
    )
    assert "requests_seen" in md
    assert "results_seen" in md
    assert "validations_seen" in md
    assert "governance_batches_seen" in md
    assert "local_dry_run_only" in md
    assert "human_review_required_before_payment" in md
    assert "NEVER pays" in md or "never pays" in md.lower()


# ---------------------------------------------------------------------------
# CLI safety
# ---------------------------------------------------------------------------


def test_cli_rejects_non_local_mode(tmp_path, daemon_mod):
    with pytest.raises(SystemExit):
        daemon_mod.main([
            "--mode", "live",
            "--workspace", str(tmp_path),
            "--run-once",
        ])


def test_cli_rejects_payout(tmp_path, daemon_mod):
    rc = daemon_mod.main([
        "--mode", "local-dry-run",
        "--workspace", str(tmp_path),
        "--run-once",
        "--payout",
    ])
    assert rc == 2


def test_cli_rejects_broadcast(tmp_path, daemon_mod):
    rc = daemon_mod.main([
        "--mode", "local-dry-run",
        "--workspace", str(tmp_path),
        "--run-once",
        "--broadcast",
    ])
    assert rc == 2


def test_cli_rejects_wallet(tmp_path, daemon_mod):
    rc = daemon_mod.main([
        "--mode", "local-dry-run",
        "--workspace", str(tmp_path),
        "--run-once",
        "--wallet", "/dev/null",
    ])
    assert rc == 2


def test_cli_rejects_network(tmp_path, daemon_mod):
    rc = daemon_mod.main([
        "--mode", "local-dry-run",
        "--workspace", str(tmp_path),
        "--run-once",
        "--network",
    ])
    assert rc == 2


def test_cli_requires_run_once_or_watch(tmp_path, daemon_mod):
    with pytest.raises(SystemExit):
        daemon_mod.main([
            "--mode", "local-dry-run",
            "--workspace", str(tmp_path),
        ])


def test_cli_run_once_writes_state_file(tmp_path, daemon_mod):
    rc = daemon_mod.main([
        "--mode", "local-dry-run",
        "--workspace", str(tmp_path / "ws"),
        "--run-once",
        "--objectives", str(OBJECTIVES_DIR),
        "--pinned-time", "2026-05-12T00:00:00+00:00",
        "--count", "0",
    ])
    assert rc == 0
    assert (
        tmp_path / "ws" / "TRINITY_BACKGROUND_DAEMON_STATE.json"
    ).exists()


# ---------------------------------------------------------------------------
# Events log
# ---------------------------------------------------------------------------


def test_events_log_is_jsonl(tmp_path, daemon_mod, builder_mod):
    ws = tmp_path / "ws"
    ws.mkdir(parents=True)
    _seed_inbox(daemon_mod, ws, builder_mod)
    daemon_mod.run_cycle(
        workspace=ws, objectives_dir=OBJECTIVES_DIR,
        seed="x", pinned_time="2026-05-12T00:00:00+00:00",
        count=0, worker_id="miner-A", reviewer_id="r",
    )
    text = (ws / "TRINITY_BACKGROUND_EVENTS.jsonl").read_text(
        encoding="utf-8"
    )
    for line in text.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        assert d["schema"] == "trinity-background-event/v0.1"
        assert "stage" in d
        assert d["stage"] in (
            "orchestrator", "worker", "validator", "governance",
        )
