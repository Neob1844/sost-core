"""Static safety surface for v13_binary_preflight.py.

This script IS allowed to use subprocess (argv-list only) for:
  - git rev-parse / status / diff / log / branch / ls-files / rev-list / merge-base
  - python -m pytest (when --run-tests is passed)
  - ctest -R <name>  (when --run-ctest is passed)

It is NOT allowed to:
  - shell=True
  - touch wallets, keys, sign, broadcast
  - call any network endpoint, GitHub API, Ethereum endpoint
  - upload / publish / release
  - invoke cmake or make (operator builds manually)
  - mutate git state (push / merge / tag / commit / add / reset / checkout)
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_binary_preflight.py"
CONFIG = REPO_ROOT / "config" / "v13_binary_preflight.json"


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
    # Make / cmake (operator builds manually).
    "subprocess.run(['cmake'",
    "subprocess.run([\"cmake\"",
    "subprocess.Popen(['cmake'",
    "subprocess.Popen([\"cmake\"",
    "subprocess.run(['make'",
    "subprocess.run([\"make\"",
    "subprocess.Popen(['make'",
    "subprocess.Popen([\"make\"",
    # Release upload (function-name form — the safety flag
    # "no_release_upload" is a documented anti-pattern, allowed).
    "upload_release(",
    "sha256sum ", "openssl dgst",
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
        "v13_binary_preflight.py contains forbidden token(s): "
        + repr(found)
    )


def test_no_destructive_git_invocations():
    src = _read()
    found = [t for t in FORBIDDEN_GIT_INVOCATIONS if t in src]
    assert not found, (
        "v13_binary_preflight.py contains destructive git argv "
        "literal(s): " + repr(found)
    )


def test_allowed_git_verbs_constant_present():
    src = _read()
    assert "ALLOWED_GIT_VERBS" in src
    for verb in (
        '"rev-parse"', '"status"', '"diff"', '"log"',
        '"branch"', '"ls-files"', '"rev-list"', '"merge-base"',
    ):
        assert verb in src, "missing allow-list verb: " + verb


def test_subprocess_uses_argv_list_only():
    """Any subprocess.run( with a string-form first arg is
    forbidden. The script must always pass an argv list."""
    src = _read()
    import re
    for m in re.finditer(r"subprocess\.(run|Popen)\s*\(", src):
        rest = src[m.end():m.end() + 6].lstrip()
        assert not rest.startswith(('"', "'")), (
            "subprocess with string-form command is forbidden: "
            + src[m.start():m.start() + 80]
        )


def test_declares_v01_schemas():
    src = _read()
    assert "trinity-v13-binary-preflight-report/v0.1" in src
    assert "sost-v13-binary-preflight/v0.1" in src


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
        "no_ethereum_deploy",
        "no_destructive_git",
        "no_shell_true",
        "no_make_invocation",
        "no_cmake_invocation",
    ):
        assert flag in src, "safety flag missing in source: " + flag


def test_imports_only_named_siblings():
    """The preflight may import v13_readiness_check and
    v13_release_candidate_check (it explicitly does so via
    importlib + a hardcoded allow-list). Any OTHER sibling import
    would be a coupling we want to know about."""
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
            "v13_binary_preflight must not import: " + tok
        )


def test_no_html_in_markdown_path():
    src = _read()
    assert "<script" not in src
    assert "javascript:" not in src
    assert "<html" not in src
    assert "<style" not in src
    assert "import html" not in src
    assert "from html" not in src
    assert "html.escape" not in src


def test_config_safety_flags_const_true():
    import json
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_release_upload",
        "no_network_required",
        "no_auto_restart",
        "no_ethereum_deploy",
        "no_destructive_git",
        "no_shell_true",
        "no_make_invocation",
        "no_cmake_invocation",
    ):
        assert cfg["safety"][flag] is True, "config flag: " + flag


def test_config_preflight_does_not_run_build_tools():
    import json
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert cfg["preflight_does_NOT_run_cmake"] is True
    assert cfg["preflight_does_NOT_run_make"]  is True
    assert cfg["preflight_does_NOT_sign"]      is True
    assert cfg["preflight_does_NOT_publish"]   is True
    assert cfg["operator_must_build_manually"] is True


def test_no_url_strings_in_source():
    """Defensive: the script should not contain any http(s):// URL
    in source. It does not fetch anything from the network."""
    src = _read()
    import re
    urls = re.findall(r"https?://[a-zA-Z0-9._/-]+", src)
    assert not urls, "v13_binary_preflight should contain no URLs; found: " + repr(urls)
