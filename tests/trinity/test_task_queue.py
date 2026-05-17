"""Functional tests for the Trinity Task Queue v0.1 (Sprint 5.26).

The queue runner invokes useful_compute_operator_loop.py and
governor_watchdog.py as subprocesses. The tests exercise both
direct in-process API calls (init, enqueue, list, inspect,
validate) and the real run-once subprocess path so the wiring
between the three scripts is covered end-to-end.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
FIXTURES = REPO_ROOT / "tests" / "trinity" / "fixtures" / "useful_compute"
REQUEST_FIXTURE = FIXTURES / "request_scientific_intake.json"
ADDRESS_MAP_FIXTURE = FIXTURES / "address_map.json"
EXAMPLE_POLICY = REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"
PINNED = "2026-05-17T00:00:00+00:00"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tq():
    return _load("task_queue_t", SCRIPTS_DIR / "task_queue.py")


def _enqueue_default(tq, queue_dir, pinned=PINNED, request=None):
    return tq.enqueue_item(
        queue_dir=queue_dir,
        request_json=request or REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=pinned,
    )


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


def test_init_creates_queue_structure(tmp_path, tq):
    qd = tmp_path / "q"
    q = tq.init_queue(qd, PINNED)
    assert q["schema"] == "trinity-task-queue/v0.1"
    assert q["queue_id"].startswith("tq-")
    assert (qd / "queue.json").is_file()
    for sub in ("pending", "running", "completed", "failed", "reports"):
        assert (qd / sub).is_dir(), "missing subdir: " + sub


def test_init_refuses_to_overwrite_existing_queue(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    with pytest.raises(tq.QueueError) as ei:
        tq.init_queue(qd, PINNED)
    assert "already exists" in str(ei.value)


def test_init_queue_id_deterministic(tmp_path, tq):
    qd1 = tmp_path / "qA"
    qd2 = tmp_path / "qB"
    q1 = tq.init_queue(qd1, PINNED)
    q2 = tq.init_queue(qd2, PINNED)
    # Different basenames produce different queue_ids
    assert q1["queue_id"] != q2["queue_id"]


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


def test_enqueue_creates_pending_item_with_hashes(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    item = _enqueue_default(tq, qd)
    assert item["schema"] == "trinity-task-queue-item/v0.1"
    assert item["queue_item_id"].startswith("qit-")
    assert item["status"] == "pending"
    assert len(item["policy_sha256"]) == 64
    assert len(item["request_sha256"]) == 64
    assert item["policy_sha256"] == (
        hashlib.sha256(EXAMPLE_POLICY.read_bytes()).hexdigest()
    )
    assert item["request_sha256"] == (
        hashlib.sha256(REQUEST_FIXTURE.read_bytes()).hexdigest()
    )
    # File landed in pending/ on disk.
    p = qd / "pending" / (item["queue_item_id"] + ".json")
    assert p.is_file()


def test_enqueue_refuses_duplicate(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    _enqueue_default(tq, qd)
    with pytest.raises(tq.QueueError) as ei:
        _enqueue_default(tq, qd)
    assert "already exists" in str(ei.value)


def test_enqueue_refuses_missing_files(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    with pytest.raises(tq.QueueError) as ei:
        tq.enqueue_item(
            queue_dir=qd,
            request_json=tmp_path / "no.json",
            worker_address_map=ADDRESS_MAP_FIXTURE,
            governor_policy=EXAMPLE_POLICY,
            pinned_time=PINNED,
        )
    assert "request-json not found" in str(ei.value)


def test_enqueue_persists_only_basenames_for_audit(tmp_path, tq):
    """Both absolute path and basename are stored — basename is the
    audit-friendly identifier and is also schema-required."""
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    item = _enqueue_default(tq, qd)
    assert item["request_json_path_basename"] == REQUEST_FIXTURE.name
    assert item["governor_policy_path_basename"] == EXAMPLE_POLICY.name
    assert item["worker_address_map_path_basename"] == ADDRESS_MAP_FIXTURE.name


# ---------------------------------------------------------------------------
# list / inspect
# ---------------------------------------------------------------------------


def test_list_shows_counts_and_items(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    _enqueue_default(tq, qd)
    view = tq.list_items(qd)
    assert view["counts"]["pending"] == 1
    assert view["counts"]["completed"] == 0
    assert len(view["items"]) == 1


def test_inspect_returns_item_dict(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    item = _enqueue_default(tq, qd)
    fetched = tq.inspect_item(qd, item["queue_item_id"])
    assert fetched["queue_item_id"] == item["queue_item_id"]


def test_inspect_unknown_id_raises(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    with pytest.raises(tq.QueueError):
        tq.inspect_item(qd, "qit-deadbeefdeadbeef")


# ---------------------------------------------------------------------------
# run-once (real subprocess to operator_loop + watchdog)
# ---------------------------------------------------------------------------


def test_run_once_completes_scientific_intake_end_to_end(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    item = _enqueue_default(tq, qd)
    result = tq.run_once(qd)
    assert result is not None
    assert result["queue_item_id"] == item["queue_item_id"]
    assert result["status"] == "completed", (
        "last_error: " + str(result.get("last_error"))
    )
    assert result["governor_decisions_count"] == 7
    assert result["watchdog_safety_status"] == "ok"
    assert result["threat_refs"] == ["T15", "T16", "T17"]
    assert result["operator_run_path"] is not None
    assert result["watchdog_report_path"] is not None
    # The audit paths point at real files on disk.
    assert Path(result["operator_run_path"]).is_file()
    assert Path(result["watchdog_report_path"]).is_file()
    # Item lives in completed/ now.
    assert (qd / "completed" / (item["queue_item_id"] + ".json")).is_file()
    assert not (qd / "pending" / (item["queue_item_id"] + ".json")).exists()


def test_run_once_writes_operator_run_and_watchdog_paths(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    _enqueue_default(tq, qd)
    result = tq.run_once(qd)
    assert result["status"] == "completed"
    # The operator_run_path lives under reports/<item_id>/operator_run/
    parts = Path(result["operator_run_path"]).parts
    assert "reports" in parts
    assert "operator_run" in parts
    # The watchdog_report_path lives under reports/<item_id>/watchdog/
    wd_parts = Path(result["watchdog_report_path"]).parts
    assert "watchdog" in wd_parts


def test_run_once_no_pending_returns_none(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    assert tq.run_once(qd) is None


def test_run_once_failure_missing_request_marks_failed(tmp_path, tq):
    """If the request_json on disk is removed between enqueue and
    run, operator_loop fails. The queue item must end in failed/
    with last_error pointing at the operator output."""
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    # Copy the fixture so we can remove it after enqueue.
    req = tmp_path / "request.json"
    req.write_bytes(REQUEST_FIXTURE.read_bytes())
    tq.enqueue_item(
        queue_dir=qd,
        request_json=req,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    req.unlink()
    result = tq.run_once(qd)
    assert result["status"] == "failed"
    assert "operator_loop exited" in (result["last_error"] or "")


def test_run_once_governor_hard_block_fails_closed(tmp_path, tq):
    """If the HALT file is present, the operator_loop exits rc=3.
    The queue item must be marked failed with last_error citing
    governor_hard_block. No retry inside run-once."""
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    halt = tmp_path / "HALT"
    halt.write_text("stop")
    # Make a policy variant pointing at the halt file.
    base = json.loads(EXAMPLE_POLICY.read_text(encoding="utf-8"))
    base["kill_switch"]["halt_file"] = str(halt)
    pol = tmp_path / "policy_with_halt.json"
    pol.write_text(json.dumps(base, indent=2), encoding="utf-8")
    tq.enqueue_item(
        queue_dir=qd,
        request_json=REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=pol,
        pinned_time=PINNED,
    )
    result = tq.run_once(qd)
    assert result["status"] == "failed"
    assert "governor_hard_block" in (result["last_error"] or "")
    # The audit decision JSON was written before the block.
    op_dir = (
        qd / "reports" / result["queue_item_id"]
        / "operator_run" / "governor_decisions"
    )
    assert op_dir.exists()
    assert list(op_dir.glob("TRINITY_AUTONOMY_GOVERNOR_DECISION_*.json"))


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def test_validate_passes_on_clean_queue(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    _enqueue_default(tq, qd)
    summary = tq.validate_queue_tree(qd)
    assert summary["items_in_index"] == 1
    assert summary["items_on_disk_validated"] == 1


def test_validate_catches_malformed_queue_item(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    item = _enqueue_default(tq, qd)
    # Corrupt the item file on disk: remove a required field.
    p = qd / "pending" / (item["queue_item_id"] + ".json")
    bad = json.loads(p.read_text(encoding="utf-8"))
    bad.pop("policy_sha256")
    p.write_text(json.dumps(bad), encoding="utf-8")
    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        tq.validate_queue_tree(qd)


def test_validate_catches_corrupt_queue_json(tmp_path, tq):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    # Corrupt queue.json's schema field.
    q = json.loads((qd / "queue.json").read_text(encoding="utf-8"))
    q["schema"] = "trinity-task-queue/v0.99"
    (qd / "queue.json").write_text(json.dumps(q), encoding="utf-8")
    import jsonschema
    with pytest.raises(jsonschema.ValidationError):
        tq.validate_queue_tree(qd)


# ---------------------------------------------------------------------------
# Mode lock
# ---------------------------------------------------------------------------


def test_ensure_local_dry_run_rejects_other_modes(tq):
    with pytest.raises(tq.QueueError):
        tq._ensure_local_dry_run("propose")
    with pytest.raises(tq.QueueError):
        tq._ensure_local_dry_run("real")
    # Allowed mode is silent.
    tq._ensure_local_dry_run("local-dry-run")


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_init_enqueue_list_run_once(tmp_path, tq):
    qd = tmp_path / "q"
    assert tq.main([
        "init", "--queue-dir", str(qd), "--pinned-time", PINNED,
    ]) == 0
    assert tq.main([
        "enqueue", "--queue-dir", str(qd),
        "--request-json", str(REQUEST_FIXTURE),
        "--worker-address-map", str(ADDRESS_MAP_FIXTURE),
        "--governor-policy", str(EXAMPLE_POLICY),
        "--pinned-time", PINNED,
    ]) == 0
    assert tq.main(["list", "--queue-dir", str(qd)]) == 0
    assert tq.main(["run-once", "--queue-dir", str(qd)]) == 0
    # Final state: one completed item.
    view = tq.list_items(qd)
    assert view["counts"]["completed"] == 1
    assert tq.main(["validate", "--queue-dir", str(qd)]) == 0
