"""Static safety surface for Sprint 5.29 reader extension.

The Sprint 5.20 intake script's static safety surface is already
covered by tests/trinity/test_scientific_prompt_intake_safety.py.
This file is a *delta* — it re-asserts the script stays off the
shell / network / wallet surface after the Sprint 5.29 readers
land, and locks the specific new shapes the readers introduce.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "scientific_prompt_intake.py"


# The Sprint 5.20 safety file already enforces no network, no
# wallet, no signing, no broadcast. Sprint 5.29 must keep that
# baseline AND additionally must not gain a subprocess (e.g., a
# shell-out to pdftotext) or a new os.system call.
# Sprint 5.29 only checks tokens that could have been introduced
# BY the reader extension itself. Wallet / signing / broadcast /
# network primitives are already enforced by the Sprint 5.20 file
# test_scientific_prompt_intake_safety.py — which uses a strip-
# aware grep that correctly ignores `no_private_keys` as a JSON
# field name. Duplicating that surface here with a plain substring
# match would false-positive on safety_status field names.
FORBIDDEN_NEW_IN_5_29 = (
    # A PDF backend MUST be loaded via dynamic import (see the
    # dedicated test below). No subprocess shell-out for pdftotext
    # / pdf2txt / catdoc / latex2html etc.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution — readers must NOT eval / exec
    # anything they extract.
    "eval(", "exec(",
)


def _read():
    return SCRIPT.read_text(encoding="utf-8")


def test_intake_script_exists():
    assert SCRIPT.is_file()


def test_intake_no_new_forbidden_tokens_after_5_29():
    src = _read()
    found = [t for t in FORBIDDEN_NEW_IN_5_29 if t in src]
    assert not found, (
        "Sprint 5.29 reader extension introduced a forbidden "
        "token into scientific_prompt_intake.py: " + repr(found)
    )


def test_reader_dispatch_table_present():
    """The reader registry MUST stay a simple ext → callable
    dispatch table so a reviewer can audit it at a glance."""
    src = _read()
    assert "_READER_BY_EXT = {" in src
    for ext in ('".txt"', '".md"', '".json"', '".tex"', '".csv"', '".pdf"'):
        assert ext + ":" in src, (
            "_READER_BY_EXT is missing extension: " + ext
        )


def test_default_allowed_exts_includes_new_readers():
    src = _read()
    # The default tuple must include every extension we register.
    for ext in ('".txt"', '".md"', '".json"', '".tex"', '".csv"', '".pdf"'):
        assert ext in src


def test_pdf_reader_module_is_dynamic_import():
    """The PDF backend MUST be loaded via an import-inside-try so
    a host without pypdf / PyPDF2 still passes the import. A
    top-level `import pypdf` would crash the module at load time."""
    src = _read()
    assert "def _pdf_reader_module():" in src
    # Top-level imports must NOT include pypdf or PyPDF2.
    for tok in ("\nimport pypdf", "\nfrom pypdf",
                "\nimport PyPDF2", "\nfrom PyPDF2"):
        assert tok not in src, (
            "pypdf/PyPDF2 must be dynamically imported inside "
            "_pdf_reader_module(), not at module top level: "
            + tok
        )


def test_unsupported_branch_does_not_raise():
    """Belt-and-braces grep: the unsupported-extension branch
    builds a reader_status='unsupported_extension' string."""
    src = _read()
    assert '"unsupported_extension"' in src
    assert "def _read_unsupported(" in src
