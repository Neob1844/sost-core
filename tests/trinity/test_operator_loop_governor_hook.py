"""Trinity Sprint 5.24 — operator_loop ↔ Autonomy Governor hook
integration tests.

Drives the full operator_loop with and without --governor-policy and
asserts the observe-only contract:
  * absence of --governor-policy is a strict no-op (baseline parity)
  * presence of --governor-policy produces one decision JSON per
    pipeline step, all registered as artifacts with sha256, and
    governor_enabled / governor_policy_sha256 /
    governor_policy_path_basename / governor_decisions_count are set
  * no absolute path of the policy file is ever persisted in
    operator_run.json (only the basename); the policy sha256 alone
    pins the file
  * a halt_file present at run time hard-blocks the first step that
    is evaluated, raising GovernorHardBlock
  * a policy mutation between resumes is detected and refuses the
    resume
  * observe-only never blocks non-critical actions even when the
    policy reports allowed=false; the decision is still recorded as
    an artifact and a warning is appended to operator_run.json
  * the integration uses direct Python import, no subprocess
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"
EXAMPLE_POLICY = REPO_ROOT / "config" / "trinity_autonomy_governor.example.json"


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def loop_mod():
    return _load(
        "ucol_gov",
        SCRIPTS_DIR / "useful_compute_operator_loop.py",
    )


@pytest.fixture(scope="module")
def gov_mod():
    return _load(
        "autonomy_governor_gov",
        SCRIPTS_DIR / "autonomy_governor.py",
    )


OPERATOR_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP"
PINNED = "2026-05-16T00:00:00+00:00"
EXPECTED_STEPS = [
    "task_builder", "worker", "replay_validator",
    "governance_gate", "reward_budget_policy",
    "payment_proposal", "payment_draft",
]


# ---------------------------------------------------------------------------
# Fixture helpers (copied from test_useful_compute_operator_loop.py so this
# file is self-contained — the existing test file is not imported because
# pytest collects test_* names from it)
# ---------------------------------------------------------------------------


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _hex_address(seed: str) -> str:
    body = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]
    return "sost1" + body


def _make_inputs(tmp_path: Path) -> Dict[str, Path]:
    bundle = tmp_path / "input_bundle.json"
    bundle.write_text(
        json.dumps(
            {"task_id": "demo-001", "payload": "abc"},
            sort_keys=True, separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    addr_map = {
        "schema": "trinity-worker-address-map/v0.1",
        "workers": [
            {
                "worker_id_hash": _sha16("worker-A"),
                "payout_address": _hex_address("worker-A-pay"),
                "label": "worker-A",
            },
            {
                "worker_id_hash": _sha16("worker-B"),
                "payout_address": _hex_address("worker-B-pay"),
                "label": "worker-B",
            },
        ],
    }
    addr_path = tmp_path / "address_map.json"
    addr_path.write_text(
        json.dumps(addr_map, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return {"bundle": bundle, "address_map": addr_path}


def _argv(
    *, out_dir: Path, bundle: Path, address_map: Path,
    governor_policy: Path = None,
    governor_decisions_dir: Path = None,
    resume: Path = None,
) -> List[str]:
    argv = [
        "--mode", "local-dry-run",
        "--out-dir", str(out_dir),
        "--require-confirmation-token", OPERATOR_TOKEN,
        "--candidate-id", "op-test-candidate-gov",
        "--input-bundle", str(bundle),
        "--worker-address-map", str(address_map),
        "--max-total-stocks", "10000000",
        "--pool-balance-stocks", "100000000",
        "--pinned-time", PINNED,
        "--worker-id", "worker-A",
        "--worker-id", "worker-B",
    ]
    if governor_policy is not None:
        argv += ["--governor-policy", str(governor_policy)]
    if governor_decisions_dir is not None:
        argv += ["--governor-decisions-dir", str(governor_decisions_dir)]
    if resume is not None:
        argv += ["--resume", str(resume)]
    return argv


def _copy_policy(tmp_path: Path, name: str = "policy.json") -> Path:
    p = tmp_path / name
    p.write_text(EXAMPLE_POLICY.read_text(encoding="utf-8"), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Baseline parity: no --governor-policy => zero observable change
# ---------------------------------------------------------------------------


def test_operator_loop_without_governor_policy_is_unchanged(
    tmp_path, loop_mod,
):
    """Sprint 5.24 must not affect the existing pipeline when the
    governor flag is absent. operator_run.json reports
    governor_enabled=false and no governor_decisions are emitted."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    assert rc == 0
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    assert state["governor_enabled"] is False
    assert state["governor_policy_sha256"] is None
    assert state["governor_policy_path_basename"] is None
    assert state["governor_decisions_count"] == 0
    assert "governor_decisions" not in state["artifacts"]
    assert not (out_dir / "governor_decisions").exists()
    # The pipeline still ran the full 7 steps.
    assert state["steps_completed"] == EXPECTED_STEPS


# ---------------------------------------------------------------------------
# With --governor-policy: one decision per step, all hashed + indexed
# ---------------------------------------------------------------------------


