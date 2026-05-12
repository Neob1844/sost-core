"""Static safety surface for the replay section of
website/trinity-useful-compute.html."""

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
    "enter your wallet",
    "paste your wallet",
    "restore wallet",
    "broadcast transaction",
    "sign transaction now",
    "sendrawtransaction",
    "submit signed tx",
    "trigger payout",
)


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


def test_replay_section_present():
    src = _read()
    assert "Validate Replay Results" in src
    assert "Step 5" in src


def test_replay_section_uses_compute_output_sha256():
    src = _read()
    # The replay JS must group results by compute_output_sha256.
    assert "compute_output_sha256" in src


def test_replay_section_uses_worker_result_id():
    src = _read()
    assert "worker_result_id" in src


def test_replay_section_has_no_network_primitives():
    src = _read()
    for token in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert token not in src, (
            f"replay section contains forbidden network primitive: "
            f"{token!r}"
        )


def test_replay_section_has_no_sensitive_input_fields():
    src = _read()
    inputs = re.findall(r"<input\b[^>]*>", src, re.IGNORECASE)
    for tag in inputs:
        lower = tag.lower()
        for forbidden in (
            "private", "wallet", "seed", "mnemonic", "passphrase",
            "rpcpass", "rpcuser", "signature",
        ):
            assert forbidden not in lower, (
                f"<input> looks sensitive: {tag}"
            )


def test_replay_section_does_not_prompt_for_secrets():
    src = _read().lower()
    for phrase in _FORBIDDEN_PROMPT_PHRASES:
        assert phrase.lower() not in src, (
            f"web page contains forbidden PROMPT phrase {phrase!r}"
        )


def test_replay_section_carries_cli_command():
    src = _read()
    assert "useful_compute_replay_validator.py" in src
    assert "--mode local-dry-run" in src
    assert "--min-workers" in src


def test_replay_disclaimer_present():
    src = _read().lower()
    # The page must say accepted does NOT pay.
    assert "does not pay" in src
    assert "governance" in src


def test_v02_badge_present():
    src = _read()
    assert "v0.2" in src
    assert "replay" in src.lower()
