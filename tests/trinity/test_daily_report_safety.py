"""Static safety surface for Sprint 5.39 trinity_daily_report.py."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "trinity_daily_report.py"


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
    # Shell / subprocess.
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
    # No HTML / no JS rendering.
    "<script", "javascript:",
    "<style", "<html",
)


def _read():
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT.is_file()


def test_no_forbidden_tokens():
    src = _read()
    found = [t for t in FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "trinity_daily_report.py contains forbidden token(s): "
        + repr(found)
    )


def test_declares_v01_schema_constant():
    src = _read()
    assert "trinity-daily-report/v0.1" in src


def test_safety_flags_constant_in_source():
    src = _read()
    for flag in (
        "no_wallet",
        "no_private_key",
        "no_signing",
        "no_broadcast",
        "no_autonomous_payment",
        "no_network",
    ):
        assert flag in src, "safety flag missing in source: " + flag


def test_does_not_import_sibling_modules():
    """The daily report is a pure consumer of dashboard JSON +
    queue dir on-disk artifacts. It must not import any sibling
    Trinity module — that would couple it to runtime APIs."""
    src = _read()
    for tok in (
        "import useful_compute_worker",
        "from useful_compute_worker",
        "import useful_compute_backends",
        "from useful_compute_backends",
        "import useful_compute_operator_loop",
        "from useful_compute_operator_loop",
        "import task_queue",
        "from task_queue",
        "import task_queue_dashboard",
        "from task_queue_dashboard",
        "import task_queue_autopilot",
        "from task_queue_autopilot",
        "import autonomy_governor",
        "from autonomy_governor",
        "import governor_watchdog",
        "from governor_watchdog",
        "import payment_proposal",
        "from payment_proposal",
        "import payment_draft",
        "from payment_draft",
    ):
        assert tok not in src, (
            "trinity_daily_report must not import: " + tok
        )


def test_renders_markdown_only():
    """The report emits Markdown, never HTML. The renderer must
    not call html.escape, must not embed <html>, <script>, or
    inline CSS."""
    src = _read()
    assert "import html" not in src
    assert "from html" not in src
    assert "html.escape" not in src