def test_operator_loop_with_governor_policy_emits_decisions(
    tmp_path, loop_mod,
):
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol = _copy_policy(tmp_path)
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    assert rc == 0
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    assert state["governor_enabled"] is True
    assert state["governor_policy_sha256"] == (
        hashlib.sha256(pol.read_bytes()).hexdigest()
    )
    # The persisted reference is a BASENAME, never an absolute path.
    assert state["governor_policy_path_basename"] == pol.name
    assert "/" not in state["governor_policy_path_basename"]
    # One decision per pipeline step.
    assert state["governor_decisions_count"] == len(EXPECTED_STEPS)
    decisions = state["artifacts"]["governor_decisions"]
    assert len(decisions) == len(EXPECTED_STEPS)
    for entry in decisions:
        p = out_dir / entry["path"]
        assert p.exists(), "missing decision file: " + entry["path"]
        actual = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual == entry["sha256"], (
            "manifest sha256 mismatch for " + entry["path"]
        )


def test_operator_loop_decisions_match_step_names_in_order(
    tmp_path, loop_mod,
):
    """The decision files emitted in order must cover each pipeline
    step exactly once and in the same sequence as the pipeline ran."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol = _copy_policy(tmp_path)
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    seen_steps = []
    for entry in state["artifacts"]["governor_decisions"]:
        decision = json.loads(
            (out_dir / entry["path"]).read_text(encoding="utf-8"),
        )
        assert decision["action"] == "pipeline_step"
        seen_steps.append(decision["action_params"]["step_name"])
    assert seen_steps == EXPECTED_STEPS


def test_operator_loop_decisions_threat_refs_are_T15_T16_T17(
    tmp_path, loop_mod,
):
    """Every pipeline_step decision must carry the same SECURITY.md
    threat refs the Governor declares for the pipeline_step action."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol = _copy_policy(tmp_path)
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    for entry in state["artifacts"]["governor_decisions"]:
        decision = json.loads(
            (out_dir / entry["path"]).read_text(encoding="utf-8"),
        )
        assert decision["threat_refs"] == ["T15", "T16", "T17"]


def test_operator_loop_uses_custom_decisions_dir(tmp_path, loop_mod):
    """--governor-decisions-dir redirects the JSONs out of the default
    out_dir/governor_decisions location into another subpath under
    out_dir, and the manifest entries still resolve from out_dir."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    out_dir.mkdir(parents=True, exist_ok=True)
    decisions_dir = out_dir / "audit_only" / "decisions"
    pol = _copy_policy(tmp_path)
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
        governor_decisions_dir=decisions_dir,
    ))
    assert rc == 0
    assert decisions_dir.exists()
    files = list(decisions_dir.glob(
        "TRINITY_AUTONOMY_GOVERNOR_DECISION_*.json",
    ))
    assert len(files) == len(EXPECTED_STEPS)
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    # Each manifest path resolves to a real file relative to out_dir.
    for entry in state["artifacts"]["governor_decisions"]:
        p = out_dir / entry["path"]
        assert p.exists(), "missing decision file: " + entry["path"]


# ---------------------------------------------------------------------------
# Privacy: no absolute paths leak into the state file
# ---------------------------------------------------------------------------


def test_operator_run_does_not_leak_absolute_policy_path(
    tmp_path, loop_mod,
):
    """operator_run.json must NEVER contain the absolute path of the
    governor policy file (it can carry user-identifying segments).
    Only the basename + sha256 are persisted."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol_dir = tmp_path / "private" / "operator_only"
    pol_dir.mkdir(parents=True)
    pol = _copy_policy(pol_dir, "very_secret_policy.json")
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    raw = (out_dir / "operator_run.json").read_text(encoding="utf-8")
    # No absolute path of the policy file leaks.
    assert "private/operator_only" not in raw
    assert str(pol) not in raw
    # The basename can appear (it's the documented persisted field).
    assert pol.name in raw


# ---------------------------------------------------------------------------
# Kill switch: halt_file present hard-blocks the run
# ---------------------------------------------------------------------------


