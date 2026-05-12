"""Static safety surface for website/trinity-useful-compute.html.

The page must NOT mention dangerous concepts as user-facing affordances
(private keys, seed phrases, RPC passwords, sendrawtransaction,
automatic payout) and must NOT contain network-fetch primitives.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_PATH = REPO_ROOT / "website" / "trinity-useful-compute.html"


_FORBIDDEN_PROMPT_PHRASES = (
    # PROMPT-style phrases that would ask the user to enter or paste
    # sensitive material. Pure denials (e.g. "does not pay
    # automatically", "no automatic payout", "does not ask for any
    # recovery phrase") are allowed and required elsewhere.
    "enter your private key",
    "paste your private key",
    "submit private key",
    "type your private key",
    "enter your seed",
    "paste your seed phrase",
    "paste your recovery phrase",
    "enter rpc password",
    "enter your wallet",
    "paste your wallet",
    "restore wallet",
    "broadcast transaction",
    "sign transaction now",
    "sendrawtransaction",
    "submit signed tx",
    "trigger payout",
)


# Promised denials — the page MUST say these out loud.
_REQUIRED_DENIAL_PHRASES = (
    "does not pay automatically",
    "no automatic payout",
    "does not connect to any wallet",
)


# JS network-fetch primitives that would let the page leak data.
_FORBIDDEN_NETWORK_PRIMITIVES = (
    "fetch(", "XMLHttpRequest", "new WebSocket(", "EventSource(",
    "navigator.sendBeacon",
)


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


def test_web_does_not_prompt_for_private_keys():
    src = _read().lower()
    for phrase in _FORBIDDEN_PROMPT_PHRASES:
        assert phrase.lower() not in src, (
            f"web page contains forbidden PROMPT-style phrase: "
            f"{phrase!r} — denials are allowed, prompts are not"
        )


def test_web_carries_required_denials():
    src = _read().lower()
    for phrase in _REQUIRED_DENIAL_PHRASES:
        assert phrase.lower() in src, (
            f"web page is missing required denial phrase: {phrase!r}"
        )


def test_web_has_no_sensitive_input_fields():
    """Even subtler: no <input> element should declare a name/id/
    placeholder that asks for a secret."""
    src = _read()
    inputs = re.findall(r"<input\b[^>]*>", src, re.IGNORECASE)
    for tag in inputs:
        lower = tag.lower()
        for forbidden in (
            "private", "wallet", "seed", "mnemonic", "passphrase",
            "rpcpass", "rpcuser", "signature",
        ):
            assert forbidden not in lower, (
                f"<input> element looks sensitive: {tag}"
            )


def test_web_does_not_use_network_primitives():
    src = _read()
    for token in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert token not in src, (
            f"web page contains forbidden network primitive: {token!r}"
        )


def test_web_declares_no_payout_and_pending_only():
    src = _read().lower()
    # The page MUST tell the user, in plain language, that it does
    # not pay automatically and that rewards are pending only.
    assert "does not pay automatically" in src
    assert "pending" in src
    assert "no automatic payout" in src


def test_web_declares_no_network_calls():
    src = _read().lower()
    # Either the explicit "no network calls" disclaimer or "never
    # connects to the network".
    assert (
        "no network calls" in src
        or "never connects to the network" in src
    )


def test_web_declares_no_wallet_or_keys():
    src = _read().lower()
    # The page must publicly state it never touches keys/wallets.
    assert "does not connect to any wallet" in src
    assert "private keys" in src  # phrase must appear in the DENIAL


def test_web_carries_v01_badge():
    src = _read()
    assert 'v0.1' in src
    assert 'local-dry-run' in src


def test_web_references_local_worker_cli():
    src = _read()
    # The exact CLI command surface must appear so users can copy it.
    assert "scripts/trinity/useful_compute_worker.py" in src
    assert "--mode local-dry-run" in src


def test_web_robots_noindex_meta():
    src = _read()
    assert re.search(
        r'<meta\s+name="robots"\s+content="noindex',
        src,
        re.IGNORECASE,
    ) is not None
