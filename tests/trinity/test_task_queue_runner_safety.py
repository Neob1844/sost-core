"""Static safety surface for the Sprint 5.27 Task Queue Runner.

The runner extends scripts/trinity/task_queue.py with a new
``run-batch`` subcommand. The new code MUST inherit every safety
invariant from Sprint 5.26 — no shell, no wallet, no signing, no
broadcasting, no network, no sibling-module imports — and MUST NOT
weaken the existing static-safety tests for the Governor, the
Watchdog or the prior Task Queue surface.

This file re-runs the task_queue forbidden-tokens grep against the
extended file, asserts the new run-batch CLI is reachable, asserts
the runner's bounded-loop / mode-lock / fail-closed surfaces are
still wired, and cross-checks the three sibling safety surfaces
(Governor / Watchdog / Task Queue baseline) for zero regression.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "task_queue.py"
GOVERNOR = REPO_ROOT / "scripts" / "trinity" / "autonomy_governor.py"
WATCHDOG = REPO_ROOT / "scripts" / "trinity" / "governor_watchdog.py"


# Same forbidden set the Sprint 5.26 safety test enforced. The
# runner code lives in the same file, so any regression here
# would fail this test even if the 5.26 file had been split.
FORBIDDEN_TOKENS_RUNNER = (
    # Wallet / signing / broadcast primitives.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # Shell-out is forbidden. Subprocess is allowed (argv only).
    "shell=True", "shell = True",
    "os.system(", "os.popen(",
    # Dynamic code execution.
    "eval(", "exec(",
    # Network primitives. The runner does not talk to the network;
    # it invokes sibling scripts via argv subprocess only.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
)


# Same enforcement as the 5.23 / 5.25 / 5.26 cross-checks: the
# Governor's static safety surface must not regress when we extend
# task_queue.py in 5.27.
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


def test_runner_lives_inside_task_queue_script():
    assert SCRIPT.is_file()


def test_runner_has_no_forbidden_tokens():
    src = _read(SCRIPT)
    found = [t for t in FORBIDDEN_TOKENS_RUNNER if t in src]
    assert not found, (
        "scripts/trinity/task_queue.py contains forbidden "
        "token(s) after the Sprint 5.27 runner extension: "
        + repr(found)
    )


def test_runner_subcommand_is_wired():
    src = _read(SCRIPT)
    assert '"run-batch"' in src
    assert "def run_batch(" in src
    assert "def _cmd_run_batch(" in src
    assert '"run-batch": _cmd_run_batch' in src


def test_runner_bounds_are_hardcoded():
    """The runner must keep its bounds as named constants — not as
    inline magic numbers a refactor could quietly bump. If a future
    PR widens 50 to 5000, this test fires."""
    src = _read(SCRIPT)
    assert "RUNNER_MIN_BATCH = 1" in src
    assert "RUNNER_MAX_BATCH = 50" in src
    assert "RUNNER_MAX_SLEEP_SECONDS = 3600" in src


def test_runner_reuses_run_once_not_duplicated():
    """The runner MUST delegate to run_once() — it must not copy
    or shadow the operator_loop / watchdog plumbing. We grep for
    the delegating call and reject any sign of a duplicate
    operator_loop / watchdog dispatch path elsewhere in the file."""
    src = _read(SCRIPT)
    assert "result = run_once(queue_dir)" in src
    # _run_operator_loop and _run_watchdog must each be referenced
    # exactly once outside their definitions — from run_once.
    # (Indirect proof: they are not pasted again under run_batch.)
    occurrences = src.count("_run_operator_loop(")
    assert occurrences == 2, (
        "_run_operator_loop must be defined once + called once; "
        "found " + str(occurrences) + " occurrences (suggests "
        "duplication into run_batch)"
    )
    occurrences_wd = src.count("_run_watchdog(")
    assert occurrences_wd == 2, (
        "_run_watchdog must be defined once + called once; found "
        + str(occurrences_wd) + " occurrences"
    )


def test_runner_locks_local_dry_run_for_batch_path():
    """run_batch must re-assert the mode lock even though run_once
    does it. Belt-and-braces against a future caller fanning a
    different mode into run_batch."""
    src = _read(SCRIPT)
    assert "_ensure_local_dry_run(ALLOWED_MODE)" in src


def test_runner_passes_safety_status_through_to_report():
    src = _read(SCRIPT)
    for tok in (
        '"safety_status"',
        '"ok"', '"warning"', '"failed"',
        "stop_on_failure",
    ):
        assert tok in src, (
            "runner is missing wiring for: " + tok
        )


def test_runner_does_not_import_sibling_modules():
    """The runner inherits the 5.26 rule: never import the operator
    loop, the watchdog, or the governor module — talk to them via
    argv subprocess only, for isolation."""
    src = _read(SCRIPT)
    for tok in (
        "import autonomy_governor", "from autonomy_governor",
        "import governor_watchdog", "from governor_watchdog",
        "import useful_compute_operator_loop",
        "from useful_compute_operator_loop",
        "import useful_compute_task_builder",
        "import useful_compute_worker",
    ):
        assert tok not in src, (
            "task_queue.py must not import sibling Trinity module: "
            + tok
        )


def test_governor_unchanged_after_5_27():
    src = _read(GOVERNOR)
    found = [t for t in FORBIDDEN_TOKENS_GOVERNOR_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.27 introduced a forbidden token into the "
        "Governor: " + repr(found)
    )


def test_watchdog_unchanged_after_5_27():
    src = _read(WATCHDOG)
    found = [t for t in FORBIDDEN_TOKENS_WATCHDOG_UNCHANGED if t in src]
    assert not found, (
        "Sprint 5.27 introduced a forbidden token into the "
        "Watchdog: " + repr(found)
    )
