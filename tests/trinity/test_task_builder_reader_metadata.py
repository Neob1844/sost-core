"""Trinity Task Builder Reader Metadata v0.1 (Sprint 5.30) tests.

Covers the new scientific_reader_manifest block carried from a
Sprint 5.29 intake into a Useful Compute request via
useful_compute_task_builder.py --from-scientific-intake.

What the manifest IS:
  - documents_count + combined_context_sha256 mirrored from intake
  - reader_kind_counts + reader_status_counts roll-ups
  - per-document: path_basename, sha256, reader_kind, reader_status,
    extracted_text_sha256, structured_summary, per-doc warnings
  - intake_warnings carried over to top-level for visibility

What the manifest IS NOT (privacy + size invariants):
  - no extracted_text (only its sha256)
  - no extracted_text_preview, no text_preview
  - no absolute paths
  - no document bodies

Cross-pipeline assertions:
  - combined_context_sha256 in request == in intake
  - extracted_text_sha256 changes ⇒ input_bundle_sha256 changes ⇒
    worker compute_output_sha256 changes (the existing Sprint 5.29
    chain — verified here at the request layer)
  - existing pipeline e2e + operator_loop + task_queue continue to
    accept the augmented request
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
        "scientific_prompt_intake_rm",
        SCRIPTS_DIR / "scientific_prompt_intake.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "useful_compute_task_builder_rm",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def worker_mod():
    return _load(
        "useful_compute_worker_rm",
        SCRIPTS_DIR / "useful_compute_worker.py",
    )


@pytest.fixture(scope="module")
def request_schema():
    with open(REQUEST_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _make_documents(tmp_path):
    """A mixed-format reader set covering text / md / csv / tex /
    pdf-missing-dep so the manifest exercises 4 reader_kinds and
    2 reader_statuses (ok + unsupported_missing_dependency)."""
    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    txt = tmp_path / "sample.txt"
    txt.write_text("ceria oxygen storage notes\n", encoding="utf-8")
    md = tmp_path / "sample.md"
    md.write_text(
        "# Oxygen Storage\n\nCompare ceria and praseodymia.\n",
        encoding="utf-8",
    )
    csv = tmp_path / "sample.csv"
    csv.write_text(
        "compound,oxygen_storage_mmol_g\nCeO2,0.42\nPrOx,0.58\n",
        encoding="utf-8",
    )
    tex = tmp_path / "sample.tex"
    tex.write_text(
        "\\section{Methods}\nWe compare \\textbf{ceria}.\n",
        encoding="utf-8",
    )
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 minimal stub\n%%EOF\n")
    return [txt, md, csv, tex, pdf]


def _produce_intake(tmp_path, intake_mod, *, docs, prompt="p"):
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


def _build_request(tmp_path, builder_mod, intake_path):
    out = tmp_path / "request.json"
    rc = builder_mod.main([
        "--from-scientific-intake", str(intake_path),
        "--intake-task-kind", "comparison",
        "--intake-output-schema", "trinity-useful-compute-result/v0.4",
        "--difficulty-class", "low",
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(out),
    ])
    assert rc == 0
    return json.loads(out.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Manifest is present and well-formed
# ---------------------------------------------------------------------------


def test_request_contains_scientific_reader_manifest(
    tmp_path, intake_mod, builder_mod,
):
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    req = _build_request(tmp_path, builder_mod, intake_path)
    md = req["metadata"]
    assert "scientific_reader_manifest" in md
    rm = md["scientific_reader_manifest"]
    assert rm["documents_count"] == 5
    assert len(rm["combined_context_sha256"]) == 64
    assert len(rm["documents"]) == 5


def test_reader_kind_counts_match_documents(
    tmp_path, intake_mod, builder_mod,
):
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    req = _build_request(tmp_path, builder_mod, intake_path)
    rm = req["metadata"]["scientific_reader_manifest"]
    # 5 documents: 2 text (.txt + .md), 1 csv, 1 latex, 1 pdf
    assert rm["reader_kind_counts"] == {
        "csv": 1, "latex": 1, "pdf": 1, "text": 2,
    }


def test_reader_status_counts_reflect_pdf_missing_dep(
    tmp_path, intake_mod, builder_mod,
):
    """On hosts without pypdf / PyPDF2 the PDF reader records
    unsupported_missing_dependency. The manifest must roll that
    up so an operator can see the gap without opening per-doc
    JSONs."""
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    req = _build_request(tmp_path, builder_mod, intake_path)
    rm = req["metadata"]["scientific_reader_manifest"]
    # On this host pypdf is not installed, so 4 ok + 1
    # unsupported_missing_dependency.
    assert rm["reader_status_counts"].get("ok") == 4
    assert rm["reader_status_counts"].get(
        "unsupported_missing_dependency"
    ) == 1


def test_manifest_per_doc_has_required_fields(
    tmp_path, intake_mod, builder_mod,
):
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    req = _build_request(tmp_path, builder_mod, intake_path)
    rm = req["metadata"]["scientific_reader_manifest"]
    required = {
        "path_basename", "sha256", "reader_kind", "reader_status",
        "extracted_text_sha256", "structured_summary", "warnings",
    }
    for d in rm["documents"]:
        assert required <= set(d.keys()), (
            "doc missing fields: " + str(required - set(d.keys()))
        )
        assert len(d["sha256"]) == 64
        assert len(d["extracted_text_sha256"]) == 64
        assert d["reader_kind"] in (
            "text", "json", "pdf", "latex", "csv", "unsupported"
        )
        assert d["reader_status"] in (
            "ok",
            "unsupported_extension",
            "unsupported_missing_dependency",
            "parse_error",
        )


def test_manifest_carries_intake_warnings(
    tmp_path, intake_mod, builder_mod,
):
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    req = _build_request(tmp_path, builder_mod, intake_path)
    rm = req["metadata"]["scientific_reader_manifest"]
    # The PDF missing-dep warning bubbles up at the intake top
    # level, and the bridge carries it across.
    assert any(
        "sample.pdf" in w and "no PDF backend" in w
        for w in rm["intake_warnings"]
    )


# ---------------------------------------------------------------------------
# Privacy invariants
# ---------------------------------------------------------------------------


def test_request_does_not_contain_extracted_text_or_preview(
    tmp_path, intake_mod, builder_mod,
):
    """We poison a doc with a sentinel string and assert that
    neither the body NOR a preview of it ever reaches the
    request. Only the sha256 of the extracted text does."""
    docs = _make_documents(tmp_path)
    extra = tmp_path / "secret.md"
    extra.write_text(
        "SCIENTIFIC-SENTINEL-DO-NOT-LEAK ceria notes",
        encoding="utf-8",
    )
    intake_path = _produce_intake(
        tmp_path, intake_mod, docs=docs + [extra],
    )
    req = _build_request(tmp_path, builder_mod, intake_path)
    raw = json.dumps(req)
    assert "SCIENTIFIC-SENTINEL-DO-NOT-LEAK" not in raw
    assert "text_preview" not in raw
    assert "extracted_text_preview" not in raw
    # The basename IS present (deliberately).
    assert "secret.md" in raw
    # The extracted-text sha256 IS present (deliberately).
    sentinel_sha = hashlib.sha256(
        "SCIENTIFIC-SENTINEL-DO-NOT-LEAK ceria notes".encode("utf-8")
    ).hexdigest()
    assert sentinel_sha in raw


def test_request_does_not_contain_absolute_paths(
    tmp_path, intake_mod, builder_mod,
):
    """Operator-private absolute paths must never reach the
    request. Only basenames are persisted."""
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    req = _build_request(tmp_path, builder_mod, intake_path)
    raw = json.dumps(req)
    for d in docs:
        assert str(d) not in raw, "absolute path leaked: " + str(d)
        assert d.name in raw, "basename missing: " + d.name


# ---------------------------------------------------------------------------
# Reader-sensitivity flows through to compute_output (Sprint 5.29 chain)
# ---------------------------------------------------------------------------


def test_combined_context_sha_in_request_matches_intake(
    tmp_path, intake_mod, builder_mod,
):
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    req = _build_request(tmp_path, builder_mod, intake_path)
    assert (
        req["metadata"]["scientific_intake"]["combined_context_sha256"]
        == intake["combined_context_sha256"]
    )
    assert (
        req["metadata"]["scientific_reader_manifest"]["combined_context_sha256"]
        == intake["combined_context_sha256"]
    )
    # The request's input_bundle_sha256 IS the combined hash —
    # that is how Sprint 5.29's reader-sensitivity reaches the
    # worker.
    assert req["input_bundle_sha256"] == intake["combined_context_sha256"]


def test_worker_compute_output_changes_when_extracted_text_changes(
    tmp_path, intake_mod, builder_mod, worker_mod,
):
    """Mutate a document so its extracted_text_sha256 changes.
    Run intake → builder → worker on both runs. The worker's
    compute_output_sha256 MUST differ between runs.

    The chain is: extracted_text_sha256 (Sprint 5.29) →
    combined_context_sha256 (Sprint 5.29 mix-in) →
    input_bundle_sha256 (Sprint 5.21 bridge) →
    compute_output_sha256 (Sprint 5.12+ worker, seed depends on
    input_sha)."""
    # Run A
    a_docs = _make_documents(tmp_path / "A")
    a_intake = _produce_intake(tmp_path / "A", intake_mod, docs=a_docs)
    a_req = _build_request(tmp_path / "A", builder_mod, a_intake)
    rc_a, result_a = _run_worker(
        worker_mod, tmp_path / "A_work", a_req,
    )
    assert rc_a == 0
    sha_a = result_a["compute_output_sha256"]

    # Run B with a mutated .md
    b_docs = _make_documents(tmp_path / "B")
    b_md = next(d for d in b_docs if d.suffix == ".md")
    b_md.write_text(
        "# Changed body content\n\nDifferent prose.\n",
        encoding="utf-8",
    )
    b_intake = _produce_intake(tmp_path / "B", intake_mod, docs=b_docs)
    b_req = _build_request(tmp_path / "B", builder_mod, b_intake)
    rc_b, result_b = _run_worker(
        worker_mod, tmp_path / "B_work", b_req,
    )
    assert rc_b == 0
    sha_b = result_b["compute_output_sha256"]

    assert sha_a != sha_b, (
        "compute_output_sha256 unchanged after extracted_text "
        "change — Sprint 5.29 chain is broken"
    )


def _run_worker(worker_mod, work_dir, req):
    """Invoke the worker on a request dict by writing it to disk
    and calling worker_mod.main."""
    work_dir.mkdir(parents=True, exist_ok=True)
    req_path = work_dir / "request.json"
    req_path.write_text(json.dumps(req), encoding="utf-8")
    out_dir = work_dir / "out"
    rc = worker_mod.main([
        "--mode", "local-dry-run",
        "--request", str(req_path),
        "--out-dir", str(out_dir),
        "--worker-id", "worker-A",
        "--pinned-time", PINNED,
    ])
    if rc != 0:
        return rc, None
    files = list(out_dir.glob(
        "TRINITY_USEFUL_COMPUTE_RESULT_*.json"
    ))
    assert len(files) == 1
    return rc, json.loads(files[0].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Schema validation: new manifest and old (no manifest) both validate
# ---------------------------------------------------------------------------


def test_new_request_validates_against_schema(
    tmp_path, intake_mod, builder_mod, request_schema,
):
    docs = _make_documents(tmp_path)
    intake_path = _produce_intake(tmp_path, intake_mod, docs=docs)
    req = _build_request(tmp_path, builder_mod, intake_path)
    jsonschema.validate(req, request_schema)


def test_legacy_request_without_manifest_still_validates(request_schema):
    """A request emitted by a pre-Sprint-5.30 builder has no
    scientific_reader_manifest. The schema must still validate
    it (manifest is OPTIONAL in metadata, not required)."""
    legacy = {
        "schema": "trinity-useful-compute-request/v0.1",
        "request_id": "uc-0123456789abcdef",
        "source_tool": "trinity_scientific_prompt_intake",
        "candidate_id": "candidate-legacy",
        "task_type": "scientific_intake",
        "input_bundle_sha256": "a" * 64,
        "expected_output_schema": "trinity-useful-compute-result/v0.4",
        "validation_method": "deterministic_hash_check",
        "estimated_compute_cost": {"seconds": 60, "tier": "low"},
        "max_reward_stocks": 100000,
        "deadline": "2026-06-30T00:00:00+00:00",
        "manual_review_required": False,
        "public_description": "legacy pre-5.30 request fixture for schema test",
        "metadata": {
            "scientific_intake": {
                "intake_id": "spi-0123456789abcdef",
                "combined_context_sha256": "a" * 64,
                "prompt_sha256":          "b" * 64,
                "documents_count":        2,
                "intake_task_kind":       "benchmark",
                "intake_artifact_sha256": "c" * 64,
            }
        },
    }
    jsonschema.validate(legacy, request_schema)


# ---------------------------------------------------------------------------
# Builder helper unit tests
# ---------------------------------------------------------------------------


def test_per_doc_record_defaults_for_pre_5_29_intake(builder_mod):
    """A legacy intake (no reader_kind / extracted_text_sha256
    fields) gets default text / ok / empty-string-sha so the
    request schema still validates."""
    legacy_doc = {
        "path_basename": "old.md",
        "sha256": "a" * 64,
        "bytes": 42,
        "text_preview": "preview text",
    }
    rec = builder_mod._per_doc_reader_record(legacy_doc)
    assert rec["reader_kind"] == "text"
    assert rec["reader_status"] == "ok"
    # Empty-string sha256 fallback for legacy docs.
    assert rec["extracted_text_sha256"] == hashlib.sha256(b"").hexdigest()
    assert rec["structured_summary"] == {}
    assert rec["warnings"] == []


def test_per_doc_record_preserves_5_29_fields(builder_mod):
    new_doc = {
        "path_basename": "new.csv",
        "sha256": "a" * 64,
        "bytes": 100,
        "text_preview": "preview",
        "reader_kind": "csv",
        "reader_status": "ok",
        "extracted_text_sha256": "b" * 64,
        "extracted_text_preview": "extracted preview",
        "structured_summary": {"row_count": 3, "column_count": 2},
        "warnings": ["one warning"],
    }
    rec = builder_mod._per_doc_reader_record(new_doc)
    assert rec["reader_kind"] == "csv"
    assert rec["reader_status"] == "ok"
    assert rec["extracted_text_sha256"] == "b" * 64
    assert rec["structured_summary"] == {"row_count": 3, "column_count": 2}
    assert rec["warnings"] == ["one warning"]
    # extracted_text_preview must NOT propagate into the request
    # record (privacy contract).
    assert "extracted_text_preview" not in rec
