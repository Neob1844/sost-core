"""Static safety surface for Sprint 5.38 task_queue_autopilot.py."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "task_queue_autopilot.py"


FORBIDDEN_TOKENS = (
    # Network primitives.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "import httpx", "from httpx", "httpx.",
    "import aiohttp", "from aiohttp", "aiohttp.",
    "socket.socket(", "socket.create_connection(",
    "http.client.HTTPConnection",
    # Shell / subprocess. The autopilot drives task_queue.run_batch
    # in-process — never via subprocess.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution.
    "eval(", "exec(",
    # Wallet / signing / broadcast tokens.
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # LLM clients.
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
)


def _read():
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT.is_file()


def test_no_forbidden_tokens():
    src = _read()
    found = [t for t in FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "task_queue_autopilot.py contains forbidden token(s): "
        + repr(found)
    )


def test_max_batches_cap_hardcoded():
    src = _read()
    assert "AUTOPILOT_MAX_BATCHES_CAP = 24" in src


def test_max_items_per_batch_cap_present():
    src = _read()
    assert "AUTOPILOT_MAX_ITEMS_PER_BATCH_CAP" in src


def test_declares_v01_schema_constant():
    src = _read()
    assert "trinity-task-queue-autopilot-report/v0.1" in src


def test_no_while_true_loop():
    """The autopilot must never spawn an unbounded loop. The
    primary safety mechanism is the explicit max-batches arg, but
    we also forbid the textual smell `while True` to catch a
    future refactor that might forget the bound."""
    src = _read()
    assert "while True" not in src


def test_imports_only_sibling_modules_via_known_helpers():
    """The autopilot is allowed to drive task_queue + dashboard
    in-process. Other sibling imports would be a coupling
    surprise."""
    src = _read()
    forbidden_sibling_imports = (
        "import useful_compute_worker",
        "from useful_compute_worker",
        "import useful_compute_operator_loop",
        "from useful_compute_operator_loop",
        "import useful_compute_backends",
        "from useful_compute_backends",
        "import autonomy_governor",
        "from autonomy_governor",
        "import governor_watchdog",
        "from governor_watchdog",
        "import payment_proposal",
        "from payment_proposal",
        "import payment_draft",
        "from payment_draft",
    )
    for tok in forbidden_sibling_imports:
        assert tok not in src, (
            "task_queue_autopilot must not import: " + tok
        )
