"""Static safety surface for Sprint 5.35 worker_onboarding.py."""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "worker_onboarding.py"


FORBIDDEN_TOKENS = (
    # Network primitives. The onboarding script is offline.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
    "http.client.HTTPConnection",
    # Shell / subprocess. The script reads no files outside its
    # own write target.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution.
    "eval(", "exec(",
    # Wallet / signing / broadcast tokens. The script must NOT
    # create or carry any of these.
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
        "worker_onboarding.py contains forbidden token(s): "
        + repr(found)
    )


def test_does_not_import_sibling_modules():
    """The onboarding script must not import the worker, the
    backends module, the task_queue, the operator_loop, etc.
    Coupling would defeat the 'distributable to other hosts'
    intent."""
    src = _read()
    for tok in (
        "import useful_compute_worker",
        "from useful_compute_worker",
        "import useful_compute_backends",
        "from useful_compute_backends",
        "import task_queue",
        "from task_queue",
        "import autonomy_governor",
        "import governor_watchdog",
    ):
        assert tok not in src, (
            "worker_onboarding must not import: " + tok
        )


def test_declares_v01_schema_constant():
    src = _read()
    assert "trinity-worker-onboarding-bundle/v0.1" in src


def test_supported_backends_constant_present():
    src = _read()
    assert "SUPPORTED_BACKENDS" in src
    # Must include the Sprint 5.32 real_backend so the bundle
    # advertises the actual capability set.
    assert "local_materials_engine_v01" in src


def test_safety_status_all_const_true_in_source():
    """The script's safety_status block must hardcode every flag
    to True (never False, never operator-controllable). A future
    refactor that turns one of these into a parameter would let
    a misconfigured bundle silently advertise no_wallet_required
    = False — catch it here at lint time."""
    src = _read()
    for tok in (
        '"no_wallet_required":           True,',
        '"no_private_key_required":      True,',
        '"no_seed_phrase_required":      True,',
        '"no_broadcast_capability":      True,',
        '"no_network_in_worker_process": True,',
        '"bundle_carries_no_secrets":    True,',
    ):
        assert tok in src, "safety_status flag must be const-True: " + tok


def test_no_secret_substring_helper_removed_or_neutered():
    """The defensive _assert_no_secret_substrings helper was
    removed in v0.1 (false-positive risk on the safety_status
    field names themselves). If it ever comes back without
    excluding the safety_status keys, this test should fail."""
    src = _read()
    # We allow the comment that explains why it was removed.
    if "_assert_no_secret_substrings" in src:
        # If it's there, it must NOT be invoked from write_bundle.
        assert "_assert_no_secret_substrings(bundle)" not in src
