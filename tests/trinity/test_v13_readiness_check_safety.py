"""Static safety surface for v13_readiness_check.py.

The script is allowed NO wallet access, NO private key access, NO
signing, NO broadcast, NO network calls, NO GitHub API, NO shell-
string subprocess, NO destructive git verb, NO push/merge/tag.
It is allowed to use subprocess only if argv-list (it does not
currently use subprocess at all)."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_readiness_check.py"
CONFIG = REPO_ROOT / "config" / "v13_activation.json"


FORBIDDEN_TOKENS = (
    # Shell escape / dynamic execution.
    "shell=True", "shell = True",
    "os.system(", "os.popen(",
    "eval(", "exec(",
    # Network primitives.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "import httpx", "from httpx", "httpx.",
    "import aiohttp", "from aiohttp", "aiohttp.",
    "socket.socket(", "socket.create_connection(",
    "http.client.HTTPConnection",
    # GitHub API surface.
    "api.github.com",
    "GITHUB_TOKEN",
    "X-GitHub-",
    "import github", "from github",
    "PyGithub",
    # Wallet / signing / broadcast.
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    "privkey", "private_key_hex",
    # LLM clients.
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
)


# Destructive git verbs MUST not appear in source.
FORBIDDEN_GIT_INVOCATIONS = (
    '"push"', "'push'",
    '"merge"', "'merge'",
    '"tag"', "'tag'",
    '"reset"', "'reset'",
    '"checkout"', "'checkout'",
    '"rm"', "'rm'",
    '"clean"', "'clean'",
    '"commit"', "'commit'",
    '"add"', "'add'",
    '"stash"', "'stash'",
)


def _read():
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT.is_file()


def test_config_exists():
    assert CONFIG.is_file()


def test_no_forbidden_tokens():
    src = _read()
    found = [t for t in FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "v13_readiness_check.py contains forbidden token(s): "
        + repr(found)
    )


def test_no_destructive_git_invocations():
    src = _read()
    found = [t for t in FORBIDDEN_GIT_INVOCATIONS if t in src]
    assert not found, (
        "v13_readiness_check.py contains destructive git argv "
        "literal(s): " + repr(found)
    )


def test_no_sibling_trinity_imports():
    """The readiness check is a pure observer; it must not
    import any other Trinity Python module."""
    src = _read()
    forbidden = (
        "import useful_compute_worker",
        "from useful_compute_worker",
        "import useful_compute_backends",
        "from useful_compute_backends",
        "import task_queue",
        "from task_queue",
        "import task_queue_dashboard",
        "from task_queue_dashboard",
        "import task_queue_autopilot",
        "from task_queue_autopilot",
        "import trinity_daily_report",
        "from trinity_daily_report",
        "import worker_onboarding",
        "from worker_onboarding",
        "import worker_trial_pack",
        "from worker_trial_pack",
        "import sprint_release_runner",
        "from sprint_release_runner",
        "import autonomy_governor",
        "from autonomy_governor",
        "import governor_watchdog",
        "from governor_watchdog",
        "import payment_proposal",
        "from payment_proposal",
        "import payment_draft",
        "from payment_draft",
    )
    for tok in forbidden:
        assert tok not in src, (
            "v13_readiness_check must not import: " + tok
        )


def test_no_html_or_js_in_markdown_path():
    """The script emits Markdown only — no HTML / JS."""
    src = _read()
    assert "import html" not in src
    assert "from html" not in src
    assert "html.escape" not in src
    assert "<script" not in src
    assert "javascript:" not in src
    assert "<html" not in src
    assert "<style" not in src


def test_declares_v01_schema_constants():
    src = _read()
    assert "trinity-v13-readiness-report/v0.1" in src
    assert "trinity-v13-activation-config/v0.1" in src


def test_safety_flag_names_present_in_source():
    src = _read()
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_calls",
        "no_github_api",
        "no_shell_true",
        "no_destructive_git",
        "no_auto_push_merge_tag",
        "ntp_mandatory_post_v13",
        "half_enabled_items_forbidden",
    ):
        assert flag in src, "safety flag missing in source: " + flag


def test_config_safety_invariants_const_true():
    import json
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    s = cfg["safety_invariants"]["readiness_check_script"]
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_calls",
        "no_github_api",
        "no_shell_true",
        "no_destructive_git",
        "no_auto_push_merge_tag",
    ):
        assert s[flag] is True, "config flag: " + flag
    b = cfg["safety_invariants"]["beacon"]
    assert b["may_inform"] is True
    assert b["may_restart"] is False
    assert b["may_block"] is False
    assert b["may_change_consensus"] is False
    assert b["may_execute_commands"] is False


def test_no_subprocess_at_all():
    """The current implementation needs no subprocess. If a
    future refactor adds it, this test forces an explicit
    review."""
    src = _read()
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    assert "subprocess." not in src
