"""Functional tests for the Trinity Task Queue Runner v0.1 (Sprint 5.27).

The runner is a bounded wrapper over the existing run_once() logic
(Sprint 5.26). These tests exercise:
  - empty queue
  - happy path with 1 item
  - max-items < pending count (stops at the bound, leaves rest pending)
  - max-items == pending count (consumes them all)
  - oldest-first selection
  - failed-item bookkeeping (without --stop-on-failure ⇒ warning,
    with --stop-on-failure ⇒ failed and halt)
  - max-items bounds (0 and 51 refused; sleep-seconds bounds)
  - default + explicit --report-path
  - determinism of batch_id for stable input state
  - real run_once subprocess path (operator_loop + watchdog)

The "failed item" branch is driven by mutating the request.json on
disk between enqueue and run-batch — the operator_loop then exits
non-zero and the runner records the item as failed.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
FIXTURES = REPO_ROOT / "tests" / "trinity" / "fixtures" / "useful_compute"
REQUEST_FIXTURE = FIXTURES / "request_scientific_intake.json"
ADDRESS_MAP_FIXTURE = FIXTURES / "address_map.json"
EXAMPLE_POLICY = REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"
RUNNER_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "task_queue_runner_report.schema.json"
)
PINNED = "2026-05-17T00:00:00+00:00"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def tq():
    return _load("task_queue_run", SCRIPTS_DIR / "task_queue.py")


@pytest.fixture(scope="module")
def runner_schema():
    with open(RUNNER_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _init(tq, tmp_path):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    return qd


def _enqueue(tq, queue_dir, *, request=None, pinned=PINNED):
    return tq.enqueue_item(
        queue_dir=queue_dir,
        request_json=request or REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=pinned,
    )


# ---------------------------------------------------------------------------
# Empty queue / happy path
# ---------------------------------------------------------------------------


def test_run_batch_empty_queue_returns_attempted_zero(tmp_path, tq):
    qd = _init(tq, tmp_path)
    report = tq.run_batch(
        queue_dir=qd, max_items=5, pinned_time=PINNED,
    )
    assert report["attempted_count"] == 0
    assert report["completed_count"] == 0
    assert report["failed_count"] == 0
    assert report["skipped_count"] == 5
    assert report["safety_status"] == "ok"
    assert report["item_ids"] == []
    assert Path(report["_report_path"]).is_file()


def test_run_batch_one_pending_item_completes(tmp_path, tq):
    qd = _init(tq, tmp_path)
    item = _enqueue(tq, qd)
    report = tq.run_batch(
        queue_dir=qd, max_items=1, pinned_time=PINNED,
    )
    assert report["attempted_count"] == 1
    assert report["completed_count"] == 1
    assert report["failed_count"] == 0
    assert report["skipped_count"] == 0
    assert report["safety_status"] == "ok"
    assert report["item_ids"] == [item["queue_item_id"]]
    assert report["completed_item_ids"] == [item["queue_item_id"]]


# ---------------------------------------------------------------------------
# Bounded batch + skipped_count
# ---------------------------------------------------------------------------


def test_run_batch_max_items_smaller_than_pending_leaves_rest(
    tmp_path, tq,
):
    qd = _init(tq, tmp_path)
    a = _enqueue(tq, qd, pinned="2026-05-17T00:00:00+00:00")
    b = _enqueue(tq, qd, pinned="2026-05-17T01:00:00+00:00")
    report = tq.run_batch(
        queue_dir=qd, max_items=1, pinned_time=PINNED,
    )
    assert report["attempted_count"] == 1
    assert report["completed_count"] == 1
    assert report["skipped_count"] == 0  # we attempted exactly max
    # One of the two items remains pending on disk.
    view = tq.list_items(qd)
    assert view["counts"]["pending"] == 1
    assert view["counts"]["completed"] == 1


def test_run_batch_max_items_equal_to_pending_consumes_both(
    tmp_path, tq,
):
    qd = _init(tq, tmp_path)
    a = _enqueue(tq, qd, pinned="2026-05-17T00:00:00+00:00")
    b = _enqueue(tq, qd, pinned="2026-05-17T01:00:00+00:00")
    report = tq.run_batch(
        queue_dir=qd, max_items=2, pinned_time=PINNED,
    )
    assert report["attempted_count"] == 2
    assert report["completed_count"] == 2
    assert report["safety_status"] == "ok"
    assert set(report["completed_item_ids"]) == {
        a["queue_item_id"], b["queue_item_id"],
    }
    view = tq.list_items(qd)
    assert view["counts"]["pending"] == 0
    assert view["counts"]["completed"] == 2


def test_run_batch_max_items_larger_than_pending_records_skipped(
    tmp_path, tq,
):
    qd = _init(tq, tmp_path)
    _enqueue(tq, qd)
    report = tq.run_batch(
        queue_dir=qd, max_items=5, pinned_time=PINNED,
    )
    assert report["attempted_count"] == 1
    assert report["completed_count"] == 1
    assert report["skipped_count"] == 4
    assert report["safety_status"] == "ok"


# ---------------------------------------------------------------------------
# Oldest-first
# ---------------------------------------------------------------------------


def test_run_batch_processes_oldest_pending_first(tmp_path, tq):
    qd = _init(tq, tmp_path)
    a = _enqueue(tq, qd, pinned="2026-05-17T00:00:00+00:00")
    b = _enqueue(tq, qd, pinned="2026-05-17T05:00:00+00:00")
    report = tq.run_batch(
        queue_dir=qd, max_items=1, pinned_time=PINNED,
    )
    # The first item picked must be 'a' (earliest created_at) — not 'b'.
    assert report["completed_item_ids"] == [a["queue_item_id"]]
    # And 'b' is still pending.
    view = tq.list_items(qd)
    by_id = {x["queue_item_id"]: x["status"] for x in view["items"]}
    assert by_id[a["queue_item_id"]] == "completed"
    assert by_id[b["queue_item_id"]] == "pending"


# ---------------------------------------------------------------------------
# Failed items
# ---------------------------------------------------------------------------


def test_run_batch_records_failed_item_as_warning(tmp_path, tq):
    """One enqueued item whose request_json is removed between
    enqueue and run-batch fails (operator_loop exits non-zero).
    Without --stop-on-failure the batch continues; the second
    item completes; safety_status=warning."""
    qd = _init(tq, tmp_path)
    # Bad item: request.json is deleted after enqueue
    bad_req = tmp_path / "bad_request.json"
    bad_req.write_bytes(REQUEST_FIXTURE.read_bytes())
    bad_item = tq.enqueue_item(
        queue_dir=qd,
        request_json=bad_req,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time="2026-05-17T00:00:00+00:00",
    )
    bad_req.unlink()
    # Good item: uses the real fixture
    good_item = _enqueue(tq, qd, pinned="2026-05-17T01:00:00+00:00")
    report = tq.run_batch(
        queue_dir=qd, max_items=2, pinned_time=PINNED,
        stop_on_failure=False,
    )
    assert report["attempted_count"] == 2
    assert report["failed_count"] == 1
    assert report["completed_count"] == 1
    assert report["safety_status"] == "warning"
    assert report["failed_item_ids"] == [bad_item["queue_item_id"]]
    assert report["completed_item_ids"] == [good_item["queue_item_id"]]
    assert any(
        bad_item["queue_item_id"] in w for w in report["warnings"]
    )


def test_run_batch_stop_on_failure_halts_after_first_failure(
    tmp_path, tq,
):
    qd = _init(tq, tmp_path)
    bad_req = tmp_path / "bad_request.json"
    bad_req.write_bytes(REQUEST_FIXTURE.read_bytes())
    bad_item = tq.enqueue_item(
        queue_dir=qd,
        request_json=bad_req,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time="2026-05-17T00:00:00+00:00",
    )
    bad_req.unlink()
    good_item = _enqueue(tq, qd, pinned="2026-05-17T01:00:00+00:00")
    report = tq.run_batch(
        queue_dir=qd, max_items=2, pinned_time=PINNED,
        stop_on_failure=True,
    )
    # Only the bad item was attempted; the runner halted on failure.
    assert report["attempted_count"] == 1
    assert report["failed_count"] == 1
    assert report["completed_count"] == 0
    assert report["safety_status"] == "failed"
    # The good item is still pending on disk.
    view = tq.list_items(qd)
    by_id = {x["queue_item_id"]: x["status"] for x in view["items"]}
    assert by_id[good_item["queue_item_id"]] == "pending"


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [0, 51, -1, 1000])
def test_run_batch_rejects_out_of_range_max_items(tmp_path, tq, bad):
    qd = _init(tq, tmp_path)
    with pytest.raises(tq.QueueError) as ei:
        tq.run_batch(
            queue_dir=qd, max_items=bad, pinned_time=PINNED,
        )
    assert "max-items" in str(ei.value)


@pytest.mark.parametrize("bad", [-1, 3601])
def test_run_batch_rejects_out_of_range_sleep(tmp_path, tq, bad):
    qd = _init(tq, tmp_path)
    with pytest.raises(tq.QueueError) as ei:
        tq.run_batch(
            queue_dir=qd, max_items=1, pinned_time=PINNED,
            sleep_seconds=bad,
        )
    assert "sleep-seconds" in str(ei.value)


def test_run_batch_refuses_when_queue_not_initialised(tmp_path, tq):
    with pytest.raises(tq.QueueError) as ei:
        tq.run_batch(
            queue_dir=tmp_path / "never_initialised",
            max_items=1, pinned_time=PINNED,
        )
    assert "not initialised" in str(ei.value)


# ---------------------------------------------------------------------------
# Sleep hook (tests the inter-item delay path without actually sleeping)
# ---------------------------------------------------------------------------


def test_run_batch_calls_sleep_hook_between_items(tmp_path, tq):
    qd = _init(tq, tmp_path)
    _enqueue(tq, qd, pinned="2026-05-17T00:00:00+00:00")
    _enqueue(tq, qd, pinned="2026-05-17T01:00:00+00:00")
    sleeps = []
    report = tq.run_batch(
        queue_dir=qd, max_items=2, pinned_time=PINNED,
        sleep_seconds=7, _sleep_hook=sleeps.append,
    )
    assert report["completed_count"] == 2
    # One sleep between item 1 and item 2; no sleep after the last item.
    assert sleeps == [7]


def test_run_batch_sleep_hook_not_called_for_zero(tmp_path, tq):
    qd = _init(tq, tmp_path)
    _enqueue(tq, qd, pinned="2026-05-17T00:00:00+00:00")
    _enqueue(tq, qd, pinned="2026-05-17T01:00:00+00:00")
    sleeps = []
    tq.run_batch(
        queue_dir=qd, max_items=2, pinned_time=PINNED,
        sleep_seconds=0, _sleep_hook=sleeps.append,
    )
    assert sleeps == []


# ---------------------------------------------------------------------------
# Report path + determinism
# ---------------------------------------------------------------------------


def test_run_batch_writes_default_report_path(tmp_path, tq):
    qd = _init(tq, tmp_path)
    _enqueue(tq, qd)
    report = tq.run_batch(
        queue_dir=qd, max_items=1, pinned_time=PINNED,
    )
    expected = qd / "reports" / "_batches" / (
        "TRINITY_TASK_QUEUE_RUNNER_REPORT_" + report["batch_id"] + ".json"
    )
    assert expected.is_file()
    assert report["_report_path"] == str(expected)


def test_run_batch_writes_explicit_report_path(tmp_path, tq):
    qd = _init(tq, tmp_path)
    _enqueue(tq, qd)
    custom = tmp_path / "audits" / "my_batch.json"
    report = tq.run_batch(
        queue_dir=qd, max_items=1, pinned_time=PINNED,
        report_path=custom,
    )
    assert custom.is_file()
    assert report["_report_path"] == str(custom)


def test_run_batch_batch_id_deterministic_for_same_state(tmp_path, tq):
    qdA = tmp_path / "qA"
    qdB = tmp_path / "qA"  # same basename ⇒ same queue_dir component
    tq.init_queue(qdA, PINNED)
    _enqueue(tq, qdA, pinned="2026-05-17T00:00:00+00:00")
    rA = tq.run_batch(
        queue_dir=qdA, max_items=1, pinned_time=PINNED,
    )
    # Rerun against the now-empty queue: the batch_id depends on
    # item_ids attempted (which differ), so we instead assert
    # determinism on the SAME state by recomputing the report
    # against the same returned item_ids.
    rA2 = tq.run_batch(
        queue_dir=qdA, max_items=1, pinned_time=PINNED,
    )
    # First run attempted 1, second attempted 0 → different batch_ids
    assert rA["batch_id"] != rA2["batch_id"]
    # But repeating with identical inputs (no state change in
    # between) is deterministic:
    rA3 = tq.run_batch(
        queue_dir=qdA, max_items=1, pinned_time=PINNED,
    )
    assert rA2["batch_id"] == rA3["batch_id"]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_run_batch_report_validates_against_schema(
    tmp_path, tq, runner_schema,
):
    qd = _init(tq, tmp_path)
    _enqueue(tq, qd)
    report = tq.run_batch(
        queue_dir=qd, max_items=1, pinned_time=PINNED,
    )
    # Strip the transient _report_path key before validation
    report = dict(report)
    report.pop("_report_path", None)
    jsonschema.validate(report, runner_schema)


def test_run_batch_empty_report_validates_against_schema(
    tmp_path, tq, runner_schema,
):
    qd = _init(tq, tmp_path)
    report = tq.run_batch(
        queue_dir=qd, max_items=3, pinned_time=PINNED,
    )
    report = dict(report)
    report.pop("_report_path", None)
    jsonschema.validate(report, runner_schema)
    assert report["safety_status"] == "ok"
    assert report["attempted_count"] == 0


def test_run_batch_failed_report_validates_against_schema(
    tmp_path, tq, runner_schema,
):
    qd = _init(tq, tmp_path)
    bad_req = tmp_path / "bad.json"
    bad_req.write_bytes(REQUEST_FIXTURE.read_bytes())
    tq.enqueue_item(
        queue_dir=qd,
        request_json=bad_req,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time="2026-05-17T00:00:00+00:00",
    )
    bad_req.unlink()
    report = tq.run_batch(
        queue_dir=qd, max_items=1, pinned_time=PINNED,
        stop_on_failure=True,
    )
    report = dict(report)
    report.pop("_report_path", None)
    jsonschema.validate(report, runner_schema)
    assert report["safety_status"] == "failed"


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_run_batch_happy_path(tmp_path, tq):
    qd = _init(tq, tmp_path)
    assert tq.main([
        "enqueue", "--queue-dir", str(qd),
        "--request-json", str(REQUEST_FIXTURE),
        "--worker-address-map", str(ADDRESS_MAP_FIXTURE),
        "--governor-policy", str(EXAMPLE_POLICY),
        "--pinned-time", PINNED,
    ]) == 0
    rc = tq.main([
        "run-batch", "--queue-dir", str(qd),
        "--max-items", "1", "--pinned-time", PINNED,
    ])
    assert rc == 0
    # The report is on disk under the default path.
    reports_dir = qd / "reports" / "_batches"
    assert reports_dir.is_dir()
    reports = list(reports_dir.glob(
        "TRINITY_TASK_QUEUE_RUNNER_REPORT_*.json",
    ))
    assert len(reports) == 1


def test_cli_run_batch_invalid_max_items_returns_2(tmp_path, tq):
    qd = _init(tq, tmp_path)
    rc = tq.main([
        "run-batch", "--queue-dir", str(qd),
        "--max-items", "0", "--pinned-time", PINNED,
    ])
    assert rc == 2
    rc = tq.main([
        "run-batch", "--queue-dir", str(qd),
        "--max-items", "51", "--pinned-time", PINNED,
    ])
    assert rc == 2
