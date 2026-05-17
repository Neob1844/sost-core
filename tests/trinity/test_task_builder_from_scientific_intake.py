"""Trinity task builder × scientific intake bridge — Sprint 5.21."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_request.schema.json"
)


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "ucb_intake",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def intake_mod():
    return _load(
        "ucintake_for_bridge",
        SCRIPTS_DIR / "scientific_prompt_intake.py",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _produce_intake(
    tmp_path: Path, intake_mod, *, prompt: str = "What is ceria?",
    pinned_time: str = "2026-05-13T00:00:00+00:00",
    documents: List[Path] = None,
) -> Path:
    """Run the real Sprint 5.20 intake to produce a valid artifact."""
    out_dir = tmp_path / "intake_out"
    argv = [
        "--mode", "local-dry-run",
        "--prompt", prompt,
        "--out-dir", str(out_dir),
        "--pinned-time", pinned_time,
    ]
    for d in documents or []:
        argv += ["--document", str(d)]
    rc = intake_mod.main(argv)
    assert rc == 0
    files = list(
        out_dir.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json")
    )
    assert len(files) == 1
    return files[0]


def _write_doc(p: Path, content: str) -> Path:
    p.write_text(content, encoding="utf-8")
    return p


def _load_request(out: Path) -> Dict[str, Any]:
    return json.loads(out.read_text(encoding="utf-8"))


def _base_intake_argv(*, out: Path, intake_path: Path) -> List[str]:
    return [
        "--difficulty-class", "low",
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--out-json", str(out),
        "--from-scientific-intake", str(intake_path),
        "--intake-task-kind", "benchmark",
        "--intake-output-schema",
        "trinity-useful-compute-result/v0.4",
    ]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_intake_bridge_produces_valid_request(
    tmp_path, builder_mod, intake_mod,
):
    a = _write_doc(tmp_path / "note.md", "Ceria has OSC.")
    b = _write_doc(
        tmp_path / "ref.txt", "Praseodymia is non-stoichiometric.",
    )
    intake_path = _produce_intake(
        tmp_path, intake_mod, documents=[a, b],
    )
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    out = tmp_path / "req.json"
    rc = builder_mod.main(
        _base_intake_argv(out=out, intake_path=intake_path)
    )
    assert rc == 0
    req = _load_request(out)
    assert req["schema"] == "trinity-useful-compute-request/v0.1"
    assert req["source_tool"] == "trinity_scientific_prompt_intake"
    assert req["task_type"] == "scientific_intake"
    assert req["validation_method"] == "deterministic_hash_check"
    assert req["input_bundle_sha256"] == \
        intake["combined_context_sha256"]
    assert req["expected_output_schema"] == \
        "trinity-useful-compute-result/v0.4"
    assert re.match(r"^uc-[0-9a-f]{16}$", req["request_id"])
    assert "metadata" in req
    meta = req["metadata"]["scientific_intake"]
    assert meta["intake_id"] == intake["intake_id"]
    assert meta["combined_context_sha256"] == \
        intake["combined_context_sha256"]
    assert meta["prompt_sha256"] == intake["prompt_sha256"]
    assert meta["documents_count"] == intake["documents_count"]
    assert meta["intake_task_kind"] == "benchmark"
    # intake_artifact_sha256 is sha256 of the intake file bytes.
    expected_artifact_sha = hashlib.sha256(
        intake_path.read_bytes(),
    ).hexdigest()
    assert meta["intake_artifact_sha256"] == expected_artifact_sha


def test_input_bundle_sha256_matches_combined_context_sha256(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    out = tmp_path / "req.json"
    builder_mod.main(_base_intake_argv(
        out=out, intake_path=intake_path,
    ))
    req = _load_request(out)
    assert req["input_bundle_sha256"] == \
        intake["combined_context_sha256"]


def test_candidate_id_derived_when_omitted(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    out = tmp_path / "req.json"
    builder_mod.main(_base_intake_argv(
        out=out, intake_path=intake_path,
    ))
    req = _load_request(out)
    assert req["candidate_id"] == "candidate-" + intake["intake_id"]


def test_candidate_id_honoured_when_supplied(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    out = tmp_path / "req.json"
    argv = _base_intake_argv(out=out, intake_path=intake_path)
    argv += ["--candidate-id", "operator-pick-A"]
    builder_mod.main(argv)
    req = _load_request(out)
    assert req["candidate_id"] == "operator-pick-A"


def test_public_description_generated_from_intake(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(
        tmp_path, intake_mod,
        prompt="Explain the magnetic moment of europium oxide.",
    )
    intake = json.loads(intake_path.read_text(encoding="utf-8"))
    out = tmp_path / "req.json"
    builder_mod.main(_base_intake_argv(
        out=out, intake_path=intake_path,
    ))
    req = _load_request(out)
    desc = req["public_description"]
    # Contains intake_id and a snippet of the prompt.
    assert intake["intake_id"] in desc
    assert "europium" in desc.lower()
    # Schema cap: 512 chars.
    assert len(desc) <= 512


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_intake_same_request_id(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    out1 = tmp_path / "req1.json"
    out2 = tmp_path / "req2.json"
    builder_mod.main(_base_intake_argv(
        out=out1, intake_path=intake_path,
    ))
    builder_mod.main(_base_intake_argv(
        out=out2, intake_path=intake_path,
    ))
    r1 = _load_request(out1)
    r2 = _load_request(out2)
    assert r1["request_id"] == r2["request_id"]
    # Byte-identical when serialized.
    assert out1.read_bytes() == out2.read_bytes()


def test_different_intake_kind_changes_request_id(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    out1 = tmp_path / "req1.json"
    out2 = tmp_path / "req2.json"
    argv1 = _base_intake_argv(out=out1, intake_path=intake_path)
    argv2 = list(argv1)
    # Replace "benchmark" with "comparison".
    idx = argv2.index("--intake-task-kind")
    argv2[idx + 1] = "comparison"
    argv2[argv2.index(str(out1))] = str(out2)
    builder_mod.main(argv1)
    builder_mod.main(argv2)
    r1 = _load_request(out1)
    r2 = _load_request(out2)
    assert r1["request_id"] != r2["request_id"]


# ---------------------------------------------------------------------------
# Safety gates on the intake
# ---------------------------------------------------------------------------


def _mutate_intake(
    intake_path: Path, mutator,
) -> Path:
    """Load, mutate, rewrite the intake file in place."""
    obj = json.loads(intake_path.read_text(encoding="utf-8"))
    mutator(obj)
    intake_path.write_text(
        json.dumps(obj, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return intake_path


@pytest.mark.parametrize("flag_name", [
    "local_only", "no_network", "no_llm_call",
    "deterministic_output",
])
def test_intake_safety_flag_must_be_true(
    tmp_path, builder_mod, intake_mod, flag_name,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    _mutate_intake(
        intake_path,
        lambda o: o["safety_status"].__setitem__(flag_name, False),
    )
    out = tmp_path / "req.json"
    rc = builder_mod.main(
        _base_intake_argv(out=out, intake_path=intake_path),
    )
    assert rc == 2
    assert not out.exists()


def test_intake_wrong_schema_rejected(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    _mutate_intake(
        intake_path,
        lambda o: o.__setitem__("schema", "not-a-real-schema/v0"),
    )
    out = tmp_path / "req.json"
    rc = builder_mod.main(
        _base_intake_argv(out=out, intake_path=intake_path),
    )
    assert rc == 2


def test_intake_wrong_intake_id_pattern_rejected(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    _mutate_intake(
        intake_path,
        lambda o: o.__setitem__("intake_id", "not-spi-style"),
    )
    out = tmp_path / "req.json"
    rc = builder_mod.main(
        _base_intake_argv(out=out, intake_path=intake_path),
    )
    assert rc == 2


def test_intake_invalid_combined_context_sha_rejected(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    _mutate_intake(
        intake_path,
        lambda o: o.__setitem__(
            "combined_context_sha256", "not-hex",
        ),
    )
    out = tmp_path / "req.json"
    rc = builder_mod.main(
        _base_intake_argv(out=out, intake_path=intake_path),
    )
    assert rc == 2


def test_missing_intake_file_rejected(
    tmp_path, builder_mod,
):
    out = tmp_path / "req.json"
    rc = builder_mod.main(_base_intake_argv(
        out=out, intake_path=tmp_path / "does-not-exist.json",
    ))
    assert rc == 2


def test_intake_task_kind_required(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    rc = builder_mod.main([
        "--difficulty-class", "low",
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--out-json", str(tmp_path / "req.json"),
        "--from-scientific-intake", str(intake_path),
        "--intake-output-schema",
        "trinity-useful-compute-result/v0.4",
    ])
    assert rc == 2


def test_intake_output_schema_required(
    tmp_path, builder_mod, intake_mod,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    rc = builder_mod.main([
        "--difficulty-class", "low",
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--out-json", str(tmp_path / "req.json"),
        "--from-scientific-intake", str(intake_path),
        "--intake-task-kind", "benchmark",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Mutually-exclusive flag matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conflict_flag,conflict_value", [
    ("--source-tool", "materials_engine"),
    ("--input-bundle", "bundle.txt"),
    ("--expected-output-schema", "some-schema/v1"),
    ("--public-description",
     "operator-supplied description text that should be rejected"),
])
def test_intake_path_rejects_legacy_flags(
    tmp_path, builder_mod, intake_mod,
    conflict_flag, conflict_value,
):
    intake_path = _produce_intake(tmp_path, intake_mod)
    out = tmp_path / "req.json"
    argv = _base_intake_argv(out=out, intake_path=intake_path)
    argv += [conflict_flag, conflict_value]
    rc = builder_mod.main(argv)
    assert rc == 2
    assert not out.exists()


# ---------------------------------------------------------------------------
# No document content / no absolute paths in the request
# ---------------------------------------------------------------------------


def test_request_does_not_copy_document_content(
    tmp_path, builder_mod, intake_mod,
):
    """Document BODY must never leak into the request. The basename
    IS deliberately carried into the Sprint 5.30 reader manifest
    (it's a public identifier, not a secret), so this test only
    bans the body and the body-preview. See
    test_request_reader_manifest_only_contains_safe_fields below
    for the positive contract."""
    doc = _write_doc(
        tmp_path / "secret.md",
        "SECRET-MAGIC-STRING-DO-NOT-LEAK abc def 123",
    )
    intake_path = _produce_intake(
        tmp_path, intake_mod, documents=[doc],
    )
    out = tmp_path / "req.json"
    builder_mod.main(_base_intake_argv(
        out=out, intake_path=intake_path,
    ))
    raw = out.read_text(encoding="utf-8")
    # Document body must not leak into the request.
    assert "SECRET-MAGIC-STRING-DO-NOT-LEAK" not in raw
    # text_preview is the body-preview from the intake; that
    # must not leak either.
    assert "text_preview" not in raw
    # extracted_text_preview is the Sprint 5.29 reader preview;
    # also must not leak.
    assert "extracted_text_preview" not in raw


def test_request_does_not_leak_absolute_path(
    tmp_path, builder_mod, intake_mod,
):
    nested = tmp_path / "deeply" / "private" / "folder"
    nested.mkdir(parents=True)
    doc = _write_doc(nested / "n.md", "content")
    intake_path = _produce_intake(
        tmp_path, intake_mod, documents=[doc],
    )
    out = tmp_path / "req.json"
    builder_mod.main(_base_intake_argv(
        out=out, intake_path=intake_path,
    ))
    raw = out.read_text(encoding="utf-8")
    assert str(nested) not in raw


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _validate(obj, schema):
    if schema.get("type") == "object":
        assert isinstance(obj, dict)
        required = set(schema.get("required", []))
        missing = required - set(obj.keys())
        assert not missing, f"missing fields: {sorted(missing)}"
        if schema.get("additionalProperties") is False:
            allowed = set(schema["properties"].keys())
            extra = set(obj.keys()) - allowed
            assert not extra, f"extra fields: {sorted(extra)}"
        for k, sub in schema["properties"].items():
            if k in obj:
                _validate(obj[k], sub)
    elif schema.get("type") == "array":
        for item in obj:
            _validate(item, schema.get("items", {}))
    else:
        if "const" in schema:
            assert obj == schema["const"]
        if "enum" in schema:
            assert obj in schema["enum"]
        if "pattern" in schema:
            assert isinstance(obj, str)
            assert re.match(schema["pattern"], obj)


def test_intake_request_validates_against_schema(
    tmp_path, builder_mod, intake_mod,
):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    intake_path = _produce_intake(tmp_path, intake_mod)
    out = tmp_path / "req.json"
    builder_mod.main(_base_intake_argv(
        out=out, intake_path=intake_path,
    ))
    req = _load_request(out)
    _validate(req, schema)


def test_legacy_path_still_validates(tmp_path, builder_mod):
    """Sanity: the legacy --input-bundle path still works after
    the intake-bridge refactor."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    bundle = tmp_path / "b.bin"
    bundle.write_bytes(b"legacy-bundle-bytes")
    out = tmp_path / "req.json"
    rc = builder_mod.main([
        "--source-tool", "trinity_orchestrator",
        "--candidate-id", "legacy-candidate-001",
        "--input-bundle", str(bundle),
        "--expected-output-schema", "trinity-useful-compute-result/v0.4",
        "--difficulty-class", "low",
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--public-description",
        "Legacy path test for the task builder regression",
        "--out-json", str(out),
    ])
    assert rc == 0
    req = _load_request(out)
    assert req["source_tool"] == "trinity_orchestrator"
    assert req["task_type"] == "other"
    _validate(req, schema)
