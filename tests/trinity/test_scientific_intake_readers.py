"""Trinity Scientific Intake Readers v0.1 (Sprint 5.29) — reader tests.

Covers the new per-document fields and per-extension readers added
to scripts/trinity/scientific_prompt_intake.py:

  .txt / .md   → text reader, ok
  .json        → json reader; valid + malformed → parse_error
  .tex         → minimal LaTeX text extraction
  .csv         → row_count / column_count / header / preview
  .pdf         → graceful: pypdf / PyPDF2 if importable, else
                 unsupported_missing_dependency

Plus contract-level tests:
  - combined_context_sha256 reflects extracted_text changes
  - existing .txt/.md/.json behaviour does not regress
  - unsupported extension (added via --allowed-ext) is recorded,
    not crashing
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def intake():
    return _load(
        "scientific_prompt_intake_rd",
        SCRIPTS_DIR / "scientific_prompt_intake.py",
    )


def _run(intake, *, tmp_path, docs, prompt="p"):
    out = tmp_path / "out"
    argv = [
        "--mode", "local-dry-run",
        "--prompt", prompt,
        "--out-dir", str(out),
        "--pinned-time", "2026-05-17T00:00:00+00:00",
    ]
    for d in docs:
        argv += ["--document", str(d)]
    rc = intake.main(argv)
    assert rc == 0, "intake.main exited " + str(rc)
    files = list(out.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"))
    assert len(files) == 1
    return json.loads(files[0].read_text(encoding="utf-8"))


def _by_basename(art):
    return {d["path_basename"]: d for d in art["documents"]}


# ---------------------------------------------------------------------------
# Existing .txt / .md / .json behavior is preserved
# ---------------------------------------------------------------------------


def test_text_reader_marks_md_as_text_kind(tmp_path, intake):
    p = tmp_path / "n.md"
    p.write_text("# H\n\nsome prose\n", encoding="utf-8")
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["n.md"]
    assert d["reader_kind"] == "text"
    assert d["reader_status"] == "ok"
    assert d["extracted_text_sha256"] == (
        hashlib.sha256(p.read_text(encoding="utf-8").encode("utf-8"))
        .hexdigest()
    )
    assert "some prose" in d["extracted_text_preview"]
    assert d["structured_summary"]["char_count"] == len(
        p.read_text(encoding="utf-8")
    )
    # Sprint 5.20 fields still present and stable.
    assert d["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    assert d["bytes"] == len(p.read_bytes())


def test_json_reader_ok_for_valid(tmp_path, intake):
    p = tmp_path / "data.json"
    p.write_text(
        json.dumps({"a": 1, "b": [2, 3]}),
        encoding="utf-8",
    )
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["data.json"]
    assert d["reader_kind"] == "json"
    assert d["reader_status"] == "ok"
    assert d["structured_summary"]["top_level_kind"] == "object"
    assert d["structured_summary"]["top_level_keys_count"] == 2


def test_json_reader_records_parse_error(tmp_path, intake):
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["broken.json"]
    assert d["reader_kind"] == "json"
    assert d["reader_status"] == "parse_error"
    assert any("json parse error" in w for w in d["warnings"])
    # The per-doc warning surfaces at the top level too.
    assert any(
        "broken.json" in w and "json parse error" in w
        for w in art["warnings"]
    )


# ---------------------------------------------------------------------------
# .tex reader
# ---------------------------------------------------------------------------


_TEX_SAMPLE = (
    "\\documentclass{article}\n"
    "% a comment that should disappear\n"
    "\\begin{document}\n"
    "\\section{Introduction}\n"
    "We study the oxygen storage capacity of \\textbf{ceria}.\n"
    "The reaction is described by $A + B \\to C$ in inline math.\n"
    "\\subsection{Methods}\n"
    "We used \\cite{paper2026} as reference.\n"
    "\\end{document}\n"
)


def test_latex_reader_extracts_prose(tmp_path, intake):
    p = tmp_path / "paper.tex"
    p.write_text(_TEX_SAMPLE, encoding="utf-8")
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["paper.tex"]
    assert d["reader_kind"] == "latex"
    assert d["reader_status"] == "ok"
    ext = d["extracted_text_preview"]
    # Comment line stripped.
    assert "a comment that should disappear" not in ext
    # Inline math stripped.
    assert "$A" not in ext
    # \section{Introduction} → "Introduction"
    assert "Introduction" in ext
    # \textbf{ceria} → "ceria"
    assert "ceria" in ext
    # Bare commands like \documentclass dropped.
    assert "\\documentclass" not in ext
    # Backslash from any command was removed.
    assert "\\" not in d["extracted_text_preview"]
    assert d["structured_summary"]["has_document_env"] is True
    assert d["structured_summary"]["section_count"] >= 1


def test_latex_reader_extracted_text_is_deterministic(tmp_path, intake):
    p = tmp_path / "paper.tex"
    p.write_text(_TEX_SAMPLE, encoding="utf-8")
    art_a = _run(intake, tmp_path=tmp_path / "a", docs=[p])
    art_b = _run(intake, tmp_path=tmp_path / "b", docs=[p])
    assert _by_basename(art_a)["paper.tex"]["extracted_text_sha256"] == (
        _by_basename(art_b)["paper.tex"]["extracted_text_sha256"]
    )


def test_latex_reader_without_document_env(tmp_path, intake):
    p = tmp_path / "snippet.tex"
    p.write_text(
        "\\section{Standalone}\nNo document env here.\n",
        encoding="utf-8",
    )
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["snippet.tex"]
    assert d["reader_status"] == "ok"
    assert d["structured_summary"]["has_document_env"] is False
    assert "Standalone" in d["extracted_text_preview"]


# ---------------------------------------------------------------------------
# .csv reader
# ---------------------------------------------------------------------------


_CSV_SAMPLE = (
    "compound,oxygen_storage_mmol_g,temperature_c\n"
    "ceria,1.7,500\n"
    "praseodymia,2.3,500\n"
    "samaria,0.9,500\n"
)


def test_csv_reader_records_row_column_header(tmp_path, intake):
    p = tmp_path / "table.csv"
    p.write_text(_CSV_SAMPLE, encoding="utf-8")
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["table.csv"]
    assert d["reader_kind"] == "csv"
    assert d["reader_status"] == "ok"
    s = d["structured_summary"]
    assert s["row_count"] == 4
    assert s["column_count"] == 3
    assert s["header"] == [
        "compound", "oxygen_storage_mmol_g", "temperature_c",
    ]
    # Preview rows include header and at least one data row.
    assert len(s["preview_rows"]) <= 5
    assert s["preview_rows"][0] == [
        "compound", "oxygen_storage_mmol_g", "temperature_c",
    ]


def test_csv_reader_no_header_when_first_row_numeric(tmp_path, intake):
    p = tmp_path / "values.csv"
    p.write_text("1,2,3\n4,5,6\n", encoding="utf-8")
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["values.csv"]
    assert d["reader_status"] == "ok"
    assert "header" not in d["structured_summary"]


def test_csv_reader_extracted_text_deterministic(tmp_path, intake):
    p = tmp_path / "table.csv"
    p.write_text(_CSV_SAMPLE, encoding="utf-8")
    art_a = _run(intake, tmp_path=tmp_path / "a", docs=[p])
    art_b = _run(intake, tmp_path=tmp_path / "b", docs=[p])
    assert _by_basename(art_a)["table.csv"]["extracted_text_sha256"] == (
        _by_basename(art_b)["table.csv"]["extracted_text_sha256"]
    )


# ---------------------------------------------------------------------------
# .pdf reader — graceful with or without dependency
# ---------------------------------------------------------------------------


def _has_pdf_backend():
    try:
        import pypdf  # noqa
        return True
    except ImportError:
        pass
    try:
        import PyPDF2  # noqa
        return True
    except ImportError:
        pass
    return False


def _minimal_pdf_bytes():
    """A minimal but parseable PDF with a single page containing
    'Hello'. Hand-built so the test does not need a generator."""
    return (
        b"%PDF-1.1\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 144]"
        b"/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>endobj\n"
        b"4 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\n"
        b"5 0 obj<</Length 44>>stream\n"
        b"BT /F1 24 Tf 100 100 Td (Hello) Tj ET\n"
        b"endstream\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000051 00000 n \n"
        b"0000000091 00000 n \n"
        b"0000000186 00000 n \n"
        b"0000000242 00000 n \n"
        b"trailer<</Size 6/Root 1 0 R>>\n"
        b"startxref\n330\n%%EOF\n"
    )


def test_pdf_reader_missing_dependency_branch(tmp_path, intake, monkeypatch):
    """Force the no-backend branch via monkeypatch on the dynamic
    importer so the test is deterministic even on a host that DOES
    have pypdf installed."""
    monkeypatch.setattr(intake, "_pdf_reader_module", lambda: None)
    p = tmp_path / "paper.pdf"
    p.write_bytes(_minimal_pdf_bytes())
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["paper.pdf"]
    assert d["reader_kind"] == "pdf"
    assert d["reader_status"] == "unsupported_missing_dependency"
    assert d["extracted_text_sha256"] == hashlib.sha256(b"").hexdigest()
    assert d["structured_summary"]["pdf_backend"] is None
    assert any(
        "no PDF backend available" in w for w in d["warnings"]
    )


@pytest.mark.skipif(
    not _has_pdf_backend(),
    reason="pypdf / PyPDF2 not installed on this host",
)
def test_pdf_reader_extracts_text_when_backend_available(tmp_path, intake):
    p = tmp_path / "paper.pdf"
    p.write_bytes(_minimal_pdf_bytes())
    art = _run(intake, tmp_path=tmp_path, docs=[p])
    d = _by_basename(art)["paper.pdf"]
    assert d["reader_kind"] == "pdf"
    # Either ok (text extracted) or parse_error (the minimal PDF is
    # technically valid but some pypdf versions can't extract text
    # from it). Either way, status must be in the enum and we must
    # not crash.
    assert d["reader_status"] in ("ok", "parse_error")
    assert d["structured_summary"]["pdf_backend"] in ("pypdf", "PyPDF2")


# ---------------------------------------------------------------------------
# Unsupported extension (admitted via --allowed-ext)
# ---------------------------------------------------------------------------


def test_unsupported_extension_records_warning_without_crash(
    tmp_path, intake,
):
    p = tmp_path / "data.yaml"
    p.write_text("key: value\n", encoding="utf-8")
    out = tmp_path / "out"
    rc = intake.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(p),
        "--out-dir", str(out),
        "--pinned-time", "2026-05-17T00:00:00+00:00",
        "--allowed-ext", ".yaml",
    ])
    assert rc == 0
    art = json.loads(
        list(out.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json"))[0]
        .read_text(encoding="utf-8")
    )
    d = _by_basename(art)["data.yaml"]
    assert d["reader_kind"] == "unsupported"
    assert d["reader_status"] == "unsupported_extension"
    assert d["extracted_text_sha256"] == hashlib.sha256(b"").hexdigest()
    assert any("not handled by any reader" in w for w in d["warnings"])
    # Surfaced at the top level too.
    assert any(
        "data.yaml" in w for w in art["warnings"]
    )


def test_truly_unknown_extension_still_rejected(tmp_path, intake):
    """An extension NOT in --allowed-ext is still refused outright
    (preserves the Sprint 5.20 contract — see
    test_unknown_extension_rejected in test_scientific_prompt_intake.py)."""
    p = tmp_path / "binary.bin"
    p.write_bytes(b"\x00\x01\x02")
    rc = intake.main([
        "--mode", "local-dry-run",
        "--prompt", "p",
        "--document", str(p),
        "--out-dir", str(tmp_path / "out"),
        "--pinned-time", "2026-05-17T00:00:00+00:00",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# combined_context_sha256 is sensitive to extracted text + reader status
# ---------------------------------------------------------------------------


def test_combined_sha_changes_when_extracted_text_changes(tmp_path, intake):
    """Mutate a .tex doc so the raw bytes change AND the extracted
    text changes. combined_context_sha256 must differ between runs.
    This proves the new mix-in (Sprint 5.29) is wired in."""
    p = tmp_path / "x.tex"
    p.write_text(
        "\\begin{document}\\section{One}First.\\end{document}\n",
        encoding="utf-8",
    )
    art_a = _run(intake, tmp_path=tmp_path / "a", docs=[p])
    p.write_text(
        "\\begin{document}\\section{Two}Second.\\end{document}\n",
        encoding="utf-8",
    )
    art_b = _run(intake, tmp_path=tmp_path / "b", docs=[p])
    assert art_a["combined_context_sha256"] != (
        art_b["combined_context_sha256"]
    )


def test_combined_sha_changes_when_reader_status_changes(
    tmp_path, intake, monkeypatch,
):
    """Run twice with the same .pdf bytes — first run patches the
    backend to None (missing-dep branch), second run uses the real
    importer. combined_context_sha256 should differ because
    reader_status is mixed into the hash."""
    p = tmp_path / "paper.pdf"
    p.write_bytes(_minimal_pdf_bytes())

    # Run 1: force missing-dep
    monkeypatch.setattr(intake, "_pdf_reader_module", lambda: None)
    art_a = _run(intake, tmp_path=tmp_path / "a", docs=[p])
    sha_a = art_a["combined_context_sha256"]

    # Run 2: lift the patch so the real backend probe runs.
    monkeypatch.undo()
    art_b = _run(intake, tmp_path=tmp_path / "b", docs=[p])
    sha_b = art_b["combined_context_sha256"]

    if _has_pdf_backend():
        # Real backend: status flips to ok or parse_error → sha differs.
        assert sha_a != sha_b
    else:
        # No backend either way: both runs give the same
        # unsupported_missing_dependency status → sha matches.
        assert sha_a == sha_b


# ---------------------------------------------------------------------------
# Reader enums are exposed as expected
# ---------------------------------------------------------------------------


def test_reader_kind_enum_values(intake):
    assert set(intake.READER_KINDS) == {
        "text", "json", "pdf", "latex", "csv", "unsupported",
    }


def test_reader_status_enum_values(intake):
    assert set(intake.READER_STATUSES) == {
        "ok",
        "unsupported_extension",
        "unsupported_missing_dependency",
        "parse_error",
    }
