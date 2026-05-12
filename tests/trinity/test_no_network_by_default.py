"""Static check: no Sprint 5.6 script imports network libraries or
spawns subprocesses."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"

_SPRINT_56_SCRIPTS = [
    "trinity_orchestrator.py",
    "sost_ai_orchestrator_adapter.py",
    "trinity_error_memory.py",
    "useful_compute_reward_model.py",
    "useful_compute_task_builder.py",
    "useful_compute_worker.py",
    "useful_compute_replay_validator.py",
    "useful_compute_governance_gate.py",
]


_FORBIDDEN_IMPORTS = (
    "requests",
    "urllib.request",
    "urllib3",
    "httpx",
    "aiohttp",
    "socket",
    "websockets",
    "paho",
)

_FORBIDDEN_SUBPROCESS_TOKENS = (
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "os.system",
)


def _strip_strings_and_comments(src: str) -> str:
    # Remove triple-quoted strings.
    src = re.sub(r'"""[\s\S]*?"""', '', src)
    src = re.sub(r"'''[\s\S]*?'''", '', src)
    # Remove single-line strings (best effort).
    src = re.sub(r'"[^"\n]*"', '""', src)
    src = re.sub(r"'[^'\n]*'", "''", src)
    # Remove comments.
    src = re.sub(r"#[^\n]*", "", src)
    return src


@pytest.mark.parametrize("script", _SPRINT_56_SCRIPTS)
def test_no_network_imports(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    stripped = _strip_strings_and_comments(src)
    for name in _FORBIDDEN_IMPORTS:
        m = re.search(rf"^\s*(?:import|from)\s+{re.escape(name)}\b",
                      stripped, re.MULTILINE)
        assert m is None, (
            f"forbidden network import {name!r} appears in {script}"
        )


@pytest.mark.parametrize("script", _SPRINT_56_SCRIPTS)
def test_no_subprocess_or_shell_invocations(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    stripped = _strip_strings_and_comments(src)
    for token in _FORBIDDEN_SUBPROCESS_TOKENS:
        assert token not in stripped, (
            f"forbidden subprocess/shell call {token!r} appears in "
            f"{script}"
        )
