"""Static safety surface for Trinity Web Miner Console v0.1.

Confirms website/trinity-useful-compute.html does NOT:
- carry network primitives (fetch, XHR, WebSocket, EventSource, beacon)
- ask for wallets, private keys, RPC credentials, seed phrases
- use innerHTML with externally-loaded file content
- mention automatic payout language as a prompt
- expose a "submit / sign / broadcast" affordance
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PATH = REPO_ROOT / "website" / "trinity-useful-compute.html"


_FORBIDDEN_NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "new WebSocket(", "EventSource(",
    "navigator.sendBeacon",
)


_FORBIDDEN_PROMPT_PHRASES = (
    "enter your private key",
    "paste your private key",
    "submit private key",
    "enter your seed",
    "paste your seed phrase",
    "paste your recovery phrase",
    "enter rpc password",
    "enter rpc-pass",
    "enter your wallet",
    "paste your wallet",
    "restore wallet",
    "broadcast transaction",
    "sign transaction now",
    "sendrawtransaction",
    "submit signed tx",
    "trigger payout",
    "click to pay",
    "send rewards now",
    "start mining now",
    "auto-pay",
)


_FORBIDDEN_INPUT_TOKENS = (
    "private", "wallet", "seed", "mnemonic", "passphrase",
    "rpcpass", "rpcuser", "signature",
)


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Network + prompt + input safety
# ---------------------------------------------------------------------------


def test_no_network_primitives():
    src = _read()
    for tok in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert tok not in src, (
            f"web page contains forbidden network primitive: {tok!r}"
        )


def test_no_prompt_phrases_for_secrets():
    src = _read().lower()
    for phrase in _FORBIDDEN_PROMPT_PHRASES:
        assert phrase.lower() not in src, (
            f"web page contains forbidden PROMPT phrase {phrase!r}"
        )


def test_no_sensitive_input_fields():
    src = _read()
    inputs = re.findall(r"<input\b[^>]*>", src, re.IGNORECASE)
    for tag in inputs:
        lower = tag.lower()
        for forbidden in _FORBIDDEN_INPUT_TOKENS:
            assert forbidden not in lower, (
                f"<input> looks sensitive: {tag}"
            )


# ---------------------------------------------------------------------------
# innerHTML safety: rule is "never assign innerHTML from externally-
# loaded content". The console JS uses textContent everywhere user
# file bytes flow through. Confirm by scanning for innerHTML uses and
# bounding what is acceptable.
# ---------------------------------------------------------------------------


def test_no_innerHTML_assignment_with_external_content():
    """innerHTML assignment is allowed only for resets to '' (clearing
    a node). Any other innerHTML assignment in the file is treated as
    a violation."""
    src = _read()
    # Collect every "innerHTML = ..." assignment
    matches = re.findall(
        r"\.innerHTML\s*=\s*([^;]+);", src,
    )
    for rhs in matches:
        rhs_stripped = rhs.strip()
        # Only allow ".innerHTML = '';" or ".innerHTML = "";"
        assert rhs_stripped in ('""', "''"), (
            f"forbidden innerHTML assignment with non-empty RHS: "
            f"{rhs_stripped!r}"
        )


def test_no_document_write():
    src = _read()
    assert "document.write" not in src, (
        "document.write is unsafe; use textContent / createElement"
    )


def test_no_eval_or_function_constructor():
    src = _read()
    # 'eval(' is the canonical risky form.
    assert re.search(r"\beval\s*\(", src) is None, (
        "eval() is forbidden in the page"
    )
    assert "new Function(" not in src, (
        "new Function() is forbidden in the page"
    )


# ---------------------------------------------------------------------------
# Required denials on the page
# ---------------------------------------------------------------------------


def test_console_declares_no_payment_and_governance():
    src = _read().lower()
    assert "does not pay" in src or "never pays" in src
    assert "governance" in src
    assert "human-signed" in src or "human review" in src or \
        "human_review_required_before_payment" in src


def test_console_declares_no_network():
    src = _read().lower()
    assert "no network calls" in src or \
        "this page never reaches the network" in src or \
        "no network primitives" in src or \
        "never reaches the network" in src


def test_console_present_in_badge_text():
    src = _read()
    assert "console" in src.lower()


# ---------------------------------------------------------------------------
# Stock-counter labels are present (visible to the user)
# ---------------------------------------------------------------------------


def test_visible_counter_labels_present():
    src = _read()
    for label in (
        "pending_unvalidated_stocks",
        "replay_accepted_stocks",
        "governance_approved_stocks",
        "rejected_or_manual_review_stocks",
        "approved_pending_reward_stocks",
    ):
        assert label in src, (
            f"console must display label {label!r}"
        )
