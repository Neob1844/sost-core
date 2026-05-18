"""Trinity Materials Engine Result Surfacing v0.1 (Sprint 5.33).

End-to-end functional tests for the surfacing layer that exposes
the Sprint 5.32 materials_engine result in three audit-friendly
places without changing compute_output_sha256 or any reward /
payment behaviour:

  1) worker_result.materials_engine_summary  (compact projection)
  2) operator_run.materials_engine_summary_count
     operator_run.materials_engine_top_materials                 (roll-up)
  3) dashboard.latest_items[*].materials_engine_*               (per-item)

Critical invariant: compute_output_sha256 stability across workers
is preserved. The summary lives OUTSIDE the hashed output_blob.
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
SUMMARY_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "materials_engine_summary.schema.json"
)
RESULT_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_result.schema.json"
)
OPERATOR_RUN_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_operator_run.schema.json"
)
DASHBOARD_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "task_queue_dashboard.schema.json"
)
FIXTURES = REPO_ROOT / "tests" / "trinity" / "fixtures" / "useful_compute"
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
def intake_mod():
    return _load("spi_surf", SCRIPTS_DIR / "scientific_prompt_intake.py")


@pytest.fixture(scope="module")
def classifier_mod():
    return _load(
        "stc_surf", SCRIPTS_DIR / "scientific_task_classifier.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "uctb_surf", SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def worker_mod():
    return _load(
        "ucw_surf", SCRIPTS_DIR / "useful_compute_worker.py",
    )


@pytest.fixture(scope="module")
def operator_loop_mod():
    return _load(
        "ucol_surf", SCRIPTS_DIR / "useful_compute_operator_loop.py",
    )


@pytest.fixture(scope="module")
def task_queue_mod():
    return _load("tq_surf", SCRIPTS_DIR / "task_queue.py")


@pytest.fixture(scope="module")
def dashboard_mod():
    return _load(
        "tqd_surf", SCRIPTS_DIR / "task_queue_dashboard.py",
    )


@pytest.fixture(scope="module")
def summary_schema():
    with open(SUMMARY_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def result_schema():
    with open(RESULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _produce_classifier_request(
    tmp_path, intake_mod, classifier_mod, builder_mod,
):
    """Run intake -> classifier -> task_builder over the canonical
    'Compare ceria and praseodymia' demo corpus."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "n.md").write_text(
        "# Notes\n\nCompare ceria and praseodymia.\n", encoding="utf-8",
    )
    (docs / "t.csv").write_text(
        "compound,oxygen_storage_mmol_g,temperature_c\n"
        "CeO2,0.42,500\nPrOx,0.58,500\n",
        encoding="utf-8",
    )
    out_intake = tmp_path / "intake"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "Compare ceria and praseodymia.",
        "--document", str(docs / "n.md"),
        "--document", str(docs / "t.csv"),
        "--out-dir", str(out_intake),
        "--pinned-time", PINNED,
    ])
    intake_path = next(out_intake.glob(
        "TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json",
    ))
    cls_path = tmp_path / "classification.json"
    classifier_mod.main([
        "--intake-json", str(intake_path),
        "--out-json", str(cls_path),
        "--pinned-time", PINNED,
    ])
    req_path = tmp_path / "request.json"
    builder_mod.main([
        "--from-scientific-classification", str(cls_path),
        "--intake-json", str(intake_path),
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(req_path),
    ])
    return req_path


