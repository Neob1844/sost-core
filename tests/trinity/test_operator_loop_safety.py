"""Static safety surface for
scripts/trinity/useful_compute_operator_loop.py (Sprint 5.19).

The operator loop drives the full Useful Compute pipeline end-to-end
in dry-run mode. It MUST NOT contain any token that would let it
slip into real signing or broadcasting, even by accident, and it
MUST NOT shell out to sost-cli. Sibling Trinity scripts are loaded
via importlib + main(argv=[...]); no subprocess is used by the
loop itself.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "trinity"
    / "useful_compute_operator_loop.py"
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


def test_no_sost_cli_references():
    """The loop must not reach sost-cli in any way. The
    downstream payment_draft module can drive sost-cli when given
    real-sign, but the loop only ever passes --unsigned-only or
    --dry-sign. We strip docstrings/strings/comments first so
    the test inspects EXECUTABLE code, not prose."""
    src = _strip(_read())
    for tok in ("sost-cli", "sost_cli"):
        assert tok not in src, (
            f"forbidden sost-cli reference {tok!r}"
        )


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


def test_no_real_sign_token():
    """The loop must not invoke the real-signing path. After
    stripping docstrings / strings / comments, the executable code
    must contain no reference to the real-sign flag or token."""
    src = _strip(_read())
    assert "--real-sign" not in src, (
        "operator loop executable code references --real-sign"
    )
    assert "I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST" not in src


def test_no_human_broadcast_mode_token():
    src = _strip(_read())
    assert "human-broadcast" not in src, (
        "operator loop executable code references --mode "
        "human-broadcast"
    )
    assert "I_UNDERSTAND_THIS_WILL_BROADCAST_A_SIGNED_TRANSACTION" \
        not in src


def test_no_sendrawtransaction_token():
    raw = _read()
    # Pre-argparse rejection allows the literal "--sendrawtransaction"
    # in the REJECTED_FLAGS tuple. We check the bare token does NOT
    # appear OUTSIDE that allowed location.
    assert raw.count("sendrawtransaction") <= 1, (
        "operator loop references sendrawtransaction beyond the "
        "rejection list (max 1 occurrence allowed if present at all)"
    )


def test_no_wallet_or_private_key_tokens():
    """After stripping string literals (including the
    REJECTED_FLAGS tuple), no wallet / private-key token may
    appear as a bare identifier in the loop's code."""
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
    """re.compile is the only compile/exec primitive allowed."""
    stripped = _strip(_read())
    stripped_no_re = re.sub(r"re\.compile\(", "", stripped)
    for tok in ("eval(", "exec(", "compile("):
        assert tok not in stripped_no_re, (
            f"forbidden dynamic-execution primitive {tok!r}"
        )


def test_rejected_flags_tuple_present():
    """The loop must declare REJECTED_FLAGS and scan raw_argv for
    them before argparse runs."""
    raw = _read()
    assert "REJECTED_FLAGS" in raw
    for flag in (
        '"--broadcast"', '"--send"', '"--payout-now"',
        '"--auto-pay"', '"--sign-now"',
        '"--export-private-key"', '"--wallet"',
        '"--from-label"', '"--from-address"',
        '"--allow-wallet-access"', '"--allow-broadcast"',
    ):
        assert flag in raw, (
            f"rejected flag {flag} missing from REJECTED_FLAGS"
        )
    stripped = _strip(raw)
    assert "raw_argv" in stripped
    assert "return 2" in stripped


def test_operator_token_present_as_string_literal():
    raw = _read()
    assert "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP" in raw


def test_const_safety_flags_recorded_false():
    """allow_wallet_access and allow_broadcast must be locked to
    false in the operator_run state file. The schema enforces it;
    the script must also write them as False, not via a flag."""
    raw = _read()
    # Both fields must appear and be explicitly False.
    assert '"allow_wallet_access": False' in raw
    assert '"allow_broadcast": False' in raw
    assert '"human_review_required": True' in raw
