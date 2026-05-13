"""Trinity Useful Compute operator loop — Sprint 5.19 functional tests.

Drives the full Useful Compute pipeline end-to-end through the
operator loop and checks: artefacts on disk, operator_run.json
shape, resume idempotence, hash-mismatch detection on tamper.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def loop_mod():
    return _load(
        "ucol",
        SCRIPTS_DIR / "useful_compute_operator_loop.py",
    )


OPERATOR_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP"


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _hex_address(seed: str) -> str:
    """Build a deterministic canonical sost1+40hex address from a
    seed. The 40-hex body is sha256(seed)[:40]."""
    body = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]
    return "sost1" + body


def _make_inputs(tmp_path: Path) -> Dict[str, Path]:
    """Create the two external inputs the loop needs:
    - an input-bundle file (any bytes)
    - a worker-address-map JSON with mappings for worker-A / worker-B
    """
    bundle = tmp_path / "input_bundle.json"
    bundle.write_text(
        json.dumps({"candidate": "op-test", "payload": "stub"},
                   sort_keys=True, separators=(",", ":")),
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
    resume: Path = None,
) -> List[str]:
    argv = [
        "--mode", "local-dry-run",
        "--out-dir", str(out_dir),
        "--require-confirmation-token", OPERATOR_TOKEN,
        "--candidate-id", "op-test-candidate-001",
        "--input-bundle", str(bundle),
        "--worker-address-map", str(address_map),
        "--max-total-stocks", "10000000",
        "--pool-balance-stocks", "100000000",
        "--pinned-time", "2026-05-13T00:00:00+00:00",
        "--worker-id", "worker-A",
        "--worker-id", "worker-B",
    ]
    if resume is not None:
        argv += ["--resume", str(resume)]
    return argv


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_full_pipeline_local_dry_run(tmp_path, loop_mod):
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    assert rc == 0
    state_path = out_dir / "operator_run.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema"] == \
        "trinity-useful-compute-operator-run/v0.1"
    assert state["mode"] == "local-dry-run"
    assert state["allow_wallet_access"] is False
    assert state["allow_broadcast"] is False
    assert state["human_review_required"] is True
    assert state["steps_completed"] == [
        "task_builder", "worker", "replay_validator",
        "governance_gate", "reward_budget_policy",
        "payment_proposal", "payment_draft",
    ]
    assert state["max_total_stocks"] == 10_000_000
    assert state["pool_balance_stocks"] == 100_000_000

    # Manifest exists and includes the recorded artifacts.
    manifest = (out_dir / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert "request.json" in manifest
    assert "TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_" in manifest


def test_artifact_files_match_state_hashes(tmp_path, loop_mod):
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8")
    )
    for step, entry in state["artifacts"].items():
        items = entry if isinstance(entry, list) else [entry]
        for e in items:
            p = out_dir / e["path"]
            assert p.exists(), f"artifact missing: {e['path']}"
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            assert h == e["sha256"], (
                f"hash mismatch for step={step} path={e['path']}"
            )


def test_payment_draft_signing_mode_is_safe(tmp_path, loop_mod):
    """The loop must never produce a real-signed draft. The final
    artefact MUST have signing_mode=unsigned_only and
    real_signed=false."""
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    draft_dir = out_dir / "draft"
    drafts = list(
        draft_dir.glob("TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_*.json")
    )
    assert drafts
    draft = json.loads(drafts[0].read_text(encoding="utf-8"))
    assert draft["signing_mode"] == "unsigned_only"
    assert draft["real_signed"] is False
    assert draft["safety_status"]["no_broadcast"] is True
    assert draft["safety_status"]["automatic_payout"] is False


# ---------------------------------------------------------------------------
# Resume idempotence
# ---------------------------------------------------------------------------


def test_resume_skips_completed_steps(tmp_path, loop_mod):
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    state_path = out_dir / "operator_run.json"
    state_before = state_path.read_text(encoding="utf-8")

    # Re-run with --resume; must complete cleanly and not change
    # the state file byte-for-byte (all steps already present, all
    # hashes match).
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        resume=state_path,
    ))
    assert rc == 0
    state_after = state_path.read_text(encoding="utf-8")
    assert state_after == state_before, (
        "resume on a fully-complete run must be byte-identical"
    )


def test_resume_requires_state_in_same_out_dir(
    tmp_path, loop_mod,
):
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    rc = loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(tmp_path / "different"),
        "--require-confirmation-token", OPERATOR_TOKEN,
        "--candidate-id", "x",
        "--input-bundle", str(inputs["bundle"]),
        "--worker-address-map", str(inputs["address_map"]),
        "--max-total-stocks", "1",
        "--pool-balance-stocks", "1",
        "--resume", str(out_dir / "operator_run.json"),
    ])
    assert rc == 2  # ValueError -> rc=2 path in main()


def test_tampered_artifact_blocks_resume(tmp_path, loop_mod):
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    state_path = out_dir / "operator_run.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Tamper with the task_builder request.
    request_path = out_dir / state["artifacts"]["task_builder"]["path"]
    obj = json.loads(request_path.read_text(encoding="utf-8"))
    obj["public_description"] = "tampered-after-run"
    request_path.write_text(
        json.dumps(obj, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    rc = loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
        resume=state_path,
    ))
    assert rc == 2  # hash mismatch is fatal


# ---------------------------------------------------------------------------
# Gate tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag", [
    "--broadcast", "--send", "--payout-now", "--auto-pay",
    "--sign-now", "--export-private-key",
    "--wallet", "--from-label", "--from-address",
    "--allow-wallet-access", "--allow-broadcast",
])
def test_cli_rejects_forbidden_flag(tmp_path, loop_mod, flag):
    rc = loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(tmp_path),
        "--require-confirmation-token", OPERATOR_TOKEN,
        "--candidate-id", "x",
        "--input-bundle", str(tmp_path / "x"),
        "--worker-address-map", str(tmp_path / "x"),
        "--max-total-stocks", "1",
        "--pool-balance-stocks", "1",
        flag,
    ])
    assert rc == 2


def test_cli_requires_exact_confirmation_token(tmp_path, loop_mod):
    inputs = _make_inputs(tmp_path)
    rc = loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(tmp_path / "run"),
        "--require-confirmation-token", "wrong",
        "--candidate-id", "x",
        "--input-bundle", str(inputs["bundle"]),
        "--worker-address-map", str(inputs["address_map"]),
        "--max-total-stocks", "1",
        "--pool-balance-stocks", "1",
    ])
    assert rc == 2


def test_cli_requires_input_bundle_and_address_map(
    tmp_path, loop_mod,
):
    inputs = _make_inputs(tmp_path)
    rc = loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(tmp_path / "run"),
        "--require-confirmation-token", OPERATOR_TOKEN,
        "--candidate-id", "x",
        "--worker-address-map", str(inputs["address_map"]),
        "--max-total-stocks", "1",
        "--pool-balance-stocks", "1",
    ])
    assert rc == 2

    rc2 = loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(tmp_path / "run"),
        "--require-confirmation-token", OPERATOR_TOKEN,
        "--candidate-id", "x",
        "--input-bundle", str(inputs["bundle"]),
        "--max-total-stocks", "1",
        "--pool-balance-stocks", "1",
    ])
    assert rc2 == 2


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_operator_run_id_deterministic_across_runs(
    tmp_path, loop_mod,
):
    """Two fresh runs with the same inputs and pinned-time must
    produce the same operator_run_id."""
    inputs = _make_inputs(tmp_path)
    rc1 = loop_mod.main(_argv(
        out_dir=tmp_path / "run1",
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    rc2 = loop_mod.main(_argv(
        out_dir=tmp_path / "run2",
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    assert rc1 == 0 and rc2 == 0
    s1 = json.loads(
        (tmp_path / "run1" / "operator_run.json")
        .read_text(encoding="utf-8")
    )
    s2 = json.loads(
        (tmp_path / "run2" / "operator_run.json")
        .read_text(encoding="utf-8")
    )
    assert s1["operator_run_id"] == s2["operator_run_id"]


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _validate(obj, schema):
    if schema.get("type") == "object":
        assert isinstance(obj, dict)
        required = set(schema.get("required", []))
        missing = required - set(obj.keys())
        assert not missing, f"missing fields: {sorted(missing)}"
        if schema.get("additionalProperties") is False:
            allowed = set(schema["properties"].keys())
            extra = set(obj.keys()) - allowed
            assert not extra, f"extra fields: {sorted(extra)}"
        for k, sub in schema["properties"].items():
            if k in obj:
                _validate(obj[k], sub)
    elif schema.get("type") == "array":
        for item in obj:
            _validate(item, schema.get("items", {}))
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
                    _validate(obj, sub)
                    ok = True
                    break
                except AssertionError:
                    continue
            assert ok


def test_operator_run_validates_against_schema(tmp_path, loop_mod):
    schema = json.loads((
        REPO_ROOT / "schemas" / "trinity"
        / "useful_compute_operator_run.schema.json"
    ).read_text(encoding="utf-8"))
    inputs = _make_inputs(tmp_path)
    out_dir = tmp_path / "run"
    loop_mod.main(_argv(
        out_dir=out_dir,
        bundle=inputs["bundle"],
        address_map=inputs["address_map"],
    ))
    state = json.loads(
        (out_dir / "operator_run.json").read_text(encoding="utf-8")
    )
    # Note: $defs structure is non-strict above; the artifact entries
    # use the entry shape via the artifacts.{step}: dict or list.
    # The strict object check above hits required/extra fields and
    # const flags, which is what we need.
    _validate(state, schema)