def _run_one_worker(worker_mod, work_dir, req_path, worker_id):
    work_dir.mkdir(parents=True, exist_ok=True)
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--out-dir", str(work_dir),
        "--worker-id", worker_id,
        "--pinned-time", PINNED,
    ])
    assert rc == 0
    files = list(work_dir.glob("TRINITY_USEFUL_COMPUTE_RESULT_*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Worker result: summary present, hash stable
# ---------------------------------------------------------------------------


def test_worker_result_includes_materials_engine_summary(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
):
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    r = _run_one_worker(
        worker_mod, tmp_path / "wa", req_path, "worker-A",
    )
    assert "materials_engine_summary" in r
    s = r["materials_engine_summary"]
    assert s["schema"] == "trinity-materials-engine-summary/v0.1"
    assert s["backend_name"] == "local_materials_engine_v01"
    assert s["backend_kind"] == "real_backend"
    assert s["top_ranked_material"] == "PrOx"
    assert 0 < s["top_ranked_score"] <= 1.0
    assert set(s["known_materials"]) == {"CeO2", "PrOx"}
    assert len(s["ranking"]) == 2
    assert s["ranking"][0]["material"] == "PrOx"
    assert s["ranking"][1]["material"] == "CeO2"


def test_summary_validates_against_schema(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
    summary_schema,
):
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    r = _run_one_worker(
        worker_mod, tmp_path / "wa", req_path, "worker-A",
    )
    jsonschema.validate(r["materials_engine_summary"], summary_schema)


def test_compute_output_sha256_unchanged_by_summary(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
):
    """The MOST IMPORTANT invariant. Two workers on the same
    classifier-derived request must still produce identical
    compute_output_sha256 — the summary lives outside the
    hashed output_blob so adding it does not affect the hash."""
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    a = _run_one_worker(
        worker_mod, tmp_path / "wa", req_path, "worker-A",
    )
    b = _run_one_worker(
        worker_mod, tmp_path / "wb", req_path, "worker-B",
    )
    assert a["compute_output_sha256"] == b["compute_output_sha256"]
    # Both also have the summary attached, with identical content
    # (sumary itself is deterministic for the same backend output).
    assert "materials_engine_summary" in a
    assert "materials_engine_summary" in b
    assert a["materials_engine_summary"] == b["materials_engine_summary"]


def test_safety_status_still_manual_review_required(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
):
    """Adding the summary surface MUST NOT flip manual_review_required
    off for real_backend results — that's a non-goal hard invariant."""
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    r = _run_one_worker(
        worker_mod, tmp_path / "wa", req_path, "worker-A",
    )
    ss = r["safety_status"]
    assert ss["manual_review_required"] is True
    assert ss["no_wallet_access"] is True
    assert ss["no_private_keys"] is True
    assert ss["no_automatic_payout"] is True
    assert ss["no_network_required"] is True


def test_full_worker_result_validates_against_extended_schema(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
    result_schema,
):
    """The Sprint 5.33 result schema extension must accept the
    augmented worker result without breaking validation."""
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    r = _run_one_worker(
        worker_mod, tmp_path / "wa", req_path, "worker-A",
    )
    jsonschema.validate(r, result_schema)


def test_non_materials_engine_worker_has_no_summary(
    tmp_path, worker_mod,
):
    """For requests that route to placeholder_scientific_intake
    (no classifier metadata, source_tool != materials_engine), the
    summary must be absent — present-on-non-materials would
    confuse downstream consumers."""
    # Build a minimal request that does NOT trigger the auto-router.
    req = {
        "schema": "trinity-useful-compute-request/v0.1",
        "request_id": "uc-feedfacefeedface",
        "source_tool": "trinity_orchestrator",
        "candidate_id": "cand-test",
        "task_type": "other",
        "input_bundle_sha256": "a" * 64,
        "expected_output_schema": "trinity-useful-compute-result/v0.4",
        "validation_method": "deterministic_hash_check",
        "estimated_compute_cost": {"seconds": 60, "tier": "low"},
        "max_reward_stocks": 100000,
        "deadline": "2026-06-30T00:00:00+00:00",
        "manual_review_required": False,
        "public_description": "non-materials request — should not produce summary",
    }
    req_path = tmp_path / "req.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    r = _run_one_worker(
        worker_mod, tmp_path / "wa", req_path, "worker-A",
    )
    assert "materials_engine_summary" not in r


# ---------------------------------------------------------------------------
# Operator run roll-up
# ---------------------------------------------------------------------------


def test_operator_run_rolls_up_materials_engine_summaries(
    tmp_path, intake_mod, classifier_mod, builder_mod, operator_loop_mod,
):
    """End-to-end through operator_loop. With 2 default workers (A
    and B), both materials_engine, the operator_run.json should
    report materials_engine_summary_count >= 2 and at least PrOx
    in materials_engine_top_materials."""
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    out_dir = tmp_path / "run"
    rc = operator_loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(out_dir),
        "--require-confirmation-token",
        "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP",
        "--worker-address-map", str(ADDRESS_MAP_FIXTURE),
        "--max-total-stocks", "10000000",
        "--pool-balance-stocks", "100000000",
        "--pinned-time", PINNED,
        "--worker-id", "worker-A",
        "--worker-id", "worker-B",
        "--request-json", str(req_path),
    ])
    assert rc == 0
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    assert state["materials_engine_summary_count"] >= 2
    assert "PrOx" in state["materials_engine_top_materials"]
    # The roll-up array is deduplicated + sorted.
    assert state["materials_engine_top_materials"] == sorted(
        set(state["materials_engine_top_materials"])
    )


def test_operator_run_default_zero_when_no_materials_engine(
    tmp_path, operator_loop_mod,
):
    """A non-classifier request (uses placeholder_scientific_intake)
    runs through the same operator_loop; the roll-up must default
    to 0 and []. The fields are always present so downstream
    consumers see a uniform schema."""
    # Use the existing scientific_intake fixture (no classifier),
    # which routes to placeholder.
    fixture_req = (
        REPO_ROOT / "tests" / "trinity" / "fixtures"
        / "useful_compute" / "request_scientific_intake.json"
    )
    out_dir = tmp_path / "run"
    rc = operator_loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(out_dir),
        "--require-confirmation-token",
        "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP",
        "--worker-address-map", str(ADDRESS_MAP_FIXTURE),
        "--max-total-stocks", "10000000",
        "--pool-balance-stocks", "100000000",
        "--pinned-time", PINNED,
        "--worker-id", "worker-A",
        "--worker-id", "worker-B",
        "--request-json", str(fixture_req),
    ])
    assert rc == 0
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    assert state["materials_engine_summary_count"] == 0
    assert state["materials_engine_top_materials"] == []


