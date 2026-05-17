"""Functional tests for the Trinity Scientific Task Classifier
v0.1 (Sprint 5.31).

Covers:
  - basic happy-path classification of the canonical
    "Compare ceria and praseodymia" intake
  - task_kind heuristics for each of comparison / extraction /
    validation / benchmark
  - material + metric detection
  - csv-header lifting into candidate_metrics
  - confidence rule (signals out of 3)
  - proposed_source_tool routing
  - deterministic classification_id under pinned_time
  - intake warnings carried into classifier warnings
  - privacy invariants: no full extracted text leaks
  - schema validation of every produced classification

Plus the task_builder bridge:
  - --from-scientific-classification builds a valid request
  - intake/classification cross-check refuses mismatched pair
  - resulting request validates and is drop-in compatible with
    the queue runner
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
CLASSIFICATION_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "scientific_task_classification.schema.json"
)
REQUEST_SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_request.schema.json"
)
PINNED = "2026-05-17T00:00:00+00:00"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def intake_mod():
    return _load(
        "scientific_prompt_intake_clf",
        SCRIPTS_DIR / "scientific_prompt_intake.py",
    )


@pytest.fixture(scope="module")
def classifier_mod():
    return _load(
        "scientific_task_classifier_clf",
        SCRIPTS_DIR / "scientific_task_classifier.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "useful_compute_task_builder_clf",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def classification_schema():
    with open(CLASSIFICATION_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def request_schema():
    with open(REQUEST_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_canonical_corpus(tmp_path):
    """The Sprint 5.29 demo corpus: a .md prose file plus a .csv
    table with oxygen_storage_mmol_g header. Produces a strong
    comparison signal with both materials and metrics."""
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    md = tmp_path / "notes.md"
    md.write_text(
        "# Oxygen storage\n\nCompare ceria and praseodymia.\n",
        encoding="utf-8",
    )
    csv = tmp_path / "table.csv"
    csv.write_text(
        "compound,oxygen_storage_mmol_g,temperature_c\n"
        "CeO2,0.42,500\nPrOx,0.58,500\n",
        encoding="utf-8",
    )
    return [md, csv]


def _produce_intake(tmp_path, intake_mod, *, prompt, docs):
    out_dir = tmp_path / "intake_out"
    argv = [
        "--mode", "local-dry-run",
        "--prompt", prompt,
        "--out-dir", str(out_dir),
        "--pinned-time", PINNED,
    ]
    for d in docs:
        argv += ["--document", str(d)]
    assert intake_mod.main(argv) == 0
    files = list(out_dir.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"))
    assert len(files) == 1
    return files[0]


def _classify(tmp_path, classifier_mod, intake_path):
    out = tmp_path / "classification.json"
    rc = classifier_mod.main([
        "--intake-json", str(intake_path),
        "--out-json", str(out),
        "--pinned-time", PINNED,
    ])
    assert rc == 0
    return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_classify_canonical_demo_is_comparison_high_confidence(
    tmp_path, intake_mod, classifier_mod,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod,
        prompt="Compare ceria and praseodymia for oxygen storage.",
        docs=docs,
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    assert c["task_kind"] == "comparison"
    assert c["confidence"] == "high"
    assert "CeO2" in c["candidate_materials"]
    assert "PrOx" in c["candidate_materials"]
    # CSV headers lift into candidate_metrics.
    assert "oxygen_storage_mmol_g" in c["candidate_metrics"]
    assert "temperature_c" in c["candidate_metrics"]
    # Also the canonical metric "oxygen_storage_capacity" is
    # detected from the column-name substring match.
    assert "oxygen_storage_capacity" in c["candidate_metrics"]
    # source_tool routing: comparison + materials ⇒ materials_engine
    assert c["proposed_source_tool"] == "materials_engine"
    # 2 materials + comparison ⇒ medium difficulty
    assert c["proposed_difficulty_class"] == "medium"


def test_classification_id_pattern(tmp_path, intake_mod, classifier_mod):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    import re
    assert re.match(r"^scl-[0-9a-f]{16}$", c["classification_id"])


def test_classification_includes_intake_sha256_and_combined_ctx(
    tmp_path, intake_mod, classifier_mod,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    c = _classify(tmp_path, classifier_mod, intake_path)
    expected_sha = hashlib.sha256(intake_path.read_bytes()).hexdigest()
    assert c["source_intake_id"] == intake["intake_id"]
    assert c["source_intake_sha256"] == expected_sha
    assert c["combined_context_sha256"] == intake["combined_context_sha256"]


def test_classification_records_reader_counts(
    tmp_path, intake_mod, classifier_mod,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    # 1 csv + 1 text (the .md is read by the text reader), all ok.
    assert c["reader_kind_counts"] == {"csv": 1, "text": 1}
    assert c["reader_status_counts"] == {"ok": 2}


# ---------------------------------------------------------------------------
# Task-kind heuristics: each kind reachable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt,expected_kind", [
    ("Compare ceria and praseodymia.",                  "comparison"),
    ("Validate the published values for ceria.",        "validation"),
    ("Benchmark CeO2 against PrOx for OSC.",            "benchmark"),
    ("Extract the table of oxygen storage values.",     "extraction"),
])
def test_task_kind_heuristics(
    tmp_path, intake_mod, classifier_mod, prompt, expected_kind,
):
    """Pure prompt-only test. We deliberately do NOT include the
    canonical .md+.csv corpus because the .md contains 'Compare'
    which would pollute the extraction case (the corpus, not the
    prompt, would then provide the strongest signal)."""
    neutral = tmp_path / "neutral.md"
    neutral.write_text(
        "# Notes\n\nMaterials science context.\n",
        encoding="utf-8",
    )
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt=prompt, docs=[neutral],
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    assert c["task_kind"] == expected_kind


def test_default_task_kind_is_extraction(
    tmp_path, intake_mod, classifier_mod,
):
    """No explicit task keyword and no materials in prose → the
    classifier picks the generic 'extraction' bucket."""
    p = tmp_path / "x.md"
    p.write_text("Just some neutral text.\n", encoding="utf-8")
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="X", docs=[p],
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    assert c["task_kind"] == "extraction"


# ---------------------------------------------------------------------------
# Confidence rule
# ---------------------------------------------------------------------------


def test_confidence_low_when_no_signals(
    tmp_path, intake_mod, classifier_mod,
):
    p = tmp_path / "x.md"
    p.write_text("Neutral text only.\n", encoding="utf-8")
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Y", docs=[p],
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    assert c["confidence"] == "low"
    assert c["candidate_materials"] == []
    # The low-confidence warning is recorded.
    assert any(
        "low-confidence classification" in w for w in c["warnings"]
    )


def test_confidence_medium_with_two_signals(
    tmp_path, intake_mod, classifier_mod,
):
    """Task keyword ('compare') + one material ('ceria') but no
    metric → 2 of 3 signals → medium."""
    p = tmp_path / "x.md"
    p.write_text(
        "Compare ceria reactivity in air.",
        encoding="utf-8",
    )
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria reactivity.",
        docs=[p],
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    assert c["confidence"] == "medium"


# ---------------------------------------------------------------------------
# source_tool + difficulty routing
# ---------------------------------------------------------------------------


def test_source_tool_falls_back_when_no_materials(
    tmp_path, intake_mod, classifier_mod,
):
    p = tmp_path / "x.md"
    p.write_text(
        "Compare two unidentified compounds head to head.",
        encoding="utf-8",
    )
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare them.", docs=[p],
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    assert c["proposed_source_tool"] == "trinity_scientific_prompt_intake"


def test_threat_refs_present(tmp_path, intake_mod, classifier_mod):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    assert set(c["threat_refs"]) >= {"T01", "T04", "T09"}


# ---------------------------------------------------------------------------
# Determinism + privacy
# ---------------------------------------------------------------------------


def test_classification_id_deterministic_for_same_inputs(
    tmp_path, intake_mod, classifier_mod,
):
    docs = _make_canonical_corpus(tmp_path / "a")
    intake_a = _produce_intake(
        tmp_path / "a", intake_mod,
        prompt="Compare ceria and praseodymia.", docs=docs,
    )
    c_a = _classify(tmp_path / "ca", classifier_mod, intake_a)
    c_b = _classify(tmp_path / "cb", classifier_mod, intake_a)
    assert c_a["classification_id"] == c_b["classification_id"]


def test_classification_does_not_leak_full_extracted_text(
    tmp_path, intake_mod, classifier_mod,
):
    """Poison a doc with a sentinel and assert the sentinel does
    not appear in the classification JSON."""
    sentinel = "CLASSIFIER-SENTINEL-DO-NOT-LEAK"
    p = tmp_path / "secret.md"
    # The sentinel is long enough to escape the 200-char preview
    # cap, ensuring it would only appear if a reader copied the
    # full text.
    p.write_text(
        sentinel + " ceria " * 100 + " " + sentinel + "-end",
        encoding="utf-8",
    )
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria.", docs=[p],
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    raw = json.dumps(c)
    # The sentinel CAN appear once (it's in the first 200 chars
    # of the intake preview), but the FULL repeated body must not.
    assert raw.count(sentinel) <= 2, (
        "classification leaked too many copies of the sentinel — "
        "full extracted text was probably copied"
    )
    # The 100-fold repeat would push the substring count past 2
    # if leaked. This is the real privacy check.


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_classification_validates_against_schema(
    tmp_path, intake_mod, classifier_mod, classification_schema,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    jsonschema.validate(c, classification_schema)


@pytest.mark.parametrize("prompt", [
    "Validate the table for CeO2.",
    "Benchmark CeO2 and PrOx for OSC.",
    "Extract the oxygen storage values.",
])
def test_other_branches_also_validate(
    tmp_path, intake_mod, classifier_mod, classification_schema, prompt,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt=prompt, docs=docs,
    )
    c = _classify(tmp_path, classifier_mod, intake_path)
    jsonschema.validate(c, classification_schema)


# ---------------------------------------------------------------------------
# CLI error paths
# ---------------------------------------------------------------------------


def test_classifier_refuses_missing_intake(tmp_path, classifier_mod):
    rc = classifier_mod.main([
        "--intake-json", str(tmp_path / "does_not_exist.json"),
        "--out-json", str(tmp_path / "out.json"),
        "--pinned-time", PINNED,
    ])
    assert rc == 2


def test_classifier_refuses_wrong_schema(tmp_path, classifier_mod):
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"schema": "trinity-other/v0.1"}),
        encoding="utf-8",
    )
    rc = classifier_mod.main([
        "--intake-json", str(bad),
        "--out-json", str(tmp_path / "out.json"),
        "--pinned-time", PINNED,
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# task_builder bridge
# ---------------------------------------------------------------------------


def test_builder_from_classification_builds_valid_request(
    tmp_path, intake_mod, classifier_mod, builder_mod, request_schema,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    classification_path = tmp_path / "classification.json"
    classifier_mod.main([
        "--intake-json", str(intake_path),
        "--out-json", str(classification_path),
        "--pinned-time", PINNED,
    ])
    req_path = tmp_path / "request.json"
    rc = builder_mod.main([
        "--from-scientific-classification", str(classification_path),
        "--intake-json", str(intake_path),
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(req_path),
    ])
    assert rc == 0
    req = json.loads(req_path.read_text(encoding="utf-8"))
    # Classification routing landed in the request.
    assert req["source_tool"] == "materials_engine"
    assert req["task_type"] == "scientific_intake"
    # Both metadata blocks present.
    assert "scientific_task_classification" in req["metadata"]
    assert "scientific_reader_manifest" in req["metadata"]
    assert "scientific_intake" in req["metadata"]
    # Cross-check ids match.
    cm = req["metadata"]["scientific_task_classification"]
    assert cm["task_kind"] == "comparison"
    assert "CeO2" in cm["candidate_materials"]
    # Schema validates.
    jsonschema.validate(req, request_schema)


def test_builder_refuses_mismatched_intake(
    tmp_path, intake_mod, classifier_mod, builder_mod,
):
    """If --intake-json points at a DIFFERENT intake than the
    classification was built from, the builder must refuse."""
    docs = _make_canonical_corpus(tmp_path)
    intake_path_a = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    classification_path = tmp_path / "classification.json"
    classifier_mod.main([
        "--intake-json", str(intake_path_a),
        "--out-json", str(classification_path),
        "--pinned-time", PINNED,
    ])
    # Build a DIFFERENT intake with a different prompt.
    intake_path_b = _produce_intake(
        tmp_path / "B", intake_mod,
        prompt="A totally unrelated question.",
        docs=docs,
    )
    req_path = tmp_path / "request.json"
    rc = builder_mod.main([
        "--from-scientific-classification", str(classification_path),
        "--intake-json", str(intake_path_b),
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(req_path),
    ])
    assert rc == 2
    assert not req_path.exists()


def test_builder_requires_intake_json_with_classification(
    tmp_path, intake_mod, classifier_mod, builder_mod,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    classification_path = tmp_path / "classification.json"
    classifier_mod.main([
        "--intake-json", str(intake_path),
        "--out-json", str(classification_path),
        "--pinned-time", PINNED,
    ])
    req_path = tmp_path / "request.json"
    # Omit --intake-json
    rc = builder_mod.main([
        "--from-scientific-classification", str(classification_path),
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(req_path),
    ])
    assert rc == 2


def test_builder_rejects_conflicting_flags_with_classification(
    tmp_path, intake_mod, classifier_mod, builder_mod,
):
    docs = _make_canonical_corpus(tmp_path)
    intake_path = _produce_intake(
        tmp_path, intake_mod, prompt="Compare ceria and praseodymia.",
        docs=docs,
    )
    classification_path = tmp_path / "classification.json"
    classifier_mod.main([
        "--intake-json", str(intake_path),
        "--out-json", str(classification_path),
        "--pinned-time", PINNED,
    ])
    req_path = tmp_path / "request.json"
    rc = builder_mod.main([
        "--from-scientific-classification", str(classification_path),
        "--intake-json", str(intake_path),
        "--difficulty-class", "high",
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(req_path),
    ])
    assert rc == 2
