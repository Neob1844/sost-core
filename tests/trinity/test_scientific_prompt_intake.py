"""Trinity scientific prompt intake — functional tests (Sprint 5.20)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "scientific_prompt_intake.schema.json"
)


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def intake_mod():
    return _load(
        "ucintake", SCRIPTS_DIR / "scientific_prompt_intake.py",
    )


def _write_doc(p: Path, content: str) -> Path:
    p.write_text(content, encoding="utf-8")
    return p


def _load_artifact(out_dir: Path) -> Dict[str, Any]:
    files = list(out_dir.glob(
        "TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"
    ))
    assert len(files) == 1, f"expected exactly 1 artifact, got {files}"
    return json.loads(files[0].read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_prompt_only_produces_valid_artifact(tmp_path, intake_mod):
    out_dir = tmp_path / "out"
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "What is the most reactive lanthanide oxide?",
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    assert rc == 0
    art = _load_artifact(out_dir)
    assert art["schema"] == \
        "trinity-scientific-prompt-intake/v0.1"
    assert re.match(r"^spi-[0-9a-f]{16}$", art["intake_id"])
    assert art["mode"] == "local-dry-run"
    assert art["documents_count"] == 0
    assert art["documents"] == []
    assert len(art["prompt_sha256"]) == 64
    assert "lanthanide" in art["prompt_preview"]


def test_prompt_plus_two_docs_hashes_correctly(
    tmp_path, intake_mod,
):
    a = _write_doc(
        tmp_path / "note-a.md",
        "## Note A\n\nCeria has unusual oxygen storage capacity.",
    )
    b = _write_doc(
        tmp_path / "note-b.txt",
        "Praseodymium oxide forms several non-stoichiometric phases.",
    )
    out_dir = tmp_path / "out"
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "Compare ceria and praseodymia.",
        "--document", str(a),
        "--document", str(b),
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    assert rc == 0
    art = _load_artifact(out_dir)
    assert art["documents_count"] == 2
    by_name = {d["path_basename"]: d for d in art["documents"]}
    assert set(by_name.keys()) == {"note-a.md", "note-b.txt"}
    # Each document sha256 must match the raw bytes on disk.
    for name, p in [("note-a.md", a), ("note-b.txt", b)]:
        expected = hashlib.sha256(p.read_bytes()).hexdigest()
        assert by_name[name]["sha256"] == expected
        assert by_name[name]["bytes"] == len(p.read_bytes())


def test_same_inputs_same_intake_id(tmp_path, intake_mod):
    """Determinism: same prompt + docs + pinned-time -> same id +
    byte-identical JSON."""
    a = _write_doc(tmp_path / "x.md", "deterministic content")
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    args = lambda od: [
        "--mode", "local-dry-run",
        "--prompt", "prompt-X",
        "--document", str(a),
        "--out-dir", str(od),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ]
    intake_mod.main(args(out_a))
    intake_mod.main(args(out_b))
    art_a = _load_artifact(out_a)
    art_b = _load_artifact(out_b)
    assert art_a["intake_id"] == art_b["intake_id"]
    # Byte-identical: the writer uses canonical_dumps.
    fa = list(out_a.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"))[0]
    fb = list(out_b.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"))[0]
    assert fa.read_bytes() == fb.read_bytes()


def test_document_change_changes_combined_context_sha(
    tmp_path, intake_mod,
):
    a = _write_doc(tmp_path / "x.md", "original")
    out_a = tmp_path / "out_a"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(a),
        "--out-dir", str(out_a),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    sha_a = _load_artifact(out_a)["combined_context_sha256"]

    # Mutate the doc.
    a.write_text("modified", encoding="utf-8")
    out_b = tmp_path / "out_b"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(a),
        "--out-dir", str(out_b),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    sha_b = _load_artifact(out_b)["combined_context_sha256"]
    assert sha_a != sha_b


def test_document_order_independence(tmp_path, intake_mod):
    """Two CLI invocations that pass the same documents in
    different order must produce the same artifact (documents are
    sorted by sha256 internally)."""
    a = _write_doc(tmp_path / "a.md", "aaa")
    b = _write_doc(tmp_path / "b.md", "bbb")
    out_1 = tmp_path / "out_1"
    out_2 = tmp_path / "out_2"
    intake_mod.main([
        "--mode", "local-dry-run", "--prompt", "p",
        "--document", str(a), "--document", str(b),
        "--out-dir", str(out_1),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    intake_mod.main([
        "--mode", "local-dry-run", "--prompt", "p",
        "--document", str(b), "--document", str(a),
        "--out-dir", str(out_2),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    a1 = _load_artifact(out_1)
    a2 = _load_artifact(out_2)
    assert a1["intake_id"] == a2["intake_id"]
    assert a1["documents"] == a2["documents"]


# ---------------------------------------------------------------------------
# Redaction / privacy
# ---------------------------------------------------------------------------


def test_no_absolute_path_in_artifact(tmp_path, intake_mod):
    nested = tmp_path / "deeply" / "nested" / "folder"
    nested.mkdir(parents=True)
    doc = _write_doc(
        nested / "secret-location.md", "content"
    )
    out_dir = tmp_path / "out"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(doc),
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    art_path = list(out_dir.glob(
        "TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"
    ))[0]
    raw = art_path.read_text(encoding="utf-8")
    # The artifact must NOT contain the absolute path leading
    # to the document — only the basename.
    assert str(nested) not in raw
    assert "secret-location.md" in raw
    art = json.loads(raw)
    assert art["documents"][0]["path_basename"] == \
        "secret-location.md"


def test_preview_is_bounded(tmp_path, intake_mod):
    huge = "x" * 4000
    doc = _write_doc(tmp_path / "big.md", huge)
    out_dir = tmp_path / "out"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(doc),
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
        "--preview-chars", "100",
    ])
    art = _load_artifact(out_dir)
    assert len(art["documents"][0]["text_preview"]) == 100


# ---------------------------------------------------------------------------
# Rejection paths
# ---------------------------------------------------------------------------


def test_unknown_extension_rejected(tmp_path, intake_mod):
    bad = _write_doc(tmp_path / "binary.bin", "not allowed")
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(bad),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    assert rc == 2
    # No artifact should have been written.
    assert not (tmp_path / "out").exists() or \
        not list((tmp_path / "out").glob(
            "TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"
        ))


def test_oversize_document_rejected(tmp_path, intake_mod):
    big = _write_doc(tmp_path / "big.md", "x" * 5000)
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(big),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
        "--max-doc-bytes", "1000",
    ])
    assert rc == 2


def test_oversize_prompt_rejected(tmp_path, intake_mod):
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "x" * 5000,
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
        "--max-prompt-bytes", "1000",
    ])
    assert rc == 2


def test_too_many_documents_rejected(tmp_path, intake_mod):
    docs = []
    for i in range(5):
        docs.append(_write_doc(tmp_path / f"d{i}.md", str(i)))
    argv = [
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
        "--max-docs", "3",
    ]
    for d in docs:
        argv += ["--document", str(d)]
    rc = intake_mod.main(argv)
    assert rc == 2


def test_missing_document_rejected(tmp_path, intake_mod):
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(tmp_path / "does-not-exist.md"),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    assert rc == 2


@pytest.mark.parametrize("flag", [
    "--broadcast", "--send", "--payout-now", "--auto-pay",
    "--sign-now", "--export-private-key", "--wallet",
    "--llm-call", "--http-call", "--upload",
])
def test_pre_argparse_flag_rejected(tmp_path, intake_mod, flag):
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--out-dir", str(tmp_path),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
        flag,
    ])
    assert rc == 2


def test_prompt_and_prompt_file_mutually_exclusive(
    tmp_path, intake_mod,
):
    pf = _write_doc(tmp_path / "p.txt", "from-file")
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "from-cli",
        "--prompt-file", str(pf),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    assert rc == 2


def test_prompt_file_path(tmp_path, intake_mod):
    pf = _write_doc(tmp_path / "prompt.txt", "what is platinum?")
    out_dir = tmp_path / "out"
    rc = intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt-file", str(pf),
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    assert rc == 0
    art = _load_artifact(out_dir)
    assert "platinum" in art["prompt_preview"]


# ---------------------------------------------------------------------------
# Safety flags + schema validation
# ---------------------------------------------------------------------------


def test_safety_status_all_const_true(tmp_path, intake_mod):
    out_dir = tmp_path / "out"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    art = _load_artifact(out_dir)
    for k in (
        "local_only", "no_network", "no_llm_call",
        "no_wallet_access", "no_broadcast", "no_private_keys",
        "deterministic_output",
    ):
        assert art["safety_status"][k] is True


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


def test_artifact_validates_against_schema(tmp_path, intake_mod):
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    doc = _write_doc(tmp_path / "x.md", "small content")
    out_dir = tmp_path / "out"
    intake_mod.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(doc),
        "--out-dir", str(out_dir),
        "--pinned-time", "2026-05-13T00:00:00+00:00",
    ])
    art = _load_artifact(out_dir)
    _validate(art, schema)
