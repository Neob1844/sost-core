"""Static safety surface for Sprint 5.34 Materials Project cache.

Backend file gained the cache loader + resolver. This file
enforces that the cache addition did NOT bring any network /
shell / LLM / wallet token into the backends module, and that the
data file itself contains no secret material.
"""
from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKENDS = REPO_ROOT / "scripts" / "trinity" / "useful_compute_backends.py"
CACHE_DATA = (
    REPO_ROOT / "data" / "trinity"
    / "materials_project_cache_v01.json"
)


FORBIDDEN_NEW_AFTER_5_34 = (
    # Network primitives.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "import httpx", "from httpx",
    "import aiohttp", "from aiohttp",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    # Shell.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution.
    "eval(", "exec(",
    # Wallet / signing / broadcast tokens.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # LLM clients.
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def test_backends_no_new_forbidden_tokens_after_5_34():
    src = _read(BACKENDS)
    found = [t for t in FORBIDDEN_NEW_AFTER_5_34 if t in src]
    assert not found, (
        "Sprint 5.34 cache loader introduced a forbidden token "
        "into scripts/trinity/useful_compute_backends.py: "
        + repr(found)
    )


def test_cache_loader_uses_lazy_module_state():
    src = _read(BACKENDS)
    assert "_materials_project_cache_state" in src
    assert "def _load_materials_project_cache" in src
    assert "def _verify_cache_hashes" in src
    assert "def _resolve_material_in_cache" in src


def test_cache_data_contains_no_private_key_like_blob():
    raw = _read(CACHE_DATA)
    # Heuristic: a raw 64-hex blob OUTSIDE the declared sha256
    # fields would be suspicious. The legitimate 64-hex appearances
    # are only the property_hash_sha256, record_sha256, cache_sha256
    # fields. We allow those by checking they only appear in the
    # expected JSON keys.
    import json
    obj = json.loads(raw)
    legitimate_hashes = set()
    legitimate_hashes.add(obj["cache_sha256"])
    for r in obj["records"]:
        legitimate_hashes.add(r["property_hash_sha256"])
        legitimate_hashes.add(r["record_sha256"])
    # Find every 64-hex substring in the file.
    found = re.findall(r"[0-9a-f]{64}", raw)
    for h in found:
        assert h in legitimate_hashes, (
            "unexpected 64-hex blob in cache: " + h
        )


def test_cache_data_no_sost_address():
    raw = _read(CACHE_DATA)
    assert not re.search(r"sost1[0-9a-f]{40}", raw), (
        "cache appears to contain a real SOST address"
    )


def test_cache_data_no_obvious_wallet_secret():
    raw = _read(CACHE_DATA).lower()
    # Refuse anything that looks like a wallet / mnemonic blob.
    for tok in (
        "private_key", "seed_phrase", "mnemonic", "passphrase",
        "wallet.json", "xprv",
    ):
        assert tok not in raw, (
            "cache data file contains forbidden token: " + repr(tok)
        )


def test_cache_source_notice_says_local():
    """The cache must explicitly tell the reader it is LOCAL +
    NOT a live fetch. A future PR that drops the disclaimer is a
    misrepresentation risk."""
    import json
    obj = json.loads(_read(CACHE_DATA))
    notice = obj["cache_source_notice"].lower()
    assert "local" in notice or "not a live" in notice
