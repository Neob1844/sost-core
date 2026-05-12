"""Static safety surface for scripts/trinity/useful_compute_real_signer.py.

This module is the ONLY Trinity script allowed to spawn a
subprocess. Its safety surface is therefore wider than
useful_compute_payment_draft.py but very strict in WHAT it can do:

- subprocess.run is allowed, but only with shell=False
- subprocess.Popen / subprocess.call / os.system are still BANNED
- argv must construct only `sost-cli` invocations
- only the `createtx` subcommand is allowed (allowlist tuple)
- forbidden argv tokens are denied at runtime
- no HTTP / TCP / WebSocket imports
- no private-key tokens (privkey, seed_phrase, mnemonic, passphrase)
- no consensus/node imports
- no real-signing TOKENs that bypass the wrapper
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "trinity"
    / "useful_compute_real_signer.py"
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


def test_subprocess_run_present_but_no_shell(_read=_read):
    """Real signer MUST use subprocess.run (it's the wrapper) but
    MUST NOT use Popen / call / os.system, and MUST always pass
    shell=False."""
    src = _read()
    stripped = _strip(src)
    assert "subprocess.run" in stripped, (
        "real signer must use subprocess.run to call sost-cli"
    )
    for tok in ("subprocess.Popen", "subprocess.call",
                "subprocess.check_call", "subprocess.check_output",
                "os.system"):
        assert tok not in stripped, (
            f"forbidden process primitive {tok!r}"
        )
    # shell= must always be False where it appears.
    for m in re.finditer(r"shell\s*=\s*([A-Za-z]+)", stripped):
        assert m.group(1) == "False", (
            f"subprocess shell= must be False; saw {m.group(0)}"
        )


def test_no_network_imports(_read=_read):
    src = _strip(_read())
    for name in (
        "requests", "urllib.request", "urllib3", "httpx",
        "aiohttp", "socket", "websockets",
    ):
        m = re.search(
            rf"^\s*(?:import|from)\s+{re.escape(name)}\b",
            src, re.MULTILINE,
        )
        assert m is None, (
            f"forbidden network import {name!r}"
        )


def test_no_private_key_tokens(_read=_read):
    """The real signer hashes the wallet file but never parses it;
    it must not contain private-key tokens as bare identifiers."""
    src = _strip(_read()).lower()
    for tok in ("private_key", "privkey", "seed_phrase",
                "mnemonic", "passphrase"):
        assert tok not in src, (
            f"private-key token {tok!r} found in code"
        )


def test_no_consensus_or_node_import(_read=_read):
    src = _strip(_read())
    for tok in ("from sost.node", "import sost_node",
                "consensus.", "tx_validation", "tx_signer"):
        assert tok not in src, (
            f"forbidden consensus/node token {tok!r}"
        )


def test_argv_allowlist_present(_read=_read):
    """The module must declare an allowlist of subcommands and a
    tuple of forbidden argv tokens, and it must scan argv with
    `_scan_argv_safety` before spawning a subprocess."""
    raw = _read()
    assert "_ALLOWED_SUBCOMMANDS" in raw
    assert '"createtx"' in raw
    assert "_FORBIDDEN_ARGV_TOKENS" in raw
    for flag in (
        '"--broadcast"', '"--send"', '"--payout-now"',
        '"--auto-pay"', '"--sendrawtransaction"',
        '"--export-private-key"',
    ):
        assert flag in raw, (
            f"forbidden token {flag} missing from allowlist"
        )
    stripped = _strip(raw)
    assert "_scan_argv_safety" in stripped


def test_only_sost_cli_subcommands_in_argv_construction(_read=_read):
    """The argv built by call_sost_cli_createtx must only reference
    string-literal `createtx` for the subcommand. There must NOT be
    any other subcommand reachable through this module."""
    raw = _read()
    # The literal createtx is intentional. Forbidden subcommands
    # must not appear AT ALL — neither as code nor as string
    # literals — to keep the module trivially auditable.
    for forbidden in (
        '"send"', '"sendmany"', '"sendrawtransaction"',
        '"importprivkey"', '"signrawtransactionwithwallet"',
    ):
        assert forbidden not in raw, (
            f"forbidden CLI subcommand literal {forbidden}"
        )


def test_no_rpc_write_method_strings(_read=_read):
    """The module must not contain any RPC write-method string
    that could be invoked even by accident."""
    raw = _read()
    for tok in (
        "sendrawtransaction", "importprivkey", "dumpprivkey",
        "walletpassphrase", "encryptwallet",
    ):
        # The token "sendrawtransaction" is explicitly listed in
        # _FORBIDDEN_ARGV_TOKENS as "--sendrawtransaction"; the
        # bare token must not appear anywhere else.
        if tok == "sendrawtransaction":
            occurrences = [
                m.start() for m in re.finditer(re.escape(tok), raw)
            ]
            assert len(occurrences) <= 2, (
                "sendrawtransaction may appear at most in the "
                "forbidden-token tuple, not as a real call"
            )
        else:
            assert tok not in raw, (
                f"forbidden RPC write token {tok!r}"
            )


def test_timeout_parameter_present(_read=_read):
    """subprocess.run must pass a timeout to prevent hangs."""
    stripped = _strip(_read())
    assert "timeout=" in stripped


def test_no_dynamic_execution(_read=_read):
    """The real signer must not call eval / exec / dynamic compile.
    `re.compile` (regex compilation) is whitelisted explicitly."""
    stripped = _strip(_read())
    # Strip every `re.compile(...)` call before scanning so the
    # bare `compile(` check still has signal on truly forbidden uses.
    stripped_no_re = re.sub(r"re\.compile\(", "", stripped)
    for tok in ("eval(", "exec(", "compile("):
        assert tok not in stripped_no_re, (
            f"forbidden dynamic-execution primitive {tok!r}"
        )