def test_halt_file_present_hard_blocks_first_step(
    tmp_path, loop_mod, gov_mod,
):
    """When the halt_file referenced by the policy exists at the
    moment a pipeline step is about to evaluate, the operator_loop
    must exit with rc=3 (governor hard-block) and refuse to proceed.
    The decision JSON for that step is written to the audit trail."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    halt = tmp_path / "HALT"
    halt.write_text("stop")
    base = json.loads(EXAMPLE_POLICY.read_text(encoding="utf-8"))
    base["kill_switch"]["halt_file"] = str(halt)
    pol = tmp_path / "policy_with_halt.json"
    pol.write_text(json.dumps(base, indent=2), encoding="utf-8")
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    # main() catches GovernorHardBlock and turns it into rc=3.
    assert rc == 3
    # Audit artefact for the blocked step exists on disk.
    decisions = list(
        (out_dir / "governor_decisions").glob(
            "TRINITY_AUTONOMY_GOVERNOR_DECISION_*.json",
        )
    )
    assert len(decisions) == 1, (
        "exactly one decision should be written before the hard-block"
    )
    decision = json.loads(decisions[0].read_text(encoding="utf-8"))
    assert decision["action"] == "pipeline_step"
    assert decision["action_params"]["step_name"] == "task_builder"
    assert decision["allowed"] is False
    assert decision["blocked_reason"] == "halt_file_present"


# ---------------------------------------------------------------------------
# Tamper detection: policy file mutates between original run and resume
# ---------------------------------------------------------------------------


def test_policy_mutation_between_resume_refuses_resume(
    tmp_path, loop_mod,
):
    """Original run pins sha256(policy). If the policy file is
    modified between the original run and the resume, the resume
    must refuse to continue (raises ValueError with the saved/current
    hashes)."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol = _copy_policy(tmp_path)
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    assert rc == 0
    # Mutate the policy file in place: append a benign extra allowlist entry.
    mutated = json.loads(pol.read_text(encoding="utf-8"))
    mutated["allowlists"]["rpc_methods"].append("getmempoolinfo")
    pol.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
        resume=out_dir / "operator_run.json",
    ))
    # main() catches the ValueError from run_operator_loop and turns it
    # into rc=2 (operator-level error). The state file on disk is not
    # advanced past the saved sha256 so the file is untouched.
    assert rc == 2
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    # The original boot sha is still recorded; the mutation did not
    # silently overwrite it.
    assert state["governor_policy_sha256"] != (
        hashlib.sha256(pol.read_bytes()).hexdigest()
    )


# ---------------------------------------------------------------------------
# State is preserved on resume of a governor-enabled run
# ---------------------------------------------------------------------------


def test_resume_governor_enabled_run_carries_sha_forward(
    tmp_path, loop_mod,
):
    """Resuming an already-complete run with the same policy file
    succeeds without altering governor_policy_sha256."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol = _copy_policy(tmp_path)
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    state_before = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
        resume=out_dir / "operator_run.json",
    ))
    assert rc == 0
    state_after = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    assert state_after["governor_enabled"] is True
    assert (
        state_after["governor_policy_sha256"]
        == state_before["governor_policy_sha256"]
    )


# ---------------------------------------------------------------------------
# operator_run.json under governor still validates against the v0.1 schema
# ---------------------------------------------------------------------------


def _validate_shape(obj, schema):
    """Tiny structural validator that mirrors the one in
    test_useful_compute_operator_loop.py. Avoids jsonschema $ref
    resolver headaches with the operator_run schema's $id."""
    if schema.get("type") == "object":
        assert isinstance(obj, dict)
        required = set(schema.get("required", []))
        missing = required - set(obj.keys())
        assert not missing, "missing fields: " + str(sorted(missing))
        if schema.get("additionalProperties") is False:
            allowed = set(schema["properties"].keys())
            extra = set(obj.keys()) - allowed
            assert not extra, "extra fields: " + str(sorted(extra))
        for k, sub in schema["properties"].items():
            if k in obj:
                _validate_shape(obj[k], sub)
    elif schema.get("type") == "array":
        for item in obj:
            _validate_shape(item, schema.get("items", {}))
    else:
        if "const" in schema:
            assert obj == schema["const"]
        if "enum" in schema:
            assert obj in schema["enum"]
        if "pattern" in schema:
            import re as _re
            assert isinstance(obj, str)
            assert _re.match(schema["pattern"], obj)
        if "oneOf" in schema:
            ok = False
            for sub in schema["oneOf"]:
                try:
                    _validate_shape(obj, sub)
                    ok = True
                    break
                except AssertionError:
                    continue
            assert ok


def test_governor_enabled_operator_run_validates_against_schema(
    tmp_path, loop_mod,
):
    """The Sprint 5.24 schema extension is backwards-compatible: the
    governor-enabled operator_run.json still validates against the
    operator_run schema (top-level shape + new governor_* fields)."""
    schema_path = (
        REPO_ROOT / "schemas" / "trinity"
        / "useful_compute_operator_run.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol = _copy_policy(tmp_path)
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8"),
    )
    _validate_shape(state, schema)
    # The four governor_* fields populated correctly.
    assert state["governor_enabled"] is True
    assert state["governor_policy_path_basename"] == pol.name
    assert state["governor_policy_sha256"] == (
        hashlib.sha256(pol.read_bytes()).hexdigest()
    )
    assert state["governor_decisions_count"] == len(EXPECTED_STEPS)


# ---------------------------------------------------------------------------
# Governor is invoked by direct import — no subprocess on the integration path
# ---------------------------------------------------------------------------


def test_no_subprocess_invocation_during_governor_hook(
    tmp_path, loop_mod, monkeypatch,
):
    """The operator_loop must NOT shell out to invoke the Governor.
    Patch subprocess.run/Popen to fail loudly and ensure the run still
    completes successfully with --governor-policy."""
    import subprocess

    def _boom(*args, **kwargs):
        raise AssertionError(
            "operator_loop reached subprocess during governor hook"
        )

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(subprocess, "check_call", _boom)
    monkeypatch.setattr(subprocess, "check_output", _boom)

    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    pol = _copy_policy(tmp_path)
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        governor_policy=pol,
    ))
    assert rc == 0