# ---------------------------------------------------------------------------
# Dashboard surfacing
# ---------------------------------------------------------------------------


def test_dashboard_surfaces_materials_engine_per_item(
    tmp_path, intake_mod, classifier_mod, builder_mod,
    task_queue_mod, dashboard_mod,
):
    """End-to-end through queue: enqueue a classifier request,
    run-once, then build the dashboard. The completed item in
    latest_items must carry materials_engine_top_material=PrOx and
    the HTML must display it."""
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    qd = tmp_path / "queue"
    task_queue_mod.init_queue(qd, PINNED)
    task_queue_mod.enqueue_item(
        queue_dir=qd,
        request_json=req_path,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    res = task_queue_mod.run_once(qd)
    assert res["status"] == "completed", (
        "queue run-once failed: " + str(res.get("last_error"))
    )
    d = dashboard_mod.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    assert len(d["latest_items"]) == 1
    it = d["latest_items"][0]
    assert it["materials_engine_summary_count"] >= 1
    assert it["materials_engine_top_material"] == "PrOx"
    assert it["materials_engine_known_count"] == 2
    assert it["materials_engine_unknown_count"] == 0
    # HTML render exposes the material name.
    htmls = dashboard_mod.render_html(d)
    assert "PrOx" in htmls
    assert "materials_engine" in htmls


def test_dashboard_html_does_not_leak_tmp_paths(
    tmp_path, intake_mod, classifier_mod, builder_mod,
    task_queue_mod, dashboard_mod,
):
    """The dashboard HTML must not contain absolute paths to the
    queue tmp dir — the Sprint 5.28 privacy contract is preserved
    by Sprint 5.33's additions."""
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    qd = tmp_path / "private_queue_xyz"
    task_queue_mod.init_queue(qd, PINNED)
    task_queue_mod.enqueue_item(
        queue_dir=qd,
        request_json=req_path,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    task_queue_mod.run_once(qd)
    d = dashboard_mod.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    htmls = dashboard_mod.render_html(d)
    assert str(qd) not in htmls
    # The queue basename IS in the html (intentional, Sprint 5.28).
    assert "private_queue_xyz" in htmls


def test_dashboard_html_has_no_js_or_external_assets(
    tmp_path, intake_mod, classifier_mod, builder_mod,
    task_queue_mod, dashboard_mod,
):
    """Sprint 5.33's added materials_engine cell must keep the
    Sprint 5.28 'no JS, no external assets' contract."""
    req_path = _produce_classifier_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    qd = tmp_path / "queue"
    task_queue_mod.init_queue(qd, PINNED)
    task_queue_mod.enqueue_item(
        queue_dir=qd,
        request_json=req_path,
        worker_address_map=ADDRESS_MAP_FIXTURE,
        governor_policy=EXAMPLE_POLICY,
        pinned_time=PINNED,
    )
    task_queue_mod.run_once(qd)
    d = dashboard_mod.build_dashboard(queue_dir=qd, pinned_time=PINNED)
    htmls = dashboard_mod.render_html(d)
    assert "<script" not in htmls.lower()
    assert "onclick=" not in htmls.lower()
    assert "onload=" not in htmls.lower()
    assert "https://" not in htmls
    assert "http://" not in htmls


# ---------------------------------------------------------------------------
# Direct unit tests for the helper
# ---------------------------------------------------------------------------


def test_build_summary_returns_none_for_non_materials_output(
    worker_mod,
):
    # A stub spec object — just needs .name and .kind attributes.
    class _Spec:
        name = "local_materials_engine_v01"
        kind = "real_backend"
    # Non-materials_engine output: missing the right schema string.
    out = worker_mod._build_materials_engine_summary(
        {"schema": "trinity-other/v0.1"}, _Spec(),
    )
    assert out is None
    # Non-dict input: also None.
    out2 = worker_mod._build_materials_engine_summary("not a dict", _Spec())
    assert out2 is None


def test_build_summary_caps_ranking_at_5(worker_mod):
    class _Spec:
        name = "local_materials_engine_v01"
        kind = "real_backend"
    big_ranking = [
        {"material": "M" + str(i), "score": (10 - i) / 10.0}
        for i in range(10)
    ]
    out = worker_mod._build_materials_engine_summary({
        "schema": "trinity-materials-engine-result/v0.1",
        "ranking": big_ranking,
        "known_materials": [r["material"] for r in big_ranking],
        "unknown_materials": [],
        "resolved_metrics": [],
        "classification_id": "scl-0123456789abcdef",
        "warnings": [],
        "limitations": [],
    }, _Spec())
    assert len(out["ranking"]) == 5
    # Order preserved.
    assert out["ranking"][0]["material"] == "M0"
    assert out["top_ranked_material"] == "M0"
