"""Static safety tests for scripts/trinity/autonomy_governor.py.

These tests enforce, by substring grep, that the Autonomy Governor v0.1
cannot accidentally grow capabilities it should not have. If a future
PR adds ``import requests`` or ``subprocess.run`` to the governor,
this test fails CI before the PR can merge.

The Governor MUST stay:
  - off the network
  - off the shell
  - off the wallet / signing / broadcast
  - off dynamic code execution (eval/exec)

The Governor MAY:
  - read its policy file from disk
  - write its decision JSON to the operator-supplied --out-dir
  - hash with hashlib
  - parse argparse / json
  - use pathlib + datetime
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "autonomy_governor.py"


# Substrings that must NEVER appear in the governor source. Each is
# either a network/IO library import, a shell-out helper, or a
# wallet/signing primitive. Tested as plain-substring match (the test
# is intentionally simple so a reviewer can scan it).
FORBIDDEN_TOKENS = (
    # Network libraries (no heartbeats, no API calls).
    "import requests", "from requests",
    "import urllib", "from urllib",
    "import httpx", "from httpx",
    "import aiohttp", "from aiohttp",
    "import socket", "from socket",
    "import websockets", "from websockets",
    "import ftplib", "from ftplib",
    # Network function calls.
    "requests.", "urllib.",
    "httpx.", "aiohttp.", "socket.", "websockets.", "ftplib.",
    # Shell / subprocess.
    "import subprocess", "from subprocess", "subprocess.",
    "os.system(", "os.popen(",
    "shell=True", "shell = True",
    # Dynamic code execution.
    "eval(", "exec(",
    # Wallet / signing primitives (raw crypto / key material).
    # We DO allow the *literal action name strings* such as 'real_sign'
    # or 'broadcast_signed_transaction' because they are action
    # identifiers, not invocations. The tokens below catch the actual
    # crypto / key handling that would be a regression.
    "private_key", "seed_phrase", "mnemonic", "passphrase",
    "ecdsa", "secp256k1",
    # sost-cli / RPC clients (the governor must not call out).
    "sendrawtransaction(", "broadcast(",
    "sost-cli",
)


def _read_source() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_governor_source_file_exists():
    assert SCRIPT.is_file(), "autonomy_governor.py not found at " + str(SCRIPT)


def test_governor_has_no_forbidden_tokens():
    src = _read_source()
    found = [tok for tok in FORBIDDEN_TOKENS if tok in src]
    assert not found, (
        "scripts/trinity/autonomy_governor.py contains forbidden token(s): "
        + repr(found)
        + ". The Governor v0.1 must stay off network/shell/wallet/eval."
    )


def test_governor_does_not_import_other_trinity_scripts():
    """The Governor must be self-contained. Importing other trinity/*
    scripts would let it inherit their capabilities (broadcast guard,
    payment draft, etc.) which is exactly the surface we keep narrow."""
    src = _read_source()
    # Allow nothing from the trinity sibling modules.
    forbidden_imports = (
        "import operator_loop", "from operator_loop",
        "import broadcast_guard", "from broadcast_guard",
        "import payment_draft", "from payment_draft",
        "import payment_proposal", "from payment_proposal",
        "import reward_budget", "from reward_budget",
        "import useful_compute_worker", "from useful_compute_worker",
        "import useful_compute_backends", "from useful_compute_backends",
        "import useful_compute_task_builder", "from useful_compute_task_builder",
        "import scientific_prompt_intake", "from scientific_prompt_intake",
    )
    found = [tok for tok in forbidden_imports if tok in src]
    assert not found, (
        "Governor v0.1 must be self-contained; cannot import sibling "
        "trinity scripts. Found: " + repr(found)
    )


def test_governor_only_writes_inside_out_dir():
    """We assert structurally that the only ``open(...,'w')`` style
    writes target ``out_path`` (and that ``out_path`` is built from the
    operator-supplied ``--out-dir``). Heuristic: every open(...) call
    with mode 'w' must be on a variable named out_path."""
    src = _read_source()
    # All occurrences of open(...) with write mode.
    matches = re.findall(r"open\(\s*([^,)]+?)\s*,\s*['\"]w['\"]", src)
    # Each target must be 'out_path' (the only place we legitimately write).
    for m in matches:
        m = m.strip()
        assert m == "out_path", (
            "open(..., 'w') target must be 'out_path' (the operator-"
            "supplied --out-dir); found writing to: " + repr(m)
        )


def test_governor_module_docstring_mentions_observe_only():
    """The first docstring must make the v0.1 scope explicit so a
    casual reader cannot miss it."""
    src = _read_source()
    # Read first ~3000 chars; the module docstring must be in there.
    head = src[:3000].lower()
    assert "observe only" in head or "observe-only" in head, (
        "module docstring must explicitly say the Governor is observe-only"
    )
    assert "no network" in head, (
        "module docstring must explicitly say the Governor has no network"
    )


def test_governor_threat_refs_cover_all_known_actions():
    """Every action in KNOWN_ACTIONS must have a non-empty THREAT_REFS
    entry. We import the module to read both constants."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("autonomy_governor", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for action in mod.KNOWN_ACTIONS:
        refs = mod.THREAT_REFS.get(action)
        assert refs, "action " + action + " missing THREAT_REFS entry"
        for ref in refs:
            assert re.match(r"^T[0-9]{2}$", ref), (
                "bad threat ref " + repr(ref) + " for action " + action
            )
