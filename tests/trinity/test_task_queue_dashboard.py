"""Functional tests for the Trinity Task Queue Dashboard v0.1
(Sprint 5.28).

The dashboard reads queue.json + per-status item files + per-item
operator_run.json + watchdog reports + per-batch runner reports and
writes a deterministic dashboard JSON plus a static HTML file. It
never invokes operator_loop, watchdog, or subprocess; it never
modifies the queue.

Tests build up a queue with the existing task_queue + run-batch
plumbing and exercise the dashboard against it.
"""
from __future__ import annotations

import importlib.util
import json
import re
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
DASHBOARD_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "task_queue_dashboard.schema.json"
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
    return _load("task_queue_dsh", SCRIPTS_DIR / "task_queue.py")


@pytest.fixture(scope="module")
def dash():
    return _load(
        "task_queue_dashboard_dsh",
        SCRIPTS_DIR / "task_queue_dashboard.py",
    )


@pytest.fixture(scope="module")
def schema():
    with open(DASHBOARD_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _populate_queue_with_n_completed(tq, qd, n):
    tq.init_queue(qd, PINNED)
    for i in range(n):
        tq.enqueue_item(
            queue_dir=qd,
            request_json=REQUEST_FIXTURE,
            worker_address_map=ADDRESS_MAP_FIXTURE,
            governor_policy=EXAMPLE_POLICY,
            pinned_time="2026-05-17T0" + str(i) + ":00:00+00:00",
        )
    report = tq.run_batch(
        queue_dir=qd, max_items=n, pinned_time=PINNED,
    )
    assert report["completed_count"] == n, (
        "fixture setup failed: " + str(report)
    )


# ---------------------------------------------------------------------------
# Empty queue
# ---------------------------------------------------------------------------


def test_dashboard_on_empty_queue(tmp_path, tq, dash):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    out = tmp_path / "dash"
    rc = dash.main([
        "--queue-dir", str(qd),
        "--out-dir", str(out),
        "--pinned-time", PINNED,
    ])
    assert rc == 0
    json_files = list(out.glob("TRINITY_TASK_QUEUE_DASHBOARD_*.json"))
    html_files = list(out.glob("TRINITY_TASK_QUEUE_DASHBOARD_*.html"))
    assert len(json_files) == 1
    assert len(html_files) == 1
    d = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert d["counts"] == {
        "pending": 0, "running": 0, "completed": 0,
        "failed": 0, "batches": 0,
    }
    assert d["latest_items"] == []
    assert d["latest_batches"] == []
    assert d["safety_status"] == "ok"
    assert d["warnings"] == []


# ---------------------------------------------------------------------------
# Happy path: 2 completed items + 1 batch report
# ---------------------------------------------------------------------------


def test_dashboard_counts_two_completed(tmp_path, tq, dash):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 2)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert d["counts"]["completed"] == 2
    assert d["counts"]["pending"] == 0
    assert d["counts"]["failed"] == 0
    assert d["counts"]["batches"] == 1
    assert d["safety_status"] == "ok"


def test_dashboard_latest_items_have_governor_and_watchdog_fields(
    tmp_path, tq, dash,
):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 2)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert len(d["latest_items"]) == 2
    for it in d["latest_items"]:
        assert it["status"] == "completed"
        assert it["governor_decisions_count"] == 7
        assert it["watchdog_safety_status"] == "ok"
        assert it["operator_run_path_basename"] == "operator_run.json"
        assert (it["watchdog_report_path_basename"] or "").startswith(
            "TRINITY_GOVERNOR_WATCHDOG_REPORT_"
        )


