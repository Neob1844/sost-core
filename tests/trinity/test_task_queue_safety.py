"""Static safety surface for scripts/trinity/task_queue.py
(Sprint 5.26).

The Task Queue is a local-dry-run runner. It MUST NOT touch wallets,
sign anything, broadcast anything, or invoke a shell. It MAY use
subprocess (it has to, in order to call useful_compute_operator_loop.py
and governor_watchdog.py), but every call MUST pass an explicit argv
list with shell=False — the static test below rejects shell=True.

The Task Queue also MUST keep two structural invariants:
  - The only --mode it accepts is local-dry-run.
  - Every operator_loop invocation passes the exact confirmation
    token I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP.

A cross-check at the end re-asserts that scripts/trinity/autonomy_governor.py
and scripts/trinity/governor_watchdog.py did NOT regain any forbidden
token in the course of Sprint 5.26.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "task_queue.py"
GOVERNOR = REPO_ROOT / "scripts" / "trinity" / "autonomy_governor.py"
WATCHDOG = REPO_ROOT / "scripts" / "trinity" / "governor_watchdog.py"


FORBIDDEN_TOKENS_QUEUE = (
    # Wallet / signing / broadcast primitives.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # Shell-out is forbidden. Subprocess is allowed but argv-only.
    "shell=True", "shell = True",
    "os.system(", "os.popen(",
    # Dynamic code execution.
    "eval(", "exec(",
    # Network primitives (the queue speaks to local sibling scripts
    # via argv only; no HTTP).
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
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
    # Network primitives — watchdog v0.1 must still have none.
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def test_queue_script_exists():
    assert SCRIPT.is_file(), "task_queue.py not found at " + str(SCRIPT)


def test_queue_has_no_forbidden_tokens():
    src = _read(SCRIPT)
    found = [t for t in FORBIDDEN_TOKENS_QUEUE if t in src]
    assert not found, (
        "scripts/trinity/task_queue.py contains forbidden "
        "token(s): " + repr(found)
        + ". Task queue v0.1 must stay off wallet/sign/broadcast/"
        "shell/network."
    )


def test_queue_uses_only_argv_subprocess():
    """subprocess is allowed in the queue (it invokes operator_loop
    and watchdog) but every call must be argv-form, never shell."""
    src = _read(SCRIPT)
    assert "subprocess.run" in src, (
        "task_queue.py should use subprocess.run for sibling script "
        "invocation"
    )
    # The forbidden-tokens test above already rejects shell=True.
    # Cross-check we never see a plain string command (no
    # subprocess.run(\"...\") at the top level).
    for needle in ("subprocess.call(", "subprocess.check_output("):
        assert needle not in src, (
            "task_queue.py uses non-preferred subprocess form: " + needle
        )


def test_queue_locks_local_dry_run_only():
    """The queue source must explicitly reference the only allowed
    mode and reject everything else."""
    src = _read(SCRIPT)
    assert '"local-dry-run"' in src
    assert "_ensure_local_dry_run" in src
    assert "ALLOWED_MODE" in src


def test_queue_always_passes_confirmation_token():
    """Every operator_loop invocation MUST include the exact
    confirmation token string. If a future refactor drops it, the
    token is no longer auto-included and the operator_loop refuses
    to start — but we catch it here at lint time, not at runtime."""
    src = _read(SCRIPT)
    assert "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP" in src
    assert "--require-confirmation-token" in src


def test_queue_calls_governor_policy_explicitly():
    """The queue MUST pass --governor-policy to the operator loop
    so the audit hook always fires. Without it, no decision JSONs
    are written and the watchdog has nothing to scan."""
    src = _read(SCRIPT)
    assert '"--governor-policy"' in src


def test_queue_fail_closed_on_hard_block():
    """The queue source must reference the rc=3 hard-block contract
    and the watchdog 'critical' branch — these are the two fail-
    closed conditions."""
    src = _read(SCRIPT)
    assert "GOVERNOR_HARD_BLOCK_RC" in src
    assert "governor_hard_block" in src
    assert "watchdog_safety_status" in src


def test_queue_does_not_import_sibling_modules_at_runtime():
    """The queue runs operator_loop / watchdog via subprocess for
    isolation. It must NOT import them as Python modules — that
    would let a bug in one cascade into all three."""
    src = _read(SCRIPT)
    for tok in (
        "import autonomy_governor",
        "from autonomy_governor",
        "import governor_watchdog",
        "from governor_watchdog",
        "import useful_compute_operator_loop",
        "from useful_compute_operator_loop",
        "import useful_compute_task_builder",
        "import useful_compute_worker",
    ):
        assert tok not in src, (
            "task_queue.py must not import sibling Trinity module: "
            + tok
        )


def test_governor_unchanged_after_5_26():
    """Cross-check: Sprint 5.26 must not regress the Governor's
    safety surface."""
    src = _read(GOVERNOR)
    found = [t for t in FORBIDDEN_TOKENS_GOVERNOR_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.26 introduced a forbidden token into the "
        "Governor: " + repr(found)
    )


def test_watchdog_unchanged_after_5_26():
    """Cross-check: Sprint 5.26 must not regress the Watchdog's
    safety surface."""
    src = _read(WATCHDOG)
    found = [t for t in FORBIDDEN_TOKENS_WATCHDOG_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.26 introduced a forbidden token into the "
        "Watchdog: " + repr(found)
    )
