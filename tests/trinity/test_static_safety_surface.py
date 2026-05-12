"""Static safety surface for Sprint 5.6 (Trinity Autonomy v0.1).

Confirms across every Trinity Autonomy script:
- no private-key handling
- no automatic payout language
- no consensus / tx / signer imports
- no paid providers enabled by default
- no on-chain register/broadcast/send/sign CLI flags
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
SCHEMAS_DIR = REPO_ROOT / "schemas" / "trinity"
CONFIG_DIR = REPO_ROOT / "config" / "trinity" / "objectives"

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


_FORBIDDEN_KEY_TOKENS = (
    "private_key", "privkey", "secret_key", "seed_phrase",
    "mnemonic", "passphrase",
)

_FORBIDDEN_PAYOUT_TOKENS = (
    "auto_payout", "automatic_payout",
    "broadcast_tx", "sign_tx", "send_tx",
    "submit_to_mempool",
)

_FORBIDDEN_CONSENSUS_TOKENS = (
    "consensus.", "tx_validation", "tx_signer",
)

_FORBIDDEN_PAID_DEFAULT_TOKENS = (
    "OpenRouter", "openai_api_key", "anthropic_api_key",
    "ollama_endpoint",
)

_FORBIDDEN_CLI_FLAGS = (
    "--register", "--send", "--broadcast", "--activate", "--reward",
    "--sign-tx",
)


def _strip_strings_and_comments(src: str) -> str:
    # Strip triple-quoted strings.
    src = re.sub(r'"""[\s\S]*?"""', '', src)
    src = re.sub(r"'''[\s\S]*?'''", '', src)
    # Strip single-line strings — this hides string literals (e.g.
    # argparse flag names, dict keys, log lines) so the test fires
    # only on bare identifiers actually used in code paths.
    src = re.sub(r'"[^"\n]*"', '""', src)
    src = re.sub(r"'[^'\n]*'", "''", src)
    # Strip comments.
    src = re.sub(r"#[^\n]*", "", src)
    return src


@pytest.mark.parametrize("script", _SPRINT_56_SCRIPTS)
def test_no_private_key_tokens(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    stripped = _strip_strings_and_comments(src).lower()
    for tok in _FORBIDDEN_KEY_TOKENS:
        assert tok.lower() not in stripped, (
            f"private-key token {tok!r} appears in code in {script} "
            f"(denial-only mentions in string literals are stripped)"
        )


@pytest.mark.parametrize("script", _SPRINT_56_SCRIPTS)
def test_no_automatic_payout_tokens(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    stripped = _strip_strings_and_comments(src)
    for tok in _FORBIDDEN_PAYOUT_TOKENS:
        assert tok not in stripped, (
            f"automatic-payout token {tok!r} appears in {script}"
        )


@pytest.mark.parametrize("script", _SPRINT_56_SCRIPTS)
def test_no_consensus_or_tx_tokens(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    stripped = _strip_strings_and_comments(src)
    for tok in _FORBIDDEN_CONSENSUS_TOKENS:
        assert tok not in stripped, (
            f"consensus/tx token {tok!r} appears in {script}"
        )


@pytest.mark.parametrize("script", _SPRINT_56_SCRIPTS)
def test_no_paid_providers_by_default(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    stripped = _strip_strings_and_comments(src)
    for tok in _FORBIDDEN_PAID_DEFAULT_TOKENS:
        assert tok not in stripped, (
            f"paid-provider token {tok!r} appears in {script}"
        )


@pytest.mark.parametrize("script", _SPRINT_56_SCRIPTS)
def test_no_register_send_broadcast_cli_flags(script):
    src = (SCRIPTS_DIR / script).read_text(encoding="utf-8")
    stripped = _strip_strings_and_comments(src)
    for flag in _FORBIDDEN_CLI_FLAGS:
        assert flag not in stripped, (
            f"forbidden CLI flag {flag!r} appears in {script}"
        )


def test_uc_request_schema_is_strict():
    import json
    schema = json.loads(
        (SCHEMAS_DIR / "useful_compute_request.schema.json")
        .read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["schema"]["const"] == \
        "trinity-useful-compute-request/v0.1"


def test_objectives_carry_hard_rules():
    import json
    for name in ("geaspirit", "materials_engine",
                 "useful_compute", "sost_ai"):
        obj = json.loads(
            (CONFIG_DIR / f"{name}.json").read_text(encoding="utf-8")
        )
        assert obj["schema"] == "trinity-objective/v0.1"
        assert isinstance(obj.get("hard_rules"), list)
        assert len(obj["hard_rules"]) >= 1
