"""Static safety surface for the Sprint 5.21 intake bridge in
scripts/trinity/useful_compute_task_builder.py.

The task builder gains a new code path
(--from-scientific-intake) that consumes a Sprint 5.20 intake
artifact. The bridge must remain free of network primitives, LLM
references, subprocess to sost-cli, wallet/signing/broadcast
tokens — every Trinity script invariant still applies.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "trinity"
    / "useful_compute_task_builder.py"
)


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '', src)
    src = re.sub(r"'''[\s\S]*?'''", '', src)
    src = re.sub(r'"[^"\n]*"', '""', src)
    src = re.sub(r"'[^'\n]*'", "''", src)
    src = re.sub(r"#[^\n]*", "", src)
    return src


def _read():
    return SCRIPT_PATH.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT_PATH.exists()


def test_no_subprocess_or_shell():
    src = _strip(_read())
    for tok in ("subprocess.run", "subprocess.Popen",
                "subprocess.call", "subprocess.check_call",
                "subprocess.check_output", "os.system",
                "os.popen"):
        assert tok not in src, (
            f"forbidden process primitive {tok!r}"
        )


def test_no_network_imports():
    src = _strip(_read())
    for name in (
        "requests", "urllib.request", "urllib3", "httpx",
        "aiohttp", "socket", "websockets", "ftplib",
    ):
        m = re.search(
            rf"^\s*(?:import|from)\s+{re.escape(name)}\b",
            src, re.MULTILINE,
        )
        assert m is None, (
            f"forbidden network import {name!r}"
        )


def test_no_llm_or_remote_api_tokens():
    src = _strip(_read()).lower()
    for tok in ("openai", "anthropic", "claude_api",
                "completion(", "chat.completions"):
        assert tok not in src, (
            f"forbidden LLM/api token {tok!r}"
        )


def test_no_sost_cli_or_send_tokens():
    src = _strip(_read())
    for tok in ("sost-cli", "sost_cli", "sendrawtransaction"):
        assert tok not in src, (
            f"forbidden token {tok!r}"
        )


def test_no_wallet_or_private_key_tokens():
    src = _strip(_read()).lower()
    for tok in ("private_key", "privkey", "seed_phrase",
                "mnemonic", "passphrase",
                "load_wallet", "open_wallet", "wallet_path"):
        assert tok not in src, (
            f"forbidden wallet token {tok!r}"
        )


def test_no_signing_tokens():
    src = _strip(_read())
    for tok in ("sign_tx", "sign_transaction", "wallet.sign",
                ".sign(", "ecdsa", "secp256k1"):
        assert tok not in src, (
            f"forbidden signing token {tok!r}"
        )


def test_no_dynamic_execution():
    stripped = _strip(_read())
    stripped_no_re = re.sub(r"re\.compile\(", "", stripped)
    for tok in ("eval(", "exec(", "compile("):
        assert tok not in stripped_no_re, (
            f"forbidden dynamic-execution primitive {tok!r}"
        )


def test_intake_schema_constant_present():
    """The bridge must literally reference the intake schema id so
    a refactor cannot silently widen the accepted intake versions."""
    raw = _read()
    assert "trinity-scientific-prompt-intake/v0.1" in raw


def test_required_intake_safety_flags_listed():
    """The bridge MUST refuse an intake whose safety_status drops
    any of these flags. The constant lives in the script source as
    a string-literal tuple; if a future refactor removes a flag the
    bridge would silently accept unsafe intakes."""
    raw = _read()
    for flag in (
        '"local_only"', '"no_network"',
        '"no_llm_call"', '"deterministic_output"',
    ):
        assert flag in raw, (
            f"required intake safety flag literal {flag} missing "
            "from script"
        )


def test_no_document_content_copied_into_request():
    """The bridge must NOT copy raw document content into the
    request. We check that the script does not have a literal
    `text_preview` propagated INTO the request — only into the
    intake summary. The simplest invariant: the metadata block we
    emit lists only known identifier / hash / count fields."""
    raw = _read()
    # All the fields we record under metadata.scientific_intake:
    for f in (
        '"intake_id"',
        '"combined_context_sha256"',
        '"prompt_sha256"',
        '"documents_count"',
        '"intake_task_kind"',
        '"intake_artifact_sha256"',
    ):
        assert f in raw, (
            f"metadata field {f} missing from intake-bridge writer"
        )
    # We must NOT propagate any document body / preview into the
    # request itself.
    stripped = _strip(raw)
    # text_preview should appear only inside string literals in
    # the source (read of intake), never as a bare identifier
    # being assigned to a request field. After _strip, it should
    # be gone entirely.
    assert "text_preview" not in stripped, (
        "task builder must not reference text_preview in code"
    )
    assert "path_basename" not in stripped, (
        "task builder must not reference path_basename in code"
    )


def test_no_absolute_path_propagation():
    """The bridge stores `path_basename` from the intake at most;
    no `.resolve()` / `os.path.abspath` is used. We check by
    grepping the stripped source."""
    stripped = _strip(_read())
    assert ".resolve()" not in stripped
    assert "os.path.abspath" not in stripped
