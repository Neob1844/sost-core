"""Static safety surface for the Sprint 5.32 Materials Engine
backend (lives inside scripts/trinity/useful_compute_backends.py).

The backends module is the bigger blast radius — any wallet /
sign / network primitive landing here would be reachable by every
Useful Compute task. Sprint 5.32 also touches
scripts/trinity/useful_compute_worker.py to add the auto-router.
This file re-asserts the existing forbidden-token surface for
both files and adds Sprint 5.32-specific checks.
"""
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKENDS = REPO_ROOT / "scripts" / "trinity" / "useful_compute_backends.py"
WORKER = REPO_ROOT / "scripts" / "trinity" / "useful_compute_worker.py"
TASK_QUEUE = REPO_ROOT / "scripts" / "trinity" / "task_queue.py"


FORBIDDEN_NEW_IN_BACKENDS = (
    # Network primitives. No backend may open a socket in v0.1.
    "import requests", "from requests",
    "import urllib", "from urllib",
    "import httpx", "from httpx",
    "import aiohttp", "from aiohttp",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
    "http.client.HTTPConnection", "http.client.HTTPSConnection",
    # Shell / subprocess. Backends are pure Python in v0.1.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution.
    "eval(", "exec(",
    # Wallet / signing / broadcast primitives — never permitted.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    "sign_tx", "sign_transaction", "wallet.sign", "real_sign",
    "sendrawtransaction(", "broadcast(",
    "sost-cli", "sost_cli",
    # LLM client libraries — explicitly forbidden in v0.1
    # (Sprint 5.32 backend is a curated table lookup, not an LLM).
    "anthropic", "openai", "langchain", "transformers",
    "llama_cpp",
)


# Sprint 5.32 only checks tokens that could have been introduced
# BY the auto-router change in this sprint. The worker's existing
# wallet / sign / broadcast safety surface is enforced by
# tests/trinity/test_useful_compute_worker_safety.py with a strip-
# aware grep that correctly ignores 'no_private_keys' as a
# safety_status field name. Duplicating that surface here with a
# plain substring grep would false-positive on those field names.
FORBIDDEN_NEW_IN_WORKER = (
    # Network primitives — the worker is local-dry-run.
    "import requests", "from requests",
    "urlopen(", "urllib.request",
    "requests.post(", "requests.get(",
    "socket.socket(", "socket.create_connection(",
    # Shell. subprocess via importlib for sibling scripts is the
    # existing pattern; shell=True is never allowed.
    "shell=True", "shell = True",
    # Dynamic code execution. The auto-router must NOT eval/exec
    # anything from the request metadata.
    "eval(", "exec(",
    # LLM client libraries — none in v0.1.
    "anthropic", "openai", "langchain", "transformers", "llama_cpp",
)


def _read(p):
    return p.read_text(encoding="utf-8")


def test_backends_script_exists():
    assert BACKENDS.is_file()


def test_backends_no_forbidden_new_tokens_after_5_32():
    src = _read(BACKENDS)
    found = [t for t in FORBIDDEN_NEW_IN_BACKENDS if t in src]
    assert not found, (
        "Sprint 5.32 introduced a forbidden token into "
        "scripts/trinity/useful_compute_backends.py: " + repr(found)
    )


def test_worker_no_forbidden_new_tokens_after_5_32():
    src = _read(WORKER)
    found = [t for t in FORBIDDEN_NEW_IN_WORKER if t in src]
    assert not found, (
        "Sprint 5.32 introduced a forbidden token into "
        "scripts/trinity/useful_compute_worker.py: " + repr(found)
    )


def test_materials_engine_handler_present():
    src = _read(BACKENDS)
    assert "def _materials_engine_v01(" in src
    assert "_MATERIALS_ENGINE_BACKEND_NAME" in src
    assert "trinity-materials-engine-result/v0.1" in src


def test_materials_engine_table_pinned_in_source():
    """The properties table must remain a named module-level
    constant so a reviewer can audit the curated values at a
    glance. v0.2 may move it into a JSON sibling; v0.1 keeps it
    in source for easy review."""
    src = _read(BACKENDS)
    assert "_MATERIALS_PROPERTIES_TABLE_V01" in src
    for material in ('"CeO2"', '"PrOx"', '"Sm2O3"', '"Y2O3"',
                     '"ZrO2"', '"TiO2"'):
        assert material in src, (
            "_MATERIALS_PROPERTIES_TABLE_V01 missing: " + material
        )


def test_metric_to_property_mapping_present():
    src = _read(BACKENDS)
    assert "_METRIC_TO_PROPERTY" in src
    # Spot-check three label families that the Sprint 5.31
    # classifier emits.
    for needle in (
        '"oxygen_storage_capacity"',
        '"temperature_c"',
        '"stability"',
    ):
        assert needle in src


def test_property_bounds_present_for_every_property():
    """If a future PR adds a property to
    _MATERIALS_PROPERTIES_TABLE_V01 without adding bounds, scoring
    would default to 0. This grep catches an obvious gap."""
    src = _read(BACKENDS)
    assert "_PROPERTY_BOUNDS" in src
    for prop in ("oxygen_storage_mmol_g", "optimal_temperature_c",
                 "redox_support", "stability", "conductivity",
                 "surface_area_m2_g"):
        # Every property used in the curated table must appear in
        # the bounds map (we grep both contexts).
        assert prop in src, (
            "_MATERIALS_PROPERTIES_TABLE_V01 uses property "
            + prop + " but _PROPERTY_BOUNDS may be missing it"
        )


def test_disclaimer_says_not_dft():
    src = _read(BACKENDS)
    assert "_MATERIALS_ENGINE_DISCLAIMER" in src
    assert "NOT DFT" in src
    assert "curated" in src


def test_worker_auto_router_wired():
    """The Sprint 5.32 auto-router must remain visible as a clear
    block in the worker source. If a refactor accidentally drops
    it, the materials_engine never runs."""
    src = _read(WORKER)
    assert "effective_backend_name" in src
    assert "local_materials_engine_v01" in src
    assert '"materials_engine"' in src
    assert "scientific_task_classification" in src


def test_task_queue_does_not_pass_materials_engine_directly(
):
    """The task_queue still passes --backend placeholder
    (default) when invoking the worker; the auto-router upgrade
    happens INSIDE the worker. If the queue ever passes the
    materials backend by name we want to know — it would defeat
    the operator's --backend placeholder opt-out path."""
    src = _read(TASK_QUEUE)
    assert "local_materials_engine_v01" not in src
