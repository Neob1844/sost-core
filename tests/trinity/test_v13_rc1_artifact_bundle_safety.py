"""Static safety surface for v13_rc1_artifact_bundle.py.

The bundler is NOT allowed to:
  - shell=True
  - touch wallets, keys, sign, broadcast
  - call any network endpoint, GitHub API, Ethereum endpoint
  - upload / publish / release
  - mutate git state (push / merge / tag / commit / add / reset / checkout)
  - use subprocess at all (hashlib + shutil + tarfile only)
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_rc1_artifact_bundle.py"
SCHEMA_PATH = (
    REPO_ROOT / "schemas" / "trinity"
    / "v13_rc1_artifact_bundle_manifest.schema.json"
)


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
    "privkey", "private_key_hex",
    # LLM clients.
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
    # Ethereum / L1 deploy.
    "web3.", "from web3", "import web3",
    "etherscan.io",
    "infura.io",
    "alchemy.com",
    "ETHERSCAN_API_KEY",
    "deploy_contract",
    "send_transaction",
    # Subprocess (the bundler must NOT shell out at all).
    "import subprocess", "from subprocess", "subprocess.",
    # Release upload (function-name form).
    "upload_release(",
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
    # git itself: the bundler must not invoke git at all.
    '"git"', "'git'",
)


def _read():
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT.is_file()


def test_schema_exists():
    assert SCHEMA_PATH.is_file()


def test_no_forbidden_tokens():
    src = _read()
    found = [t for t in FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "v13_rc1_artifact_bundle.py contains forbidden token(s): "
        + repr(found)
    )


def test_no_destructive_git_invocations():
    src = _read()
    found = [t for t in FORBIDDEN_GIT_INVOCATIONS if t in src]
    assert not found, (
        "v13_rc1_artifact_bundle.py contains forbidden git argv "
        "literal(s): " + repr(found)
    )


def test_no_sibling_trinity_imports():
    """The bundler must not import any sibling Trinity module."""
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
        "import v13_readiness_check",
        "from v13_readiness_check",
        "import v13_release_candidate_check",
        "from v13_release_candidate_check",
        "import v13_binary_preflight",
        "from v13_binary_preflight",
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
            "v13_rc1_artifact_bundle must not import: " + tok
        )


def test_no_html_or_js_in_markdown_path():
    src = _read()
    assert "<script" not in src
    assert "javascript:" not in src
    assert "<html" not in src
    assert "<style" not in src
    assert "import html" not in src
    assert "from html" not in src
    assert "html.escape" not in src


def test_declares_v01_schema_constants():
    src = _read()
    assert "trinity-v13-rc1-artifact-bundle-manifest/v0.1" in src
    assert "trinity-v13-binary-preflight-report/v0.1" in src


def test_safety_flag_names_present_in_source():
    src = _read()
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_release_upload",
        "no_network_required",
        "no_auto_restart",
        "no_subprocess",
        "no_shell_true",
        "no_github_api",
        "no_ethereum_deploy",
    ):
        assert flag in src, "safety flag missing in source: " + flag


def test_uses_only_safe_stdlib_for_io():
    """The bundler must use ONLY hashlib, shutil and tarfile (plus
    json / os / sys / argparse / pathlib / datetime / re / io) for
    file IO and packaging. No urllib, no requests, no subprocess."""
    src = _read()
    assert "import hashlib" in src
    assert "import shutil" in src
    assert "import tarfile" in src
    # And the forbidden ones are already checked above.


def test_no_url_strings_in_source():
    """Defensive: the script should not embed any http(s):// URL.
    All distribution is local."""
    src = _read()
    import re
    urls = re.findall(r"https?://[a-zA-Z0-9._/-]+", src)
    assert not urls, "v13_rc1_artifact_bundle should contain no URLs; found: " + repr(urls)
