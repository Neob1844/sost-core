"""Static safety surface for Step 7 (Background Autonomy Loop) of
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
    "click to pay",
    "send rewards now",
    "start mining now",
    "auto-pay",
)


def _read():
    return WEB_PATH.read_text(encoding="utf-8")


def test_background_section_present():
    src = _read()
    assert "Step 7" in src
    assert "Background Autonomy Loop" in src


def test_background_section_has_no_network_primitives():
    src = _read()
    for tok in _FORBIDDEN_NETWORK_PRIMITIVES:
        assert tok not in src, (
            f"background section contains forbidden network "
            f"primitive: {tok!r}"
        )


def test_background_section_has_no_sensitive_input_fields():
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


def test_background_section_does_not_prompt_for_secrets():
    src = _read().lower()
    for phrase in _FORBIDDEN_PROMPT_PHRASES:
        assert phrase.lower() not in src, (
            f"web page contains forbidden PROMPT phrase {phrase!r}"
        )


def test_background_section_declares_local_dry_run_only():
    src = _read().lower()
    assert "local-dry-run" in src
    assert "does not pay" in src or "never pays" in src


def test_background_section_carries_daemon_cli_command():
    src = _read()
    assert "trinity_background_daemon.py" in src
    assert "--mode local-dry-run" in src
    assert "--watch" in src or "--run-once" in src
    assert "--workspace" in src


def test_background_section_reads_daemon_state_schema_string():
    src = _read()
    assert "trinity-background-daemon-state/v0.1" in src


def test_daemon_present_in_badge():
    # The badge version is bumped sprint-over-sprint; what matters is
    # that "daemon" is named once Sprint 5.10 has shipped.
    src = _read()
    assert "daemon" in src.lower()