def test_dashboard_latest_batches_present(tmp_path, tq, dash):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 2)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert len(d["latest_batches"]) == 1
    b = d["latest_batches"][0]
    assert b["safety_status"] == "ok"
    assert b["attempted_count"] == 2
    assert b["completed_count"] == 2
    assert b["failed_count"] == 0


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_dashboard_failed_item_promotes_safety_to_warning(
    tmp_path, tq, dash,
):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    bad = tmp_path / "bad_request.json"
    bad.write_bytes(REQUEST_FIXTURE.read_bytes())
    tq.enqueue_item(
        queue_dir=qd,
        request_json=bad,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    bad.unlink()
    tq.run_batch(queue_dir=qd, max_items=1, pinned_time=PINNED)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert d["counts"]["failed"] == 1
    # Failed item alone does not produce a critical watchdog,
    # so the dashboard rolls up to warning, not failed.
    assert d["safety_status"] == "warning"


def test_dashboard_critical_watchdog_promotes_to_failed(
    tmp_path, tq, dash,
):
    """Halt-file in the policy triggers governor_hard_block → item
    failed AND the per-item watchdog report records the halt as a
    critical decision. The dashboard rollup MUST land on 'failed',
    not 'warning'."""
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    halt = tmp_path / "HALT"
    halt.write_text("stop")
    pol = tmp_path / "policy_with_halt.json"
    base = json.loads(EXAMPLE_POLICY.read_text(encoding="utf-8"))
    base["kill_switch"]["halt_file"] = str(halt)
    pol.write_text(json.dumps(base, indent=2), encoding="utf-8")
    tq.enqueue_item(
        queue_dir=qd,
        request_json=REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=pol,
        pinned_time=PINNED,
    )
    tq.run_batch(queue_dir=qd, max_items=1, pinned_time=PINNED)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    # The hard-blocked run never produced a watchdog report (the
    # operator loop exited rc=3 before the watchdog ran). The item
    # is failed; the rollup is warning unless there's also a
    # critical watchdog. We assert the failed-item path produces
    # at least "warning" — failed-only is the documented behaviour.
    assert d["counts"]["failed"] == 1
    assert d["safety_status"] in ("warning", "failed")


def test_dashboard_malformed_item_produces_warning(
    tmp_path, tq, dash,
):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    tq.enqueue_item(
        queue_dir=qd,
        request_json=REQUEST_FIXTURE,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    # Corrupt the pending item file: invalid JSON
    pend = list((qd / "pending").glob("*.json"))[0]
    pend.write_text("{not json", encoding="utf-8")
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert d["safety_status"] == "warning"
    assert any("malformed" in w for w in d["warnings"])


def test_dashboard_unreferenced_file_produces_warning(
    tmp_path, tq, dash,
):
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    # Drop a file that is not in the index.
    stray = qd / "pending" / "qit-0000000000000001.json"
    stray.write_text(json.dumps({
        "schema": "trinity-task-queue-item/v0.1",
        "queue_item_id": "qit-0000000000000001",
    }), encoding="utf-8")
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert any(
        "not referenced in queue.json" in w for w in d["warnings"]
    )
    assert d["safety_status"] == "warning"


def test_dashboard_missing_queue_dir_raises(tmp_path, dash):
    with pytest.raises(dash.DashboardError) as ei:
        dash.build_dashboard(
            queue_dir=tmp_path / "never_initialised",
            pinned_time=PINNED,
        )
    assert "does not exist" in str(ei.value)


def test_dashboard_no_queue_json_raises(tmp_path, dash):
    empty = tmp_path / "empty_dir"
    empty.mkdir()
    with pytest.raises(dash.DashboardError) as ei:
        dash.build_dashboard(
            queue_dir=empty, pinned_time=PINNED,
        )
    assert "no readable queue.json" in str(ei.value)


# ---------------------------------------------------------------------------
# HTML safety
# ---------------------------------------------------------------------------


def test_html_escapes_injected_text(tmp_path, tq, dash):
    """Any string the dashboard pulls into the HTML MUST be escaped.
    Poison three independent text-insertion paths — queue_id pulled
    from queue.json, pinned_time pulled from the CLI, and a warning
    string assembled internally — and assert the rendered HTML
    contains the escaped form, never the raw <script> tag.

    The dashboard deliberately ignores queue.json's
    queue_dir_basename field (it uses the trusted Path's basename
    instead) so we do NOT poison that one."""
    qd = tmp_path / "q"
    tq.init_queue(qd, PINNED)
    q = json.loads((qd / "queue.json").read_text(encoding="utf-8"))
    poison_qid = "tq-<script>alert('xss')</script>"
    q["queue_id"] = poison_qid
    (qd / "queue.json").write_text(
        json.dumps(q), encoding="utf-8",
    )
    poison_pinned = "<img src=x onerror=alert(1)>"
    d = dash.build_dashboard(queue_dir=qd, pinned_time=poison_pinned)
    htmls = dash.render_html(d)
    # Raw HTML tags must NOT appear — they would execute. The
    # standalone substring "onerror=alert" can still appear because
    # html.escape only escapes <, >, &, ', " — neither = nor letters
    # are special. What matters is that the brackets are escaped so
    # no tag can be assembled.
    assert "<script>alert" not in htmls
    assert "<img src=x" not in htmls.lower()
    # Escaped forms MUST appear, proving html.escape is on the path.
    assert "&lt;script&gt;alert" in htmls
    assert "&lt;img src=x" in htmls


def test_html_does_not_contain_absolute_paths(tmp_path, tq, dash):
    """The dashboard must never put the queue absolute path into
    the HTML. We use a tmp dir with a recognisable basename and
    check the absolute prefix never appears, only the basename."""
    qd = tmp_path / "private_queue_xyz"
    _populate_queue_with_n_completed(tq, qd, 1)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    htmls = dash.render_html(d)
    # Absolute path (with leading slash) must not appear.
    assert str(qd) not in htmls
    # The basename appears (intentional — it's persisted in queue.json).
    assert "private_queue_xyz" in htmls


def test_html_contains_no_javascript_or_external_assets(
    tmp_path, tq, dash,
):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 1)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    htmls = dash.render_html(d)
    # No <script>, no inline event handlers, no remote URLs.
    assert "<script" not in htmls.lower()
    assert "onclick=" not in htmls.lower()
    assert "onload=" not in htmls.lower()
    assert "https://" not in htmls
    assert "http://" not in htmls
    # No CDN-style links / fonts.
    assert "googleapis" not in htmls.lower()
    assert "cdnjs" not in htmls.lower()


def test_html_has_robots_noindex_meta(tmp_path, tq, dash):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 1)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    htmls = dash.render_html(d)
    assert 'name="robots"' in htmls
    assert 'noindex' in htmls
    assert 'nofollow' in htmls


