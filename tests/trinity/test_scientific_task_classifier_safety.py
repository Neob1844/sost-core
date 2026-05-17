"""Static safety surface for scripts/trinity/scientific_task_classifier.py
(Sprint 5.31).

The classifier is local, deterministic, no-LLM, no-network. It
reads ONE JSON file (the intake artifact) and writes ONE JSON
file (the classification). It MUST NOT touch wallets, sign
anything, broadcast anything, shell out, open a socket, or
eval/exec any text it reads.

Cross-check at the bottom: Sprint 5.31 must not regress the
Sprint 5.29 intake's safety surface or the Sprint 5.30 task
builder's safety surface.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = (
    REPO_ROOT / "scripts" / "trinity"
    / "scientific_task_classifier.py"
)
INTAKE = REPO_ROOT / "scripts" / "trinity" / "scientific_prompt_intake.py"
BUILDER = (
    REPO_ROOT / "scripts" / "trinity"
    / "useful_compute_task_builder.py"
)


FORBIDDEN_TOKENS_CLASSIFIER = (
    # Wallet / signing / broadcast primitives.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # Shell / subprocess. The classifier reads ONE JSON file and
    # writes ONE JSON file. No subprocess. No shell.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution. The classifier must NEVER eval / exec
    # anything from the intake — that would be the most direct LLM-
    # smuggling vector.
    "eval(", "exec(",
    # Network primitives. The classifier is offline.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    # Mutating filesystem ops on inputs. The classifier may write
    # the OUTPUT file; it must not unlink/chmod/rename anything else.
    ".unlink(", ".rmdir(", "shutil.rmtree", "os.remove(",
    "os.unlink(", "os.chmod(", ".chmod(", "os.rename(",
    # No LLM client libraries.
    "anthropic", "openai", "langchain", "transformers",
    "llama_cpp",
)


# Sprint 5.29 intake safety baseline. The classifier must not have
# nudged anything into the intake either.
FORBIDDEN_NEW_IN_INTAKE = (
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    "eval(", "exec(",
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
)


# Sprint 5.30 task builder safety baseline.
FORBIDDEN_NEW_IN_BUILDER = (
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    "eval(", "exec(",
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def test_classifier_script_exists():
    assert CLASSIFIER.is_file()


def test_classifier_has_no_forbidden_tokens():
    src = _read(CLASSIFIER)
    found = [t for t in FORBIDDEN_TOKENS_CLASSIFIER if t in src]
    assert not found, (
        "scripts/trinity/scientific_task_classifier.py contains "
        "forbidden token(s): " + repr(found)
    )


def test_classifier_declares_v01_schema_constant():
    src = _read(CLASSIFIER)
    assert "trinity-scientific-task-classification/v0.1" in src


def test_classifier_does_not_import_sibling_modules():
    """The classifier reads JSON files only. It must NOT import
    the intake, the worker, the task_builder, the queue or the
    operator loop — coupling them tightly would defeat the
    one-file-in / one-file-out design."""
    src = _read(CLASSIFIER)
    for tok in (
        "import scientific_prompt_intake",
        "from scientific_prompt_intake",
        "import useful_compute_task_builder",
        "from useful_compute_task_builder",
        "import useful_compute_worker",
        "from useful_compute_worker",
        "import autonomy_governor",
        "import task_queue",
    ):
        assert tok not in src, (
            "classifier must not import sibling Trinity module: "
            + tok
        )


def test_classifier_caps_evidence_length():
    """A static check that the evidence-snippet cap is in the
    source as a named constant. If a future PR raises it past
    256, the schema's maxLength would still catch the runtime
    case, but this fires earlier at lint time."""
    src = _read(CLASSIFIER)
    assert "EVIDENCE_SNIPPET_MAX = 200" in src
    assert "EVIDENCE_MAX_ITEMS = 16" in src


def test_classifier_heuristic_tables_present():
    """Belt-and-tirantes: the three heuristic tables must remain
    named module-level constants so a reviewer can audit them
    quickly."""
    src = _read(CLASSIFIER)
    assert "_TASK_KEYWORDS" in src
    assert "_MATERIAL_PATTERNS" in src
    assert "_METRIC_PATTERNS" in src
    assert "_MATERIAL_REGEX" in src


def test_classifier_threat_refs_constant():
    src = _read(CLASSIFIER)
    assert 'THREAT_REFS = ("T01", "T04", "T09")' in src


def test_intake_unchanged_after_5_31():
    src = _read(INTAKE)
    found = [t for t in FORBIDDEN_NEW_IN_INTAKE if t in src]
    assert not found, (
        "Sprint 5.31 introduced a forbidden token into the "
        "intake: " + repr(found)
    )


def test_task_builder_unchanged_after_5_31():
    """Cross-check that Sprint 5.31's extensions to the task
    builder did not introduce a forbidden token there either."""
    src = _read(BUILDER)
    found = [t for t in FORBIDDEN_NEW_IN_BUILDER if t in src]
    assert not found, (
        "Sprint 5.31 introduced a forbidden token into the "
        "task builder: " + repr(found)
    )
