"""Static safety surface for scripts/trinity/useful_compute_payment_draft.py.

These tests are layered on top of the Sprint 5.6 static safety
extension. Even after Sprint 5.17 introduces real signing, the
higher-level `useful_compute_payment_draft.py` script must REMAIN
free of subprocess, network, signing, consensus and private-key
tokens — all of that lives in the sibling delegate
`useful_compute_real_signer.py` (which has its own stricter test
file: `test_payment_draft_real_sign_safety.py`).
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPO_ROOT / "scripts" / "trinity"
    / "useful_compute_payment_draft.py"
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


def test_pre_check_rejects_forbidden_flags(_read=_read):
    """The script must contain the rejected_flags tuple AND a
    pre-argparse check that scans raw_argv for those flags. After
    stripping string literals the tuple disappears, but the
    decision loop ("if f in raw_argv: ... return 2") remains and
    must still be visible in the stripped source."""
    raw = _read()
    for flag in (
        '"--broadcast"', '"--send"', '"--payout-now"',
        '"--auto-pay"', '"--sendrawtransaction"',
        '"--export-private-key"',
    ):
        assert flag in raw, (
            f"forbidden flag {flag} missing from rejection tuple"
        )
    stripped = _strip(raw)
    assert "raw_argv" in stripped
    assert "rejected_flags" in stripped
    assert "return 2" in stripped


def test_no_subprocess_or_shell(_read=_read):
    """payment_draft.py itself must NOT contain subprocess tokens.
    Real signing is delegated to `useful_compute_real_signer.py`
    via importlib; this file remains subprocess-free so its
    Sprint 5.6 static safety surface is preserved."""
    src = _strip(_read())
    for tok in ("subprocess.run", "subprocess.Popen",
                "subprocess.call", "os.system"):
        assert tok not in src


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
            f"forbidden network import {name!r} in payment draft"
        )


def test_no_private_key_handling(_read=_read):
    """No argparse attribute carries a private-key token. Strip
    strings and confirm none of the forbidden tokens appear as
    bare identifiers."""
    src = _strip(_read()).lower()
    for tok in ("private_key", "privkey", "seed_phrase",
                "mnemonic", "passphrase"):
        assert tok not in src, (
            f"private-key token {tok!r} found in code "
            "(string-literal denials are stripped)"
        )


def test_no_direct_signing_in_payment_draft(_read=_read):
    """payment_draft.py must not invoke any signing function
    directly. Real signing happens through the real_signer
    delegate. Cheap heuristic: the strings 'sign_tx',
    'sign_transaction', 'wallet.sign', '.sign(' must not appear in
    code paths (after stripping)."""
    src = _strip(_read())
    forbidden = (
        "sign_tx", "sign_transaction", "wallet.sign", ".sign(",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"forbidden signing token {tok!r} present in code"
        )


def test_no_consensus_or_node_import(_read=_read):
    src = _strip(_read())
    for tok in ("from sost.node", "import sost_node",
                "consensus.", "tx_validation", "tx_signer"):
        assert tok not in src, (
            f"forbidden consensus/node token {tok!r}"
        )


def test_v02_schema_constant_present(_read=_read):
    """Sprint 5.17 bumps the schema to v0.2. The script must
    advertise that exact schema id, not v0.1."""
    raw = _read()
    assert "trinity-useful-compute-payment-draft/v0.2" in raw
    assert "trinity-useful-compute-payment-draft/v0.1" not in raw


def test_real_sign_token_present(_read=_read):
    """The real-sign confirmation token must be a string literal
    in the script (the gate that protects --real-sign)."""
    raw = _read()
    assert "I_UNDERSTAND_THIS_WILL_SIGN_BUT_NOT_BROADCAST" in raw
