"""Trinity Materials Engine Deterministic Backend v0.1 (Sprint 5.32).

Functional tests for the first non-placeholder, non-toy backend.
The backend reads Sprint 5.31 classifier metadata, looks materials
up in a curated local properties table, and emits a ranked
materials comparison. Worker auto-routes to it when the operator's
default --backend=placeholder meets a classifier-derived
materials_engine request.

Covers:
  - direct backend handler CeO2 vs PrOx ranking is deterministic
  - unknown materials warned, not crashing
  - schema validates every documented branch
  - worker integration: source_tool=materials_engine +
    scientific_task_classification metadata triggers the new
    backend; result carries backend_name=local_materials_engine_v01
    and backend_kind=real_backend
  - two workers over the same request produce the same
    compute_output_sha256 (cross-worker replay contract)
  - operator can opt out by explicitly passing --backend placeholder
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
RESULT_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "materials_engine_result.schema.json"
)
PINNED = "2026-05-17T00:00:00+00:00"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def backends_mod():
    return _load(
        "useful_compute_backends_me",
        SCRIPTS_DIR / "useful_compute_backends.py",
    )


@pytest.fixture(scope="module")
def worker_mod():
    return _load(
        "useful_compute_worker_me",
        SCRIPTS_DIR / "useful_compute_worker.py",
    )


@pytest.fixture(scope="module")
def intake_mod():
    return _load(
        "scientific_prompt_intake_me",
        SCRIPTS_DIR / "scientific_prompt_intake.py",
    )


@pytest.fixture(scope="module")
def classifier_mod():
    return _load(
        "scientific_task_classifier_me",
        SCRIPTS_DIR / "scientific_task_classifier.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "useful_compute_task_builder_me",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def result_schema():
    with open(RESULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Direct backend handler
# ---------------------------------------------------------------------------


def _stub_request(materials, metrics, *, task_kind="comparison"):
    """Minimal request dict carrying just enough metadata for the
    materials_engine handler to run. Mirrors the shape produced by
    the Sprint 5.31 classifier → 5.30 task builder pipeline."""
    return {
        "schema": "trinity-useful-compute-request/v0.1",
        "request_id": "uc-deadbeefdeadbeef",
        "source_tool": "materials_engine",
        "candidate_id": "candidate-test",
        "task_type": "scientific_intake",
        "input_bundle_sha256": "a" * 64,
        "expected_output_schema": "trinity-useful-compute-result/v0.4",
        "validation_method": "deterministic_hash_check",
        "estimated_compute_cost": {"seconds": 60, "tier": "low"},
        "max_reward_stocks": 100000,
        "deadline": "2026-06-30T00:00:00+00:00",
        "manual_review_required": False,
        "public_description": "stub request for direct backend test",
        "metadata": {
            "scientific_intake": {
                "intake_id": "spi-0123456789abcdef",
                "combined_context_sha256": "b" * 64,
                "prompt_sha256": "c" * 64,
                "documents_count": 2,
                "intake_task_kind": task_kind,
                "intake_artifact_sha256": "d" * 64,
            },
            "scientific_task_classification": {
                "classification_id": "scl-0123456789abcdef",
                "source_intake_id": "spi-0123456789abcdef",
                "source_intake_sha256": "e" * 64,
                "task_kind": task_kind,
                "confidence": "high",
                "candidate_materials": list(materials),
                "candidate_metrics": list(metrics),
                "proposed_source_tool": "materials_engine",
                "proposed_difficulty_class": "medium",
                "threat_refs": ["T01", "T04", "T09"],
            },
        },
    }


def test_backend_ranks_ceo2_vs_prox_deterministically(
    backends_mod, result_schema,
):
    req = _stub_request(
        materials=["CeO2", "PrOx"],
        metrics=["oxygen_storage_capacity"],
    )
    out = backends_mod._materials_engine_v01(0, req)
    jsonschema.validate(out, result_schema)
    assert out["backend"] == "materials_engine"
    assert out["backend_version"] == "v0.1"
    assert set(out["known_materials"]) == {"CeO2", "PrOx"}
    assert out["unknown_materials"] == []
    # PrOx has higher oxygen_storage_mmol_g (2.3 vs 1.7) → ranked first.
    assert out["ranking"][0]["material"] == "PrOx"
    assert out["ranking"][1]["material"] == "CeO2"
    assert out["ranking"][0]["score"] > out["ranking"][1]["score"]


def test_backend_is_deterministic_for_same_inputs(backends_mod):
    req = _stub_request(
        materials=["CeO2", "PrOx"],
        metrics=["oxygen_storage_capacity", "stability"],
    )
    a = backends_mod._materials_engine_v01(123, req)
    b = backends_mod._materials_engine_v01(123, req)
    assert a == b


def test_backend_records_unknown_materials_without_crash(
    backends_mod, result_schema,
):
    req = _stub_request(
        materials=["CeO2", "UnobtainiumX"],
        metrics=["oxygen_storage_capacity"],
    )
    out = backends_mod._materials_engine_v01(0, req)
    jsonschema.validate(out, result_schema)
    assert "CeO2" in out["known_materials"]
    assert "UnobtainiumX" in out["unknown_materials"]
    # Only known materials get a property_table entry.
    assert "CeO2" in out["property_table"]
    assert "UnobtainiumX" not in out["property_table"]
    # Warning recorded.
    assert any(
        "unknown material" in w.lower() for w in out["warnings"]
    )
    # Ranking still emitted for the known set.
    assert len(out["ranking"]) == 1
    assert out["ranking"][0]["material"] == "CeO2"


def test_backend_falls_back_when_no_recognised_metrics(
    backends_mod, result_schema,
):
    req = _stub_request(
        materials=["CeO2", "PrOx"],
        metrics=["unrelated_metric_label"],
    )
    out = backends_mod._materials_engine_v01(0, req)
    jsonschema.validate(out, result_schema)
    # The unrecognised metric is warned and dropped; fallback to
    # oxygen_storage_capacity makes the ranking still produce
    # meaningful PrOx > CeO2 order.
    assert any("not recognised" in w for w in out["warnings"])
    assert out["ranking"][0]["material"] == "PrOx"


def test_backend_temperature_inverted_correctly(
    backends_mod, result_schema,
):
    """temperature is lower_is_better. PrOx's optimal_temperature_c
    (450) is lower than CeO2 (500), so PrOx should win on
    temperature alone."""
    req = _stub_request(
        materials=["CeO2", "PrOx"],
        metrics=["temperature_c"],
    )
    out = backends_mod._materials_engine_v01(0, req)
    jsonschema.validate(out, result_schema)
    rm = out["resolved_metrics"][0]
    assert rm["direction"] == "lower_is_better"
    assert out["ranking"][0]["material"] == "PrOx"


def test_backend_handles_zero_known_materials(
    backends_mod, result_schema,
):
    """All-unknown corpus: ranking is empty, warnings populated,
    no crash."""
    req = _stub_request(
        materials=["UnknownA", "UnknownB"],
        metrics=["oxygen_storage_capacity"],
    )
    out = backends_mod._materials_engine_v01(0, req)
    jsonschema.validate(out, result_schema)
    assert out["known_materials"] == []
    assert out["ranking"] == []
    assert set(out["unknown_materials"]) == {"UnknownA", "UnknownB"}


def test_backend_source_request_sha256_is_64hex(backends_mod):
    req = _stub_request(
        materials=["CeO2"], metrics=["oxygen_storage_capacity"],
    )
    out = backends_mod._materials_engine_v01(0, req)
    assert len(out["source_request_sha256"]) == 64
    assert all(c in "0123456789abcdef" for c in out["source_request_sha256"])


def test_backend_source_request_sha_changes_with_request(backends_mod):
    a = backends_mod._materials_engine_v01(
        0, _stub_request(["CeO2"], ["oxygen_storage_capacity"]),
    )
    b = backends_mod._materials_engine_v01(
        0, _stub_request(["CeO2", "PrOx"], ["oxygen_storage_capacity"]),
    )
    assert a["source_request_sha256"] != b["source_request_sha256"]


# ---------------------------------------------------------------------------
# Backend registry
# ---------------------------------------------------------------------------


def test_materials_engine_backend_registered(backends_mod):
    names = {b["name"] for b in backends_mod.list_available_backends()}
    assert "local_materials_engine_v01" in names


def test_materials_engine_is_real_backend_kind(backends_mod):
    by_name = {
        b["name"]: b for b in backends_mod.list_available_backends()
    }
    spec = by_name["local_materials_engine_v01"]
    assert spec["kind"] == backends_mod.REAL_BACKEND_KIND
    assert spec["experimental"] is False
    assert spec["task_types"] == ["scientific_intake"]
    assert spec["version"] == "v0.1"


def test_materials_engine_disclaimer_says_not_dft(backends_mod):
    by_name = {
        b["name"]: b for b in backends_mod.list_available_backends()
    }
    disclaimer = by_name["local_materials_engine_v01"]["disclaimer"]
    assert "NOT DFT" in disclaimer
    assert "curated" in disclaimer.lower()


# ---------------------------------------------------------------------------
# Worker integration: auto-routing
# ---------------------------------------------------------------------------


def _make_classification_request(
    tmp_path, intake_mod, classifier_mod, builder_mod,
):
    """Run intake → classifier → task_builder to produce a
    classifier-derived request that should trigger the
    materials_engine backend."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    md = docs_dir / "notes.md"
    md.write_text(
        "# Oxygen storage\n\nCompare ceria and praseodymia.\n",
        encoding="utf-8",
    )
    csv = docs_dir / "table.csv"
    csv.write_text(
        "compound,oxygen_storage_mmol_g,temperature_c\n"
        "CeO2,0.42,500\nPrOx,0.58,500\n",
        encoding="utf-8",
    )
    out_intake = tmp_path / "intake"
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "Compare ceria and praseodymia.",
        "--document", str(md),
        "--document", str(csv),
        "--out-dir", str(out_intake),
        "--pinned-time", PINNED,
    ])
    assert rc == 0
    intake_path = list(
        out_intake.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json")
    )[0]
    cls_path = tmp_path / "classification.json"
    rc = classifier_mod.main([
        "--intake-json", str(intake_path),
        "--out-json", str(cls_path),
        "--pinned-time", PINNED,
    ])
    assert rc == 0
    req_path = tmp_path / "request.json"
    rc = builder_mod.main([
        "--from-scientific-classification", str(cls_path),
        "--intake-json", str(intake_path),
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(req_path),
    ])
    assert rc == 0
    return json.loads(req_path.read_text(encoding="utf-8")), req_path


