"""Static safety surface for Sprint 5.40 sprint_release_runner.py.

The release runner is allowed to use ``subprocess`` (for git read
commands + pytest) but ONLY with argv-list calls and NEVER with
``shell=True``. It must NEVER push, merge, tag, or otherwise
mutate remote / shared state. It must NEVER touch a wallet, key,
or broadcast surface. It must NEVER call the GitHub API or any
network.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "sprint_release_runner.py"


# Hard prohibitions — these must NEVER appear in source.
FORBIDDEN_TOKENS = (
    # Shell escape.
    "shell=True", "shell = True",
    "os.system(", "os.popen(",
    # Dynamic code execution.
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
    # GitHub API / token-flavoured.
    "api.github.com",
    "GITHUB_TOKEN",
    "X-GitHub-",
    "import github", "from github",
    "PyGithub",
    # Wallet / signing / broadcast tokens.
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    "privkey", "private_key_hex",
    # LLM clients.
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
)


# Destructive git verbs MUST not appear in source. The runner is
# read-only on git state.
FORBIDDEN_GIT_INVOCATIONS = (
    # argv-list flavours that would mutate state.
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


def test_no_forbidden_tokens():
    src = _read()
    found = [t for t in FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "sprint_release_runner.py contains forbidden token(s): "
        + repr(found)
    )


def test_no_destructive_git_invocations():
    src = _read()
    found = [t for t in FORBIDDEN_GIT_INVOCATIONS if t in src]
    assert not found, (
        "sprint_release_runner.py contains destructive git "
        "argv literal(s) (this script must be git-read-only): "
        + repr(found)
    )


def test_allowed_git_verbs_constant_present():
    src = _read()
    assert "ALLOWED_GIT_VERBS" in src
    # All seven explicit allow-list verbs must be listed.
    for verb in (
        '"rev-parse"', '"status"', '"diff"', '"log"',
        '"branch"', '"ls-files"', '"rev-list"',
    ):
        assert verb in src, "missing allow-list verb: " + verb


def test_subprocess_uses_argv_list_only():
    """The script calls subprocess only with argv lists. There is
    no string-form ``subprocess.run("git status")``."""
    src = _read()
    # Any subprocess.run(<string-literal>) is forbidden.
    import re
    for m in re.finditer(r"subprocess\.run\s*\(", src):
        # Look at the next non-whitespace char; should be '[' (argv list)
        # or '\n' followed by '[' on the next line, or a bareword for
        # a list variable.
        rest = src[m.end():m.end() + 4]
        # Reject quote-prefixed first arg.
        first = rest.lstrip()
        assert not first.startswith(('"', "'")), (
            "subprocess.run with string-form command is forbidden: "
            + src[m.start():m.start() + 80]
        )


def test_declares_v01_schema_constant():
    src = _read()
    assert "trinity-sprint-release-report/v0.1" in src


def test_known_artifact_schemas_constant_present():
    src = _read()
    assert "KNOWN_ARTIFACT_SCHEMAS" in src
    for schema_id in (
        "trinity-task-queue-autopilot-report/v0.1",
        "trinity-task-queue-dashboard/v0.1",
        "trinity-daily-report/v0.1",
        "trinity-worker-trial-pack-manifest/v0.1",
    ):
        assert schema_id in src, "missing artifact schema: " + schema_id


def test_safety_flags_constant_in_source():
    src = _read()
    for flag in (
        "no_git_push",
        "no_git_merge",
        "no_git_tag",
        "no_wallet_access",
        "no_signing",
        "no_broadcast",
        "no_network_required",
    ):
        assert flag in src, "safety flag missing in source: " + flag


def test_no_sibling_trinity_imports():
    """The release runner is a pure observer; it must not import
    any other Trinity Python module. Coupling would defeat the
    intent (one-shot preflight, no runtime hooks)."""
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
            "sprint_release_runner must not import: " + tok
        )
