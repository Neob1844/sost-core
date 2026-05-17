"""Static safety surface for scripts/trinity/governor_watchdog.py
(Sprint 5.25).

The Watchdog is a read-only observer of the Autonomy Governor audit
trail. It MUST NOT touch wallets, sign anything, broadcast anything,
or shell out. It MAY have stdlib network reachability for the future
webhook dispatch, but v0.1 has it gated and not exercised — see
tests/trinity/test_governor_watchdog.py for the runtime contract.

This file enforces, by plain substring grep, that the Watchdog
source cannot acquire dangerous capabilities by accident in a
future PR. The grep is intentionally simple so a reviewer can
scan it.

This file also re-asserts that scripts/trinity/autonomy_governor.py
did NOT regain any forbidden token in the course of Sprint 5.25;
the Governor's own safety file already enforces this, but adding
the cross-check here means the Watchdog cannot smuggle a banned
token into the Governor via a shared helper.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "governor_watchdog.py"
GOVERNOR = REPO_ROOT / "scripts" / "trinity" / "autonomy_governor.py"


# Substrings that must NEVER appear in the Watchdog source. The
# Watchdog must stay off the wallet/signing/broadcast surface, off
# the shell, off dynamic code execution. urllib is allowed because
# the future webhook dispatch will use stdlib http.
FORBIDDEN_TOKENS_WATCHDOG = (
    # Wallet / signing / broadcast primitives.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # Reward / payment surfaces.
    "payment_proposal", "payment_draft", "reward_budget",
    # Shell / subprocess.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution.
    "eval(", "exec(",
    # Mutating filesystem ops on inputs (the watchdog is read-only
    # on the decisions dir; it MAY write the report to out-dir
    # via open(..., 'w') for the report file only).
    ".unlink(", ".rmdir(", "shutil.rmtree", "os.remove(", "os.unlink(",
    "os.chmod(", ".chmod(", "os.rename(",
)


FORBIDDEN_TOKENS_GOVERNOR_UNCHANGED = (
    "import requests", "from requests",
    "import urllib", "from urllib",
    "import httpx", "from httpx",
    "import aiohttp", "from aiohttp",
    "import socket", "from socket",
    "import websockets", "from websockets",
    "requests.", "urllib.",
    "httpx.", "aiohttp.", "socket.", "websockets.",
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    "eval(", "exec(",
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sendrawtransaction(", "broadcast(",
    "sost-cli",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def test_watchdog_source_exists():
    assert SCRIPT.is_file(), "governor_watchdog.py not found at " + str(SCRIPT)


def test_watchdog_has_no_forbidden_tokens():
    src = _read(SCRIPT)
    found = [t for t in FORBIDDEN_TOKENS_WATCHDOG if t in src]
    assert not found, (
        "scripts/trinity/governor_watchdog.py contains forbidden "
        + "token(s): " + repr(found)
        + ". The Watchdog v0.1 must stay off shell / wallet / "
        + "signing / broadcast / mutation."
    )


def test_watchdog_does_not_import_governor_internals():
    """The Watchdog must NOT import the Autonomy Governor module.
    Cross-module imports between safety-critical components are
    forbidden in v0.1 — the Watchdog only reads JSON files."""
    src = _read(SCRIPT)
    for tok in (
        "import autonomy_governor",
        "from autonomy_governor",
        "useful_compute_operator_loop",
        "useful_compute_task_builder",
        "useful_compute_worker",
        "useful_compute_payment",
    ):
        assert tok not in src, (
            "Watchdog must not import sibling Trinity module: " + tok
        )


def test_watchdog_declares_schema_constant():
    """A grep-level check that the Watchdog uses the v0.1 schema
    string. If a future PR silently bumps to v0.2 without also
    updating the schema file, this test fails."""
    src = _read(SCRIPT)
    assert "trinity-governor-watchdog-report/v0.1" in src
    assert "trinity-autonomy-governor-decision/v0.1" in src


def test_watchdog_denylist_present_in_source():
    """The PATH_DENYLIST symbols must remain wired and contain at
    least the four cores: wallets, secrets, .git, .ssh."""
    src = _read(SCRIPT)
    assert "PATH_DENYLIST" in src
    for tok in ('"wallets"', '"secrets"', '".git"', '".ssh"'):
        assert tok in src, (
            "PATH_DENYLIST is missing required entry: " + tok
        )


def test_watchdog_webhook_does_not_actually_fetch_in_v01():
    """v0.1 contract: the Watchdog source MUST NOT contain any of
    the stdlib network primitives that would actually open a
    socket. The webhook URL is recorded only; dispatch arrives in
    a later sprint."""
    src = _read(SCRIPT)
    for tok in (
        "urlopen(", "urllib.request",
        "http.client.HTTPConnection", "http.client.HTTPSConnection",
        "requests.post(", "requests.get(",
        "socket.socket(", "socket.create_connection(",
    ):
        assert tok not in src, (
            "Watchdog v0.1 must not actually open the network: "
            + tok
        )


def test_governor_still_has_no_forbidden_tokens_after_5_25():
    """Cross-check: Sprint 5.25 must not regress the Governor's
    static safety surface. If a Watchdog refactor accidentally
    moves a banned token into the Governor module, this fails CI."""
    src = _read(GOVERNOR)
    found = [t for t in FORBIDDEN_TOKENS_GOVERNOR_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.25 introduced a forbidden token into the "
        "Governor: " + repr(found)
    )
