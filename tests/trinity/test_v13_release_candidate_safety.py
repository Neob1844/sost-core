"""Static safety surface for v13_release_candidate_check.py.

The script is allowed NO wallet access, NO private key access, NO
signing, NO broadcast, NO network calls, NO GitHub API, NO
shell-string subprocess, NO destructive git verb, NO push/merge/tag,
NO subprocess at all (not even argv-list), NO Ethereum/L1 deploy."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "v13_release_candidate_check.py"
CONFIG = REPO_ROOT / "config" / "v13_release_candidate.json"
PUBLIC = REPO_ROOT / "website" / "api" / "v13_release_candidate.json"


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
    # Wallet / signing / broadcast tokens.
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "privkey", "private_key_hex",
    # LLM clients.
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
    # Ethereum / L1 deploy primitives.
    "web3.", "from web3", "import web3",
    "etherscan.io",
    "infura.io",
    "alchemy.com",
    "ETHERSCAN_API_KEY",
    "deploy_contract",
    "send_transaction",
    # Subprocess (the script must not shell out at all).
    "import subprocess", "from subprocess", "subprocess.",
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


def test_public_mirror_exists():
    assert PUBLIC.is_file()


def test_no_forbidden_tokens():
    src = _read()
    found = [t for t in FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "v13_release_candidate_check.py contains forbidden "
        "token(s): " + repr(found)
    )


def test_no_destructive_git_invocations():
    src = _read()
    found = [t for t in FORBIDDEN_GIT_INVOCATIONS if t in src]
    assert not found, (
        "v13_release_candidate_check.py contains destructive git "
        "argv literal(s): " + repr(found)
    )


def test_no_sibling_trinity_imports():
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
            "v13_release_candidate_check must not import: " + tok
        )


def test_no_html_or_js_in_markdown_path():
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
    assert "trinity-v13-release-candidate-report/v0.1" in src
    assert "sost-v13-release-candidate/v0.1" in src
    assert "sost-v13-release-candidate-public/v0.1" in src


def test_safety_flag_names_present_in_source():
    src = _read()
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
        "no_github_api",
        "no_shell_true",
        "no_destructive_git",
        "no_auto_push_merge_tag",
        "no_subprocess",
        "no_ethereum_deploy",
    ):
        assert flag in src, "safety flag missing in source: " + flag


def test_config_safety_flags_const_true():
    import json
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
        "no_auto_restart",
        "no_consensus_auto_toggle",
    ):
        assert cfg["safety"][flag] is True, "config flag: " + flag


def test_public_mirror_safety_flags_const_true():
    import json
    pub = json.loads(PUBLIC.read_text(encoding="utf-8"))
    for flag in (
        "no_wallet_access",
        "no_private_key_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
        "no_auto_restart",
        "no_consensus_auto_toggle",
    ):
        assert pub["safety"][flag] is True, "public flag: " + flag


def test_public_mirror_carries_no_evidence_keywords():
    """The public mirror must NOT leak internal evidence_keyword
    or detailed reasons. Those are private to the in-repo
    config."""
    import json
    pub = json.loads(PUBLIC.read_text(encoding="utf-8"))
    # The public mirror MUST not expose a list-of-objects for
    # confirmed_items (only the safe IDs).
    assert "confirmed_items_ids" in pub
    assert isinstance(pub["confirmed_items_ids"], list)
    for entry in pub["confirmed_items_ids"]:
        assert isinstance(entry, str), (
            "public confirmed_items_ids must be a flat list of "
            "strings; found " + repr(type(entry))
        )
    # Similarly for fallback.
    assert "fallback_v15_items_ids" in pub
    assert isinstance(pub["fallback_v15_items_ids"], list)
    for entry in pub["fallback_v15_items_ids"]:
        assert isinstance(entry, str)
    # The public mirror MUST not contain any "evidence_keyword"
    # field anywhere.
    blob = json.dumps(pub)
    assert "evidence_keyword" not in blob, (
        "public mirror leaks evidence_keyword (should be private "
        "to the in-repo config)"
    )


def test_public_mirror_no_tmp_paths():
    import json
    pub_text = PUBLIC.read_text(encoding="utf-8")
    assert "/tmp/" not in pub_text, "public mirror leaks /tmp path"
