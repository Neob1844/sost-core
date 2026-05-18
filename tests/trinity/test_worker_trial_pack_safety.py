"""Static safety surface for Sprint 5.37 worker_trial_pack.py."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "worker_trial_pack.py"


FORBIDDEN_TOKENS = (
    # Network primitives. The pack builder is offline.
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
)


def _read():
    return SCRIPT.read_text(encoding="utf-8")


def test_script_exists():
    assert SCRIPT.is_file()


def test_no_forbidden_tokens():
    src = _read()
    found = [t for t in FORBIDDEN_TOKENS if t in src]
    assert not found, (
        "worker_trial_pack.py contains forbidden token(s): "
        + repr(found)
    )


def test_only_one_sibling_import_path():
    """The trial-pack builder may import useful_compute_backends to
    compute the expected hash. Any *other* sibling import is a
    coupling we want to know about — flag it at lint time."""
    src = _read()
    # Allowed: useful_compute_backends (and ONLY that) via dynamic
    # import (inside _compute_expected_hashes).
    forbidden_sibling_imports = (
        "import useful_compute_worker",
        "from useful_compute_worker",
        "import useful_compute_operator_loop",
        "from useful_compute_operator_loop",
        "import task_queue",
        "from task_queue",
        "import task_queue_dashboard",
        "from task_queue_dashboard",
        "import autonomy_governor",
        "from autonomy_governor",
        "import governor_watchdog",
        "from governor_watchdog",
    )
    for tok in forbidden_sibling_imports:
        assert tok not in src, (
            "worker_trial_pack must not import: " + tok
        )


def test_declares_v01_schemas():
    src = _read()
    assert "trinity-worker-trial-pack-manifest/v0.1" in src
    assert "trinity-worker-trial-pack-expected/v0.1" in src
    assert "trinity-worker-trial-pack-config/v0.1" in src


def test_safety_flags_constant_in_source():
    src = _read()
    for flag in (
        "no_wallet_required",
        "no_private_key_required",
        "no_seed_phrase_required",
        "no_broadcast_capability",
        "no_network_in_worker_process",
        "pack_carries_no_secrets",
    ):
        assert flag in src, "safety flag missing in source: " + flag


def test_payout_address_template_literal_present():
    src = _read()
    assert "<PAYOUT_ADDRESS_FOR_" in src


def test_validate_worker_id_present():
    src = _read()
    # The worker-id validator must reject non-[A-Za-z0-9._-] chars.
    assert "_validate_worker_id" in src


def test_validate_commit_present():
    src = _read()
    assert "_validate_commit" in src


def test_validate_tag_present():
    src = _read()
    assert "_validate_tag" in src
