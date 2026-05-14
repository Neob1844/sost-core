"""Trinity end-to-end pipeline (Sprint 5.22b regression).

Reproduces the user-reported failure where the worker rejected
requests built from a scientific intake with:

  [useful_compute_worker] backend error:
    unknown source_tool: 'trinity_scientific_prompt_intake'

The full chain that must complete:

  scientific_prompt_intake.py
    -> useful_compute_task_builder.py --from-scientific-intake
       -> useful_compute_operator_loop.py --request-json
          -> task_builder (imported)
             -> worker x N
                -> replay_validator
                   -> governance_gate
                      -> reward_budget_policy
                         -> payment_proposal
                            -> payment_draft (unsigned-only)
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
def intake_mod():
    return _load(
        "e2e_intake", SCRIPTS_DIR / "scientific_prompt_intake.py",
    )


@pytest.fixture(scope="module")
def builder_mod():
    return _load(
        "e2e_builder",
        SCRIPTS_DIR / "useful_compute_task_builder.py",
    )


@pytest.fixture(scope="module")
def loop_mod():
    return _load(
        "e2e_loop",
        SCRIPTS_DIR / "useful_compute_operator_loop.py",
    )


@pytest.fixture(scope="module")
def worker_mod():
    return _load(
        "e2e_worker", SCRIPTS_DIR / "useful_compute_worker.py",
    )


@pytest.fixture(scope="module")
def backends_mod():
    return _load(
        "e2e_backends", SCRIPTS_DIR / "useful_compute_backends.py",
    )


OPERATOR_TOKEN = "I_UNDERSTAND_THIS_IS_ONLY_A_DRY_RUN_LOOP"
PINNED = "2026-05-13T00:00:00+00:00"


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _hex_address(seed: str) -> str:
    body = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:40]
    return "sost1" + body


def _make_address_map(tmp_path: Path) -> Path:
    obj = {
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
    p = tmp_path / "address_map.json"
    p.write_text(
        json.dumps(obj, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return p


def _make_docs(tmp_path: Path) -> List[Path]:
    a = tmp_path / "note.md"
    b = tmp_path / "data.txt"
    a.write_text(
        "# Ceria\n\nOxygen storage capacity is high.",
        encoding="utf-8",
    )
    b.write_text(
        "praseodymia non-stoichiometric phases.",
        encoding="utf-8",
    )
    return [a, b]


def _run_intake(intake_mod, tmp_path: Path) -> Path:
    out_dir = tmp_path / "intake_out"
    docs = _make_docs(tmp_path)
    argv = [
        "--mode", "local-dry-run",
        "--prompt",
        "Compare ceria and praseodymia oxygen storage capacity.",
        "--out-dir", str(out_dir),
        "--pinned-time", PINNED,
    ]
    for d in docs:
        argv += ["--document", str(d)]
    rc = intake_mod.main(argv)
    assert rc == 0
    files = list(
        out_dir.glob("TRINITY_SCIENTIFIC_PROMPT_INTAKE_*.json")
    )
    assert len(files) == 1
    return files[0]


def _run_builder(
    builder_mod, *, intake_path: Path, out_json: Path,
) -> Path:
    rc = builder_mod.main([
        "--from-scientific-intake", str(intake_path),
        "--intake-task-kind", "comparison",
        "--intake-output-schema",
        "trinity-useful-compute-result/v0.4",
        "--difficulty-class", "low",
        "--deadline", "2026-06-30T00:00:00+00:00",
        "--max-reward-stocks", "100000",
        "--out-json", str(out_json),
    ])
    assert rc == 0
    return out_json


def _run_operator_loop(
    loop_mod, *, request_json: Path, address_map: Path,
    out_dir: Path,
) -> Path:
    rc = loop_mod.main([
        "--mode", "local-dry-run",
        "--out-dir", str(out_dir),
        "--require-confirmation-token", OPERATOR_TOKEN,
        "--worker-address-map", str(address_map),
        "--max-total-stocks", "1000000",
        "--pool-balance-stocks", "10000000",
        "--pinned-time", PINNED,
        "--request-json", str(request_json),
    ])
    assert rc == 0, (
        "operator loop failed; this was the regression: "
        "worker rejected the scientific-intake source_tool"
    )
    return out_dir / "operator_run.json"


# ---------------------------------------------------------------------------
# Worker-level regression (the exact symptom the user hit)
# ---------------------------------------------------------------------------


def test_worker_accepts_scientific_intake_source_tool(
    tmp_path, intake_mod, builder_mod, worker_mod,
):
    intake = _run_intake(intake_mod, tmp_path)
    req_path = tmp_path / "request.json"
    _run_builder(
        builder_mod, intake_path=intake, out_json=req_path,
    )
    req = json.loads(req_path.read_text(encoding="utf-8"))
    # validate_request must NOT raise on the new source_tool +
    # task_type + metadata.
    worker_mod.validate_request(req)


def test_worker_rejects_scientific_intake_without_metadata(
    tmp_path, intake_mod, builder_mod, worker_mod,
):
    intake = _run_intake(intake_mod, tmp_path)
    req_path = tmp_path / "request.json"
    _run_builder(
        builder_mod, intake_path=intake, out_json=req_path,
    )
    req = json.loads(req_path.read_text(encoding="utf-8"))
    # Strip metadata; validate_request must refuse.
    req.pop("metadata", None)
    import pytest as _pytest
    with _pytest.raises(ValueError, match="scientific_intake"):
        worker_mod.validate_request(req)


def test_worker_rejects_scientific_intake_with_bad_metadata(
    tmp_path, intake_mod, builder_mod, worker_mod,
):
    intake = _run_intake(intake_mod, tmp_path)
    req_path = tmp_path / "request.json"
    _run_builder(
        builder_mod, intake_path=intake, out_json=req_path,
    )
    req = json.loads(req_path.read_text(encoding="utf-8"))
    req["metadata"]["scientific_intake"]["intake_id"] = \
        "not-spi-style"
    import pytest as _pytest
    with _pytest.raises(ValueError, match="intake_id"):
        worker_mod.validate_request(req)


def test_two_workers_produce_identical_compute_output_sha256(
    tmp_path, intake_mod, builder_mod, worker_mod,
):
    """The cross-worker replay contract holds for the new
    scientific_intake task: two workers given the same request
    produce byte-identical compute outputs, so their compute hashes
    match."""
    intake = _run_intake(intake_mod, tmp_path)
    req_path = tmp_path / "request.json"
    _run_builder(
        builder_mod, intake_path=intake, out_json=req_path,
    )
    req = json.loads(req_path.read_text(encoding="utf-8"))

    out_a = tmp_path / "wa"
    out_b = tmp_path / "wb"
    res_a, _ = worker_mod.run_worker(
        request=req, worker_id="worker-A", out_dir=out_a,
        pinned_time=PINNED, backend_name="placeholder",
    )
    res_b, _ = worker_mod.run_worker(
        request=req, worker_id="worker-B", out_dir=out_b,
        pinned_time=PINNED, backend_name="placeholder",
    )
    assert res_a["compute_output_sha256"] == \
        res_b["compute_output_sha256"], (
            "two workers on the same scientific_intake request "
            "must produce identical compute output hashes"
        )


def test_backend_output_carries_intake_identifiers(
    tmp_path, intake_mod, builder_mod, backends_mod,
):
    intake = _run_intake(intake_mod, tmp_path)
    intake_obj = json.loads(intake.read_text(encoding="utf-8"))
    req_path = tmp_path / "request.json"
    _run_builder(
        builder_mod, intake_path=intake, out_json=req_path,
    )
    req = json.loads(req_path.read_text(encoding="utf-8"))
    spec = backends_mod.select_backend(
        task_type="scientific_intake",
        backend_name="placeholder",
        allow_experimental=False,
    )
    br = backends_mod.run_backend(
        spec, request=req, deterministic_seed=0xDEAD_BEEF,
    )
    out = br.output_obj
    assert out["kind"] == "placeholder_scientific_intake_v0"
    assert out["source_tool"] == "trinity_scientific_prompt_intake"
    assert out["task_type"] == "scientific_intake"
    assert out["request_id"] == req["request_id"]
    assert out["input_bundle_sha256"] == req["input_bundle_sha256"]
    assert out["intake_id"] == intake_obj["intake_id"]
    assert out["combined_context_sha256"] == \
        intake_obj["combined_context_sha256"]
    assert out["prompt_sha256"] == intake_obj["prompt_sha256"]
    assert out["documents_count"] == \
        intake_obj["documents_count"]
    assert out["intake_task_kind"] == "comparison"
    assert out["validation_status"] == "hash_manifest_only"


# ---------------------------------------------------------------------------
# Full end-to-end through operator loop
# ---------------------------------------------------------------------------


def test_full_scientific_pipeline_completes_through_payment_draft(
    tmp_path, intake_mod, builder_mod, loop_mod,
):
    """Regression for the user-reported e2e failure. The full chain
    intake → task_builder --from-scientific-intake →
    operator_loop --request-json must run all seven steps and end
    in an unsigned payment draft."""
    intake = _run_intake(intake_mod, tmp_path)
    req_path = tmp_path / "request.json"
    _run_builder(
        builder_mod, intake_path=intake, out_json=req_path,
    )
    addr_map = _make_address_map(tmp_path)
    state_path = _run_operator_loop(
        loop_mod, request_json=req_path,
        address_map=addr_map, out_dir=tmp_path / "oprun",
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["steps_completed"] == [
        "task_builder", "worker", "replay_validator",
        "governance_gate", "reward_budget_policy",
        "payment_proposal", "payment_draft",
    ]
    assert state["request_source"] == "existing_request"
    # The final payment_draft must be unsigned-only.
    drafts = list(
        (tmp_path / "oprun" / "draft").glob(
            "TRINITY_USEFUL_COMPUTE_PAYMENT_DRAFT_*.json"
        )
    )
    assert len(drafts) == 1
    draft = json.loads(drafts[0].read_text(encoding="utf-8"))
    assert draft["signing_mode"] == "unsigned_only"
    assert draft["real_signed"] is False
    assert draft["safety_status"]["no_broadcast"] is True


def test_e2e_scientific_pipeline_is_deterministic(
    tmp_path, intake_mod, builder_mod, loop_mod,
):
    """Two complete runs from the same scientific inputs produce
    the same operator_run_id."""
    intake = _run_intake(intake_mod, tmp_path)
    req_path = tmp_path / "request.json"
    _run_builder(
        builder_mod, intake_path=intake, out_json=req_path,
    )
    addr_map = _make_address_map(tmp_path)

    sp1 = _run_operator_loop(
        loop_mod, request_json=req_path,
        address_map=addr_map, out_dir=tmp_path / "run1",
    )
    sp2 = _run_operator_loop(
        loop_mod, request_json=req_path,
        address_map=addr_map, out_dir=tmp_path / "run2",
    )
    s1 = json.loads(sp1.read_text(encoding="utf-8"))
    s2 = json.loads(sp2.read_text(encoding="utf-8"))
    assert s1["operator_run_id"] == s2["operator_run_id"]
    assert s1["source_request_sha256"] == \
        s2["source_request_sha256"]
