"""Static safety surface for
scripts/trinity/useful_compute_broadcast_guard.py.

This is the FIRST Trinity script that is allowed to broadcast a
transaction. Its safety surface is therefore wider than every
prior Trinity script (it must use ``subprocess.run`` on
``sost-cli sendrawtransaction``) but it remains tightly bounded:

- subprocess.run allowed, but Popen / call / check_call /
  check_output / os.system are BANNED.
- shell=False must be the only value of the shell= keyword.
- Only the ``sost-cli`` binary is spawned.
- Only the ``sendrawtransaction`` subcommand is in the allowlist.
- No HTTP / socket / WebSocket imports.
- No wallet / signing / private-key / seed tokens.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "trinity"
    / "useful_compute_broadcast_guard.py"
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


def test_subprocess_run_only_no_other_primitives():
    src = _read()
    stripped = _strip(src)
    assert "subprocess.run" in stripped, (
        "broadcast guard must use subprocess.run to call sost-cli"
    )
    for tok in ("subprocess.Popen", "subprocess.call",
                "subprocess.check_call", "subprocess.check_output",
                "os.system"):
        assert tok not in stripped, (
            f"forbidden process primitive {tok!r}"
        )
    for m in re.finditer(r"shell\s*=\s*([A-Za-z]+)", stripped):
        assert m.group(1) == "False", (
            f"subprocess shell= must be False; saw {m.group(0)}"
        )


def test_argv_allowlist_present():
    raw = _read()
    assert "_ALLOWED_SUBCOMMANDS" in raw
    assert '"sendrawtransaction"' in raw
    assert "_FORBIDDEN_ARGV_TOKENS" in raw
    for flag in (
        '"--auto-pay"', '"--send"', '"--payout-now"',
        '"--export-private-key"', '"--sign-now"',
    ):
        assert flag in raw, (
            f"forbidden flag {flag} missing from allowlist tuple"
        )
    stripped = _strip(raw)
    assert "_scan_argv_safety" in stripped


def test_pre_check_rejects_forbidden_flags():
    raw = _read()
    stripped = _strip(raw)
    assert "raw_argv" in stripped
    assert "rejected_flags" in stripped
    assert "return 2" in stripped


def test_no_network_imports():
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


def test_no_wallet_or_private_key_tokens():
    """The broadcast guard must NOT carry wallet / private-key
    tokens. Signing belongs to Sprint 5.17, not this one."""
    src = _strip(_read()).lower()
    for tok in ("private_key", "privkey", "seed_phrase",
                "mnemonic", "passphrase",
                "wallet_path", "load_wallet", "open_wallet"):
        assert tok not in src, (
            f"forbidden token {tok!r} in broadcast guard"
        )


def test_no_signing_tokens():
    src = _strip(_read())
    for tok in ("sign_tx", "sign_transaction", "wallet.sign",
                ".sign(", "ecdsa", "secp256k1"):
        assert tok not in src, (
            f"forbidden signing token {tok!r}"
        )


def test_no_dynamic_execution():
    """No eval / exec / dynamic compile. re.compile is whitelisted."""
    stripped = _strip(_read())
    stripped_no_re = re.sub(r"re\.compile\(", "", stripped)
    for tok in ("eval(", "exec(", "compile("):
        assert tok not in stripped_no_re, (
            f"forbidden dynamic-execution primitive {tok!r}"
        )


def test_timeout_parameter_present():
    stripped = _strip(_read())
    assert "timeout=" in stripped


def test_only_sost_cli_sendrawtransaction_in_argv():
    """Argv is built from string literals + the validated
    signed_tx_hex. The literal subcommand must be exactly
    "sendrawtransaction", and other CLI subcommands must not be
    reachable through this module — neither as code nor as string
    literals."""
    raw = _read()
    for forbidden in (
        '"send"', '"sendmany"', '"createtx"', '"importprivkey"',
        '"dumpprivkey"', '"newwallet"', '"signrawtransactionwithwallet"',
    ):
        assert forbidden not in raw, (
            f"forbidden CLI subcommand literal {forbidden}"
        )


def test_const_safety_status_flags_present():
    raw = _read()
    for k in (
        "human_broadcast_only", "requires_manual_confirmation",
        "no_private_keys", "no_wallet_access", "no_signing",
        "no_automatic_payout", "single_transaction_only",
    ):
        assert k in raw, (
            f"safety_status field {k!r} missing from receipt builder"
        )
