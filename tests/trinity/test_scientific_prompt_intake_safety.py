"""Static safety surface for
scripts/trinity/scientific_prompt_intake.py (Sprint 5.20).

The intake script is purely local: read prompt + documents from
disk, hash them, write one canonical JSON. No network, no LLM, no
wallet, no signer, no broadcast. These tests pin those invariants
at the source level so a future edit cannot quietly introduce any
of them.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "trinity"
    / "scientific_prompt_intake.py"
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


def test_no_sost_cli_references():
    src = _strip(_read())
    for tok in ("sost-cli", "sost_cli", "sendrawtransaction"):
        assert tok not in src, (
            f"forbidden sost-cli reference {tok!r}"
        )


def test_no_wallet_or_private_key_tokens():
    """No wallet/private-key/seed tokens may appear as bare
    identifiers in executable code."""
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


def test_no_llm_or_remote_api_tokens():
    """Trinity v0.1 intake stays local. Mentioning the names of
    common LLM APIs as bare identifiers in code would suggest a
    network call path; reject them defensively."""
    src = _strip(_read()).lower()
    for tok in ("openai", "anthropic", "claude_api",
                "completion(", "chat.completions"):
        assert tok not in src, (
            f"forbidden LLM/api token {tok!r}"
        )


def test_no_dynamic_execution():
    stripped = _strip(_read())
    stripped_no_re = re.sub(r"re\.compile\(", "", stripped)
    for tok in ("eval(", "exec(", "compile(", "execfile("):
        assert tok not in stripped_no_re, (
            f"forbidden dynamic-execution primitive {tok!r}"
        )


def test_rejected_flags_present():
    raw = _read()
    for flag in (
        '"--broadcast"', '"--send"', '"--payout-now"',
        '"--auto-pay"', '"--sign-now"',
        '"--export-private-key"', '"--wallet"',
        '"--llm-call"', '"--http-call"', '"--upload"',
    ):
        assert flag in raw, (
            f"rejected flag literal {flag} missing"
        )
    stripped = _strip(raw)
    assert "raw_argv" in stripped
    assert "return 2" in stripped


def test_const_safety_flags_emitted_true():
    """All seven safety flags must be written as True (the schema
    also enforces const-true, but a bug in the writer would still
    produce an artifact rejected at validation time — this test
    catches that earlier)."""
    raw = _read()
    for k in (
        "local_only", "no_network", "no_llm_call",
        "no_wallet_access", "no_broadcast", "no_private_keys",
        "deterministic_output",
    ):
        assert k in raw, (
            f"safety flag {k!r} not emitted by the writer"
        )
        # Each safety flag must be set True (not False, not a var).
        assert re.search(
            rf'"{re.escape(k)}":\s*True', raw,
        ) is not None, (
            f"safety flag {k!r} must be set to True literally"
        )


def test_no_absolute_path_in_output():
    """The artifact records `path_basename`, never the full path.
    Confirm the writer emits the field literally named
    `path_basename` and does not emit a bare `path` field."""
    raw = _read()
    assert '"path_basename"' in raw, (
        "writer must use the path_basename JSON field"
    )
    # Inside the _read_document writer body, the dict assembled for
    # each doc must NOT include a "path" key. Check by looking at
    # the segment between def _read_document and its `return`.
    body = raw.split("def _read_document", 1)[-1]
    body_until_return = body.split("return {", 1)[-1].split("}", 1)[0]
    assert '"path":' not in body_until_return, (
        "writer must not emit a 'path' field (only path_basename)"
    )
