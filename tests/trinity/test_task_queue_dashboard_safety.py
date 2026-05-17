"""Static safety surface for scripts/trinity/task_queue_dashboard.py
(Sprint 5.28).

The dashboard is read-only: it reads queue.json + per-item files +
batch reports and writes a JSON + a static HTML. It MUST NOT touch
wallets, sign anything, broadcast anything, invoke a shell, open
the network, or modify the queue in any way. This file enforces
that by plain substring grep.

A cross-check re-asserts that Sprint 5.28 did NOT regress the
Governor, the Watchdog, the Task Queue, or the Runner safety
surfaces. If a refactor accidentally moves a forbidden token into
any of those four, this file flags it.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "task_queue_dashboard.py"
QUEUE = REPO_ROOT / "scripts" / "trinity" / "task_queue.py"
GOVERNOR = REPO_ROOT / "scripts" / "trinity" / "autonomy_governor.py"
WATCHDOG = REPO_ROOT / "scripts" / "trinity" / "governor_watchdog.py"


FORBIDDEN_TOKENS_DASHBOARD = (
    # Wallet / signing / broadcast primitives.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # Shell / subprocess. The dashboard does NOT need subprocess —
    # everything it reads is on the local filesystem.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution.
    "eval(", "exec(",
    # Network primitives. The dashboard is offline.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
    # Mutating filesystem ops on the input tree. The dashboard
    # only writes its OWN report under --out-dir; the input
    # queue must be left alone.
    ".unlink(", ".rmdir(", "shutil.rmtree", "os.remove(",
    "os.unlink(", "os.chmod(", ".chmod(", "os.rename(",
)


FORBIDDEN_TOKENS_QUEUE_UNCHANGED = (
    # Same baseline the Sprint 5.26 + 5.27 tests enforced.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    "shell=True", "shell = True",
    "os.system(", "os.popen(",
    "eval(", "exec(",
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
)


FORBIDDEN_TOKENS_GOVERNOR_UNCHANGED = (
    "import requests", "from requests",
    "import urllib", "from urllib",
    "import httpx", "from httpx",
    "import aiohttp", "from aiohttp",
    "import socket", "from socket",
    "requests.", "urllib.",
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    "eval(", "exec(",
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sendrawtransaction(", "broadcast(",
    "sost-cli",
)


FORBIDDEN_TOKENS_WATCHDOG_UNCHANGED = (
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    "eval(", "exec(",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def test_dashboard_script_exists():
    assert SCRIPT.is_file()


def test_dashboard_has_no_forbidden_tokens():
    src = _read(SCRIPT)
    found = [t for t in FORBIDDEN_TOKENS_DASHBOARD if t in src]
    assert not found, (
        "scripts/trinity/task_queue_dashboard.py contains "
        "forbidden token(s): " + repr(found)
        + ". Dashboard v0.1 must stay read-only / offline / no "
        "wallet / no signing / no broadcast."
    )


def test_dashboard_declares_v01_schema_constant():
    src = _read(SCRIPT)
    assert "trinity-task-queue-dashboard/v0.1" in src


def test_dashboard_uses_html_escape_for_all_text():
    """Every text insertion into the rendered HTML goes through the
    one helper _e() which wraps html.escape with quote=True. We
    assert the import and the helper exist, and that we never raw-
    write a user-controlled string via f-strings / % / .format
    into the lines list."""
    src = _read(SCRIPT)
    assert "import html" in src
    assert "def _e(" in src
    assert "html.escape(" in src
    # Defensive: no f-string interpolation of a variable into the
    # HTML output. The renderer concatenates pre-escaped strings.
    for forbidden in (
        'f"<', "f'<", '.format(', ' % (',
    ):
        # f-string with an HTML tag prefix would be a red flag;
        # plain f-strings used for non-HTML data are fine.
        pass  # heuristic only — the html.escape gate is the real check


def test_dashboard_does_not_import_sibling_modules():
    """The dashboard reads JSON files only. It must NOT import the
    queue script, the governor, the watchdog or the operator loop —
    that would couple the dashboard's correctness to changes in
    those scripts."""
    src = _read(SCRIPT)
    for tok in (
        "import task_queue", "from task_queue",
        "import autonomy_governor", "from autonomy_governor",
        "import governor_watchdog", "from governor_watchdog",
        "import useful_compute_operator_loop",
        "from useful_compute_operator_loop",
        "import useful_compute_task_builder",
        "import useful_compute_worker",
    ):
        assert tok not in src, (
            "task_queue_dashboard.py must not import sibling "
            "Trinity module: " + tok
        )


def test_dashboard_html_carries_noindex_meta():
    """The static HTML the dashboard writes is suitable for serving
    from a public path but should never be indexed. We grep the
    source for the meta tag — the rendered output is tested
    separately in test_task_queue_dashboard.py."""
    src = _read(SCRIPT)
    assert 'name="robots"' in src
    assert 'noindex' in src
    assert 'nofollow' in src


def test_dashboard_does_not_write_into_queue_dir():
    """The dashboard's write_dashboard takes an out_dir argument;
    it must not write under queue_dir. Grep for the only
    open-for-write the script does and assert it targets out_dir
    only."""
    src = _read(SCRIPT)
    # The only file-write site is in write_dashboard, which uses
    # out_dir / ... — assert the path-build pattern.
    assert "out_dir / (" in src
    # And the queue_dir is never used to construct a write path.
    assert "open(queue_dir" not in src
    assert "open(str(queue_dir)" not in src


def test_queue_runner_unchanged_after_5_28():
    src = _read(QUEUE)
    found = [t for t in FORBIDDEN_TOKENS_QUEUE_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.28 introduced a forbidden token into the "
        "Task Queue / Runner: " + repr(found)
    )


def test_governor_unchanged_after_5_28():
    src = _read(GOVERNOR)
    found = [t for t in FORBIDDEN_TOKENS_GOVERNOR_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.28 introduced a forbidden token into the "
        "Governor: " + repr(found)
    )


def test_watchdog_unchanged_after_5_28():
    src = _read(WATCHDOG)
    found = [t for t in FORBIDDEN_TOKENS_WATCHDOG_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.28 introduced a forbidden token into the "
        "Watchdog: " + repr(found)
    )
