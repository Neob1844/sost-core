"""Functional tests for the Trinity Autonomy Governor v0.1
(Sprint 5.23). These tests exercise the policy/decision contract
documented in docs/TRINITY_AUTONOMY_GOVERNOR_V01.md and SECURITY.md.

All tests are local-only: no network, no subprocess, no wallet, no
real ``sost-cli``. The Governor itself is also forbidden from any of
those — see test_autonomy_governor_safety.py for the static checks.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "trinity" / "autonomy_governor.py"
EXAMPLE_POLICY = REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"

# Make the script importable as a module: scripts/trinity is not a
# package, so we add it to sys.path inside a fixture.
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


@pytest.fixture(scope="module")
def gov():
    """Import the autonomy_governor module by file path."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        import autonomy_governor  # type: ignore
        yield autonomy_governor
    finally:
        try:
            sys.path.remove(str(SCRIPTS_DIR))
        except ValueError:
            pass


@pytest.fixture
def example_policy_dict():
    with open(EXAMPLE_POLICY, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def write_policy(tmp_path):
    """Returns a callable that writes a policy dict to a tmp file and
    returns its Path."""
    def _w(policy_dict, name="policy.json"):
        p = tmp_path / name
        p.write_text(json.dumps(policy_dict, indent=2), encoding="utf-8")
        return p
    return _w


def _boot_and_decide(gov, policy_path, action, params=None, pinned_time="2026-05-16T00:00:00+00:00"):
    boot = gov._sha256_file(policy_path)
    with open(policy_path, "r", encoding="utf-8") as f:
        policy = json.load(f)
    gov._validate_policy_v01(policy)
    return gov.decide(
        policy=policy,
        policy_path=policy_path,
        boot_policy_sha256=boot,
        action=action,
        action_params=params or {},
        pinned_time=pinned_time,
    )


# ---------------------------------------------------------------------------
# Policy load-time invariants
# ---------------------------------------------------------------------------

def test_example_policy_validates_under_load(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    # Just calling _validate_policy_v01 must not raise.
    gov._validate_policy_v01(example_policy_dict)


def test_propose_mode_rejected(gov, example_policy_dict, write_policy):
    bad = copy.deepcopy(example_policy_dict)
    bad["mode"] = "propose"
    with pytest.raises(gov.GovernorError) as excinfo:
        gov._validate_policy_v01(bad)
    assert "propose" in str(excinfo.value) or "observe" in str(excinfo.value)


def test_execute_bounded_mode_rejected(gov, example_policy_dict):
    bad = copy.deepcopy(example_policy_dict)
    bad["mode"] = "execute_bounded"
    with pytest.raises(gov.GovernorError):
        gov._validate_policy_v01(bad)


def test_autonomous_sost_stocks_nonzero_rejected(gov, example_policy_dict):
    bad = copy.deepcopy(example_policy_dict)
    bad["caps_per_day"]["autonomous_sost_stocks"] = 1
    with pytest.raises(gov.GovernorError) as excinfo:
        gov._validate_policy_v01(bad)
    assert "T08" in str(excinfo.value)


def test_wrong_schema_rejected(gov, example_policy_dict):
    bad = copy.deepcopy(example_policy_dict)
    bad["schema"] = "trinity-autonomy-governor-policy/v0.2"
    with pytest.raises(gov.GovernorError):
        gov._validate_policy_v01(bad)


# ---------------------------------------------------------------------------
# Per-action decisions
# ---------------------------------------------------------------------------

def test_create_request_allowed_for_allowlisted_source_tool(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(
        gov, p, "create_request",
        {"source_tool": "trinity_scientific_prompt_intake"},
    )
    assert d["allowed"] is True
    assert d["blocked_reason"] is None
    assert d["allowlists_checked"]["source_tools"]["allowed"] is True
    assert d["threat_refs"] == ["T01", "T05", "T09"]


def test_create_request_blocked_for_unknown_source_tool(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(
        gov, p, "create_request",
        {"source_tool": "definitely_not_registered"},
    )
    assert d["allowed"] is False
    assert d["blocked_reason"] == "source_tool_not_in_allowlist"


def test_create_request_cap_exceeded_blocks(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    cap = example_policy_dict["caps_per_day"]["requests_created"]
    d = _boot_and_decide(
        gov, p, "create_request",
        {
            "source_tool": "trinity_scientific_prompt_intake",
            "requests_created_today": cap,
        },
    )
    assert d["allowed"] is False
    assert d["blocked_reason"] == "cap.requests_created_exceeded"


def test_real_sign_always_requires_human(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "real_sign", {})
    assert d["allowed"] is False
    assert d["requires_human_approval"] is True
    assert d["blocked_reason"] == "requires_human_approval"
    assert "T07" in d["threat_refs"] and "T08" in d["threat_refs"]


def test_broadcast_always_requires_human(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "broadcast_signed_transaction", {})
    assert d["allowed"] is False
    assert d["requires_human_approval"] is True
    assert d["blocked_reason"] == "requires_human_approval"


def test_wallet_access_blocked(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "wallet_access", {})
    assert d["allowed"] is False
    assert d["requires_human_approval"] is True


def test_call_rpc_allowlisted_method(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "call_rpc", {"rpc_method": "getinfo"})
    assert d["allowed"] is True
    assert d["allowlists_checked"]["rpc_methods"]["allowed"] is True


def test_call_rpc_non_allowlisted_method(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "call_rpc", {"rpc_method": "dumpprivkey"})
    assert d["allowed"] is False
    assert d["blocked_reason"] == "rpc_method_not_in_allowlist"


def test_filesystem_read_allowlisted_path(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "filesystem_read", {"path": "data/intake/foo.json"})
    assert d["allowed"] is True
    assert d["allowlists_checked"]["filesystem_read"]["allowed"] is True


def test_filesystem_read_forbidden_path(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "filesystem_read", {"path": "secrets/db.key"})
    assert d["allowed"] is False
    assert d["blocked_reason"] == "filesystem_path_forbidden"


def test_filesystem_write_to_constitution_blocked(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    # Either by exact path or by basename: writing the policy must be refused.
    d = _boot_and_decide(
        gov, p, "filesystem_write",
        {"path": "config/trinity_autonomy_governor.example.json"},
    )
    assert d["allowed"] is False
    # Either path-forbidden or cannot-write-constitution is acceptable;
    # the spec says the policy file should be in filesystem_forbidden and
    # the Governor also belt-and-tirantes blocks it by basename match.
    assert d["blocked_reason"] in (
        "cannot_write_constitution",
        "filesystem_path_forbidden",
    )


def test_filesystem_write_to_allowlisted_path(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(
        gov, p, "filesystem_write", {"path": "drafts/foo.txt"},
    )
    assert d["allowed"] is True


def test_unknown_action_blocked(gov, example_policy_dict, write_policy):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(gov, p, "rm_dash_rf_slash", {})
    assert d["allowed"] is False
    assert d["blocked_reason"].startswith("unknown_action:")


# ---------------------------------------------------------------------------
# Kill switch + policy mutation
# ---------------------------------------------------------------------------

def test_halt_file_blocks_all_actions(
    gov, example_policy_dict, write_policy, tmp_path,
):
    halt = tmp_path / "HALT"
    halt.write_text("stop")
    pol = copy.deepcopy(example_policy_dict)
    pol["kill_switch"]["halt_file"] = str(halt)
    p = write_policy(pol)
    d = _boot_and_decide(
        gov, p, "create_request",
        {"source_tool": "trinity_scientific_prompt_intake"},
    )
    assert d["allowed"] is False
    assert d["blocked_reason"] == "halt_file_present"
    assert d["kill_switch_checked"]["halt_file"] is True


def test_policy_mutated_at_runtime_blocks(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    boot = gov._sha256_file(p)
    # Mutate the file AFTER computing the boot hash.
    with open(p, "r", encoding="utf-8") as f:
        policy = json.load(f)
    mutated = copy.deepcopy(policy)
    mutated["allowlists"]["rpc_methods"].append("dumpprivkey")
    p.write_text(json.dumps(mutated, indent=2), encoding="utf-8")

    d = gov.decide(
        policy=policy,           # caller still holds the in-memory boot copy
        policy_path=p,
        boot_policy_sha256=boot,
        action="call_rpc",
        action_params={"rpc_method": "getinfo"},
        pinned_time="2026-05-16T00:00:00+00:00",
    )
    assert d["allowed"] is False
    assert d["blocked_reason"] == "policy_mutated_at_runtime"
    assert d["policy_hashes_match"] is False


# ---------------------------------------------------------------------------
# Determinism + decision shape
# ---------------------------------------------------------------------------

def test_decision_is_deterministic_for_same_inputs(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    d1 = _boot_and_decide(
        gov, p, "create_request",
        {"source_tool": "trinity_scientific_prompt_intake"},
        pinned_time="2026-05-16T00:00:00+00:00",
    )
    d2 = _boot_and_decide(
        gov, p, "create_request",
        {"source_tool": "trinity_scientific_prompt_intake"},
        pinned_time="2026-05-16T00:00:00+00:00",
    )
    assert d1["decision_id"] == d2["decision_id"]
    assert d1 == d2


def test_action_params_appear_in_decision(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(
        gov, p, "create_request",
        {"source_tool": "trinity_scientific_prompt_intake",
         "estimated_worker_minutes": 5},
    )
    assert d["action_params"]["source_tool"] == "trinity_scientific_prompt_intake"
    assert d["action_params"]["estimated_worker_minutes"] == 5


def test_decision_has_all_required_fields(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    d = _boot_and_decide(
        gov, p, "create_request",
        {"source_tool": "trinity_scientific_prompt_intake"},
    )
    required = (
        "schema", "decision_id", "policy_sha256", "policy_runtime_sha256",
        "policy_hashes_match", "policy_path_basename", "action", "action_params",
        "mode", "allowed", "blocked_reason", "requires_human_approval",
        "caps_checked", "allowlists_checked", "kill_switch_checked",
        "safety_status", "threat_refs", "pinned_time",
    )
    for key in required:
        assert key in d, "missing required decision field: " + key
    assert d["schema"] == "trinity-autonomy-governor-decision/v0.1"
    assert d["mode"] == "observe"
    assert len(d["policy_sha256"]) == 64
    assert len(d["policy_runtime_sha256"]) == 64
    assert len(d["decision_id"]) == 32


def test_threat_refs_set_for_every_known_action(
    gov, example_policy_dict, write_policy,
):
    p = write_policy(example_policy_dict)
    for action in gov.KNOWN_ACTIONS:
        d = _boot_and_decide(gov, p, action, {})
        assert d["threat_refs"], "action " + action + " missing threat_refs"
        for ref in d["threat_refs"]:
            assert ref.startswith("T")
            assert ref[1:].isdigit()