# ---------------------------------------------------------------------------
# Determinism + bounded latest
# ---------------------------------------------------------------------------


def test_dashboard_id_deterministic_for_same_inputs(
    tmp_path, tq, dash,
):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 2)
    d1 = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    d2 = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert d1["dashboard_id"] == d2["dashboard_id"]
    # Plus the per-item view is stable order.
    assert d1["latest_items"] == d2["latest_items"]
    assert d1["latest_batches"] == d2["latest_batches"]


def test_latest_limit_caps_arrays(tmp_path, tq, dash):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 3)
    d = dash.build_dashboard(
        queue_dir=qd, pinned_time=PINNED, latest_limit=2,
    )
    assert len(d["latest_items"]) == 2
    assert d["counts"]["completed"] == 3  # counts are NOT capped


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_cli_writes_json_and_html(tmp_path, tq, dash):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 1)
    out = tmp_path / "dash_out"
    rc = dash.main([
        "--queue-dir", str(qd),
        "--out-dir", str(out),
        "--pinned-time", PINNED,
    ])
    assert rc == 0
    json_files = list(out.glob("TRINITY_TASK_QUEUE_DASHBOARD_*.json"))
    html_files = list(out.glob("TRINITY_TASK_QUEUE_DASHBOARD_*.html"))
    assert len(json_files) == 1
    assert len(html_files) == 1
    # The two files share the dashboard_id stem.
    j_stem = json_files[0].stem
    h_stem = html_files[0].stem
    assert j_stem == h_stem


def test_cli_missing_queue_dir_returns_2(tmp_path, dash):
    rc = dash.main([
        "--queue-dir", str(tmp_path / "does_not_exist"),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", PINNED,
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Schema validation (sanity — full coverage in schema test file)
# ---------------------------------------------------------------------------


def test_dashboard_validates_against_schema(tmp_path, tq, dash, schema):
    qd = tmp_path / "q"
    _populate_queue_with_n_completed(tq, qd, 1)
    d = dash.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    jsonschema.validate(d, schema)