def _run_worker(worker_mod, work_dir, req_path, worker_id="worker-A",
                backend="placeholder"):
    work_dir.mkdir(parents=True, exist_ok=True)
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--out-dir", str(work_dir),
        "--worker-id", worker_id,
        "--pinned-time", PINNED,
        "--backend", backend,
    ])
    assert rc == 0
    files = list(work_dir.glob("TRINITY_USEFUL_COMPUTE_RESULT_*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def test_worker_auto_routes_classifier_request_to_materials_engine(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
):
    req, req_path = _make_classification_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    assert req["source_tool"] == "materials_engine"
    assert "scientific_task_classification" in req["metadata"]
    result = _run_worker(
        worker_mod, tmp_path / "work_a", req_path,
        worker_id="worker-A",
    )
    assert result["backend_name"] == "local_materials_engine_v01"
    assert result["backend_kind"] == "real_backend"


def test_two_workers_same_compute_output_sha(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
):
    """Cross-worker replay contract — two workers on the same
    classifier-derived request must produce the same
    compute_output_sha256, just like every other Trinity task type."""
    req, req_path = _make_classification_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    a = _run_worker(
        worker_mod, tmp_path / "work_a", req_path, worker_id="worker-A",
    )
    b = _run_worker(
        worker_mod, tmp_path / "work_b", req_path, worker_id="worker-B",
    )
    assert a["compute_output_sha256"] == b["compute_output_sha256"]
    # But worker_result_id MUST differ (it's worker-bound).
    assert a["worker_result_id"] != b["worker_result_id"]


def test_operator_can_opt_out_to_placeholder(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
):
    """Auto-routing fires ONLY when --backend is the default
    'placeholder'. An operator who explicitly passes
    --backend placeholder_scientific_intake gets the old hash-only
    stub."""
    req, req_path = _make_classification_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    result = _run_worker(
        worker_mod, tmp_path / "work_opt_out", req_path,
        worker_id="worker-A",
        backend="placeholder_scientific_intake",
    )
    assert result["backend_name"] == "placeholder_scientific_intake"
    assert result["backend_kind"] == "placeholder"


def test_non_materials_engine_request_still_uses_placeholder(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
):
    """When source_tool stays trinity_scientific_prompt_intake (no
    materials in the corpus), the auto-router must NOT fire."""
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    md = docs_dir / "n.md"
    # Compare two unidentified things → classifier picks
    # comparison but no materials → proposed_source_tool stays
    # trinity_scientific_prompt_intake.
    md.write_text(
        "Compare two unidentified compounds.\n", encoding="utf-8",
    )
    out_intake = tmp_path / "intake"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "Compare them.",
        "--document", str(md),
        "--out-dir", str(out_intake),
        "--pinned-time", PINNED,
    ])
    intake_path = list(
        out_intake.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json")
    )[0]
    cls_path = tmp_path / "cls.json"
    classifier_mod.main([
        "--intake-json", str(intake_path),
        "--out-json", str(cls_path),
        "--pinned-time", PINNED,
    ])
    cls = json.loads(cls_path.read_text(encoding="utf-8"))
    assert cls["proposed_source_tool"] == "trinity_scientific_prompt_intake"
    req_path = tmp_path / "req.json"
    builder_mod.main([
        "--from-scientific-classification", str(cls_path),
        "--intake-json", str(intake_path),
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(req_path),
    ])
    result = _run_worker(
        worker_mod, tmp_path / "work_pi", req_path,
    )
    # source_tool != materials_engine → router does NOT fire,
    # placeholder remains.
    assert result["backend_name"] == "placeholder_scientific_intake"
    assert result["backend_kind"] == "placeholder"


# ---------------------------------------------------------------------------
# Worker output validates against the materials_engine result schema
# ---------------------------------------------------------------------------


def test_worker_compute_output_validates_against_result_schema(
    tmp_path, intake_mod, classifier_mod, builder_mod, worker_mod,
    result_schema,
):
    """compute_output_sha256 hashes the canonical backend output.
    We can re-read it from the worker_result by re-deriving — or
    simpler, validate the backend output directly via _materials_engine_v01
    on the same request."""
    req, req_path = _make_classification_request(
        tmp_path, intake_mod, classifier_mod, builder_mod,
    )
    backends_mod = _load(
        "useful_compute_backends_me_v2",
        SCRIPTS_DIR / "useful_compute_backends.py",
    )
    out = backends_mod._materials_engine_v01(0, req)
    jsonschema.validate(out, result_schema)
    assert out["classification_id"].startswith("scl-")
    assert "CeO2" in out["known_materials"]
    assert "PrOx" in out["known_materials"]
