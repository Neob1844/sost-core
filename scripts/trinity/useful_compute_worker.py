#!/usr/bin/env python3
"""Trinity / Useful Compute — Local Dry-Run Worker v0.2.

Reads a ``trinity-useful-compute-request/v0.1`` manifest, validates
it against the request schema, executes a deterministic placeholder
task (NOT a real DFT / quantum simulation), and emits two files:

- ``TRINITY_USEFUL_COMPUTE_RESULT_<request_id>_<worker_result_id>.json``
- ``TRINITY_USEFUL_COMPUTE_PENDING_REWARD_<request_id>_<worker_result_id>.json``

v0.2 introduces a clean split between worker-independent and
worker-dependent identifiers:

- ``compute_output_sha256``: SHA-256 of the pure technical output.
  Depends ONLY on (request_id, input_bundle_sha256) so that two
  honest workers running the same task on the same input reach the
  same hash. This is the field the cross-worker replay validator
  groups by.
- ``worker_result_id``: 16-hex id binding (request_id, worker_id,
  compute_output_sha256, elapsed_seconds). Unique per submission.

Hard invariants
---------------
- Only ``--mode local-dry-run`` is accepted.
- The worker never broadcasts, signs, sends, or pays.
- No network calls. No subprocess invocations. No wallet/private-key
  imports.
- The placeholder task output is byte-identical across runs for the
  same (request_id, input_bundle_sha256). Worker identity does NOT
  perturb the technical output.
- The pending reward is computed via
  ``useful_compute_reward_model.compute_pending_reward``; it is a
  *report*, never an on-chain payout.
- ``duplicate_result`` is decided by an optional, on-disk seen-set
  of ``compute_output_sha256`` values passed via ``--seen-results``.

Real DFT / quantum back-ends will plug in later sprints behind
explicit feature flags; the schemas are forward-compatible.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_RESULT = "trinity-useful-compute-result/v0.3"
SCHEMA_PENDING_REWARD = "trinity-useful-compute-pending-reward/v0.2"
SCHEMA_REQUEST = "trinity-useful-compute-request/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_REQUEST_SCHEMA_PATH = (
    _REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_request.schema.json"
)
_RESULT_SCHEMA_PATH = (
    _REPO_ROOT / "schemas" / "trinity"
    / "useful_compute_result.schema.json"
)

_TASK_TYPES = (
    "dft", "quantum", "structure_relaxation",
    "scoring", "simulation", "other",
)

_DIFFICULTY_TIERS = ("low", "medium", "high", "extreme")


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha256_hex(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _load(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Minimal hand-rolled request validator (avoid jsonschema dependency)
# ---------------------------------------------------------------------------


_REQ_REQUIRED = {
    "schema", "request_id", "source_tool", "candidate_id",
    "task_type", "input_bundle_sha256", "expected_output_schema",
    "validation_method", "estimated_compute_cost",
    "max_reward_stocks", "deadline", "manual_review_required",
    "public_description",
}


def validate_request(request: Dict[str, Any]) -> None:
    """Validate a v0.1 request manifest. Raises ValueError on the
    first violation. Strict: rejects unknown keys, wrong types,
    missing required fields and out-of-range values."""
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")

    missing = _REQ_REQUIRED - set(request.keys())
    if missing:
        raise ValueError(
            f"request missing required fields: {sorted(missing)}"
        )

    if request.get("schema") != SCHEMA_REQUEST:
        raise ValueError(
            f"request.schema must be {SCHEMA_REQUEST!r}, "
            f"got {request.get('schema')!r}"
        )

    rid = request.get("request_id", "")
    if not (isinstance(rid, str) and re.match(r"^uc-[0-9a-f]{16,64}$", rid)):
        raise ValueError(f"request_id has wrong format: {rid!r}")

    src = request.get("source_tool")
    if src not in (
        "materials_engine", "geaspirit", "trinity_orchestrator",
    ):
        raise ValueError(f"unknown source_tool: {src!r}")

    tt = request.get("task_type")
    if tt not in _TASK_TYPES:
        raise ValueError(f"unknown task_type: {tt!r}")

    sha = request.get("input_bundle_sha256", "")
    if not (isinstance(sha, str) and re.match(r"^[0-9a-f]{64}$", sha)):
        raise ValueError("input_bundle_sha256 must be 64-hex lower")

    eos = request.get("expected_output_schema")
    if not (isinstance(eos, str) and len(eos) >= 1):
        raise ValueError("expected_output_schema must be a non-empty string")

    vm = request.get("validation_method")
    if vm not in (
        "redundant_replay", "cross_worker_consensus",
        "deterministic_hash_check", "manual_review",
    ):
        raise ValueError(f"unknown validation_method: {vm!r}")

    cost = request.get("estimated_compute_cost", {})
    if not isinstance(cost, dict):
        raise ValueError("estimated_compute_cost must be an object")
    sec = cost.get("seconds")
    if not (isinstance(sec, int) and 1 <= sec <= 86400):
        raise ValueError("estimated_compute_cost.seconds out of range")
    tier = cost.get("tier")
    if tier not in _DIFFICULTY_TIERS:
        raise ValueError(f"estimated_compute_cost.tier: {tier!r}")

    mrs = request.get("max_reward_stocks")
    if not (isinstance(mrs, int) and 0 <= mrs <= 1000000):
        raise ValueError("max_reward_stocks out of range")

    deadline = request.get("deadline")
    if not (isinstance(deadline, str) and len(deadline) >= 10):
        raise ValueError("deadline must be an ISO-8601 timestamp string")

    mrr = request.get("manual_review_required")
    if not isinstance(mrr, bool):
        raise ValueError("manual_review_required must be boolean")

    pd = request.get("public_description")
    if not (isinstance(pd, str) and 8 <= len(pd) <= 512):
        raise ValueError("public_description length out of range")

    pn = request.get("private_notes")
    if pn is not None and not (isinstance(pn, str) and len(pn) <= 2048):
        raise ValueError("private_notes too long or wrong type")

    allowed = _REQ_REQUIRED | {"private_notes"}
    unknown = set(request.keys()) - allowed
    if unknown:
        raise ValueError(
            f"request has unknown fields: {sorted(unknown)}"
        )


# ---------------------------------------------------------------------------
# Placeholder task handlers — deterministic, honest, not real science
# ---------------------------------------------------------------------------


def _compute_seed(
    request_id: str, input_bundle_sha256: str,
) -> int:
    """Return a stable 64-bit int seed derived ONLY from the
    request_id and the input_bundle_sha256.

    Critically, the seed does NOT include worker_id. Two honest
    workers running the same task on the same input must reach the
    same placeholder output bytes so the replay validator can match
    them. Worker identity is bound later via worker_result_id.
    """
    blob = canonical_dumps({
        "rid": request_id, "sha": input_bundle_sha256,
    }).encode("utf-8")
    return int.from_bytes(hashlib.sha256(blob).digest()[:8], "big")


# The actual task handlers live in
# scripts/trinity/useful_compute_backends.py. The worker imports that
# module lazily (so unit tests that patch the registry can do so before
# run_worker is called).
def _backends_mod():
    return _load(
        "ucw_backends",
        _SCRIPTS_DIR / "useful_compute_backends.py",
    )


# ---------------------------------------------------------------------------
# Duplicate detection (local seen-set, append-only)
# ---------------------------------------------------------------------------


def _is_duplicate(
    seen_path: Optional[Path], output_sha256: str,
) -> bool:
    if seen_path is None or not seen_path.exists():
        return False
    for raw in seen_path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw == output_sha256:
            return True
    return False


def _record_seen(seen_path: Optional[Path], output_sha256: str) -> None:
    if seen_path is None:
        return
    with seen_path.open("a", encoding="utf-8") as fh:
        fh.write(output_sha256 + "\n")


# ---------------------------------------------------------------------------
# Core: run a single request
# ---------------------------------------------------------------------------


def run_worker(
    *,
    request: Dict[str, Any],
    worker_id: str,
    out_dir: Path,
    pinned_time: str,
    seen_results: Optional[Path] = None,
    input_bundle_path: Optional[Path] = None,
    backend_name: str = "placeholder",
    allow_experimental_backends: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Execute one request in local-dry-run mode. Returns (result,
    pending_reward_report) and writes both to disk."""

    validate_request(request)
    out_dir.mkdir(parents=True, exist_ok=True)

    rid = request["request_id"]
    task_type = request["task_type"]
    input_sha = request["input_bundle_sha256"]
    max_reward = int(request["max_reward_stocks"])
    tier = request["estimated_compute_cost"]["tier"]

    # If the caller supplied a bundle file, verify its SHA matches.
    if input_bundle_path is not None:
        actual_sha = _sha256_hex(input_bundle_path.read_bytes())
        if actual_sha != input_sha:
            raise ValueError(
                "input bundle sha256 mismatch: "
                f"declared={input_sha} actual={actual_sha}"
            )

    # 1) Resolve backend. Placeholder is the default; experimental
    #    backends require an explicit opt-in flag.
    backends = _backends_mod()
    spec = backends.select_backend(
        task_type=task_type,
        backend_name=backend_name,
        allow_experimental=bool(allow_experimental_backends),
    )

    # 2) Pure technical output — depends ONLY on the task contract
    #    (request_id + input bundle sha). Worker identity does NOT
    #    influence these bytes. Two workers using the SAME backend on
    #    the SAME request MUST reach the same compute_output_sha256.
    seed64 = _compute_seed(rid, input_sha)
    backend_result = backends.run_backend(
        spec,
        request=request,
        deterministic_seed=seed64,
        input_bundle_bytes=None,
    )
    output_blob = canonical_dumps(
        backend_result.output_obj
    ).encode("utf-8")
    compute_output_sha = _sha256_hex(output_blob)

    # 3) Duplicate detection lives at the compute layer (same
    #    technical output across submissions). Worker identity is
    #    irrelevant to "did we already see this result?".
    duplicate = _is_duplicate(seen_results, compute_output_sha)
    result_validated = len(output_blob) > 0

    # 4) Elapsed seconds — pinned to the request's estimated cost in
    #    v0.x. Real timers come later when outputs are anchored to
    #    wall-clock checkpoints. backend_runtime_seconds carries the
    #    actual measured runtime (pinned to 0.0 for placeholder so
    #    byte-identical tests on placeholder stay stable).
    elapsed = float(request["estimated_compute_cost"]["seconds"])

    # 5) worker_result_id binds (request, worker, compute output,
    #    elapsed) into one 16-hex submission id. This IS worker-
    #    dependent by design: two workers on the same task must get
    #    different worker_result_id values while still sharing
    #    compute_output_sha256.
    worker_result_id = _sha16(canonical_dumps({
        "rid": rid,
        "wid": worker_id,
        "compute_sha": compute_output_sha,
        "elapsed": elapsed,
    }))

    result = {
        "schema": SCHEMA_RESULT,
        "request_id": rid,
        "worker_id": worker_id,
        "task_type": task_type,
        "input_bundle_sha256": input_sha,
        "compute_output_sha256": compute_output_sha,
        "worker_result_id": worker_result_id,
        "started_at": pinned_time,
        "finished_at": pinned_time,
        "elapsed_seconds": elapsed,
        "result_validated": bool(result_validated),
        "duplicate_result": bool(duplicate),
        "public_summary": (
            f"{spec.kind} {spec.name} {task_type} result for {rid} "
            f"by {worker_id}; deterministic, not real scientific "
            "validation; pending verification."
        ),
        "backend_name":            spec.name,
        "backend_version":         spec.version,
        "backend_kind":            spec.kind,
        "backend_disclaimer":      spec.disclaimer,
        "backend_runtime_seconds": float(backend_result.runtime_seconds),
        "safety_status": {
            "no_wallet_access":       True,
            "no_private_keys":        True,
            "no_automatic_payout":    True,
            "no_network_required":    True,
            "manual_review_required": True,
        },
    }

    # Reward model report.
    reward_mod = _load(
        "uc_worker_reward",
        _SCRIPTS_DIR / "useful_compute_reward_model.py",
    )
    pending = reward_mod.compute_pending_reward(
        task_id=rid,
        worker_id=worker_id,
        benchmark_score=1.0,
        verified_compute_seconds=elapsed,
        difficulty_class=tier,
        result_validated=bool(result_validated),
        duplicate_result=bool(duplicate),
        max_reward_stocks=max_reward,
    )

    # Pending reward v0.2 carries backend identity so downstream
    # consumers (governance gate, web console) can group rewards by
    # backend without needing to load the full result file.
    pending_report = {
        "schema": SCHEMA_PENDING_REWARD,
        "request_id": rid,
        "worker_id": worker_id,
        "worker_result_id": worker_result_id,
        "pending_reward_stocks": pending["pending_reward_stocks"],
        "reason": pending["reason"],
        "requires_manual_review": pending["requires_manual_review"],
        "reward_model_schema": pending["schema"],
        "reward_model_deterministic_id": pending["deterministic_id"],
        "backend_name":    spec.name,
        "backend_version": spec.version,
        "backend_kind":    spec.kind,
        "safety_status": {
            "no_wallet_access":       True,
            "no_private_keys":        True,
            "no_automatic_payout":    True,
            "no_network_required":    True,
            "manual_review_required": True,
        },
    }

    # File names embed worker_result_id so that multiple workers
    # can drop their submissions into the same directory without
    # clobbering each other. The replay validator scans for the
    # request_id prefix and groups all matches.
    result_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_RESULT_{rid}_{worker_result_id}.json"
    )
    reward_path = (
        out_dir
        / f"TRINITY_USEFUL_COMPUTE_PENDING_REWARD_{rid}_{worker_result_id}.json"
    )
    result_path.write_text(canonical_dumps(result), encoding="utf-8")
    reward_path.write_text(canonical_dumps(pending_report), encoding="utf-8")

    # Record output in the seen-set AFTER writing.
    _record_seen(seen_results, compute_output_sha)

    return result, pending_report


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_worker",
        description=(
            "Trinity Useful Compute local-dry-run worker v0.1. "
            "Runs a deterministic placeholder for the requested "
            "task_type and emits a pending-reward report. "
            "Never pays, never signs, never broadcasts."
        ),
    )
    p.add_argument(
        "--request", required=True,
        help="Path to TRINITY_USEFUL_COMPUTE_REQUEST_<id>.json",
    )
    p.add_argument(
        "--worker-id", required=True,
        help="Local worker identifier (free-form, ≤128 chars)",
    )
    p.add_argument(
        "--out-dir", required=True,
        help="Directory to write the result + pending reward",
    )
    p.add_argument(
        "--mode", required=True, choices=["local-dry-run"],
        help="v0.1 only supports local-dry-run",
    )
    p.add_argument(
        "--pinned-time", default="2026-05-12T00:00:00+00:00",
        help="Pinned ISO-8601 timestamp for started_at/finished_at",
    )
    p.add_argument(
        "--seen-results", default=None,
        help=(
            "Optional path to an append-only list of previously "
            "observed output SHAs. Used to flag duplicate_result."
        ),
    )
    p.add_argument(
        "--input-bundle", default=None,
        help=(
            "Optional path to the actual input bundle file. When "
            "supplied, the worker verifies its SHA matches the "
            "request manifest before running the task."
        ),
    )
    p.add_argument(
        "--backend", default="placeholder",
        help=(
            "Backend name to use. Default 'placeholder' resolves to "
            "placeholder_<task_type>. Sandbox toy backends require "
            "--allow-experimental-backends."
        ),
    )
    p.add_argument(
        "--allow-experimental-backends", action="store_true",
        help=(
            "Opt-in flag required to use experimental sandbox_toy "
            "backends. Without this flag any non-placeholder backend "
            "is rejected with a clear error."
        ),
    )

    # Hard-rejection guards for flags the user might add.
    p.add_argument("--broadcast", action="store_true",
                   help="REJECTED in v0.1")
    p.add_argument("--payout",    action="store_true",
                   help="REJECTED in v0.1")
    p.add_argument("--send",      action="store_true",
                   help="REJECTED in v0.1")
    p.add_argument("--wallet",    type=str, default=None,
                   help="REJECTED in v0.1")
    p.add_argument("--network",   action="store_true",
                   help="REJECTED in v0.1")
    p.add_argument(
        "--worker-id-from-wallet", action="store_true",
        help="REJECTED in v0.1",
    )

    args = p.parse_args(argv)

    if args.mode != "local-dry-run":
        print(
            "[useful_compute_worker] only --mode local-dry-run is "
            "supported in v0.1",
            file=sys.stderr,
        )
        return 2
    for forbidden_flag, name in (
        (args.broadcast, "--broadcast"),
        (args.payout,    "--payout"),
        (args.send,      "--send"),
        (args.network,   "--network"),
        (args.worker_id_from_wallet, "--worker-id-from-wallet"),
    ):
        if forbidden_flag:
            print(
                f"[useful_compute_worker] flag {name} is rejected in v0.1",
                file=sys.stderr,
            )
            return 2
    if args.wallet is not None:
        print(
            "[useful_compute_worker] --wallet is rejected in v0.1; "
            "this worker NEVER touches wallets or private keys",
            file=sys.stderr,
        )
        return 2

    if len(args.worker_id) < 1 or len(args.worker_id) > 128:
        print(
            "[useful_compute_worker] --worker-id must be 1..128 chars",
            file=sys.stderr,
        )
        return 2

    request_path = Path(args.request)
    if not request_path.exists():
        print(
            f"[useful_compute_worker] request not found: {request_path}",
            file=sys.stderr,
        )
        return 2

    request = json.loads(request_path.read_text(encoding="utf-8"))
    try:
        result, pending = run_worker(
            request=request,
            worker_id=args.worker_id,
            out_dir=Path(args.out_dir),
            pinned_time=args.pinned_time,
            seen_results=(
                Path(args.seen_results) if args.seen_results else None
            ),
            input_bundle_path=(
                Path(args.input_bundle) if args.input_bundle else None
            ),
            backend_name=args.backend,
            allow_experimental_backends=bool(
                args.allow_experimental_backends
            ),
        )
    except ValueError as exc:
        print(
            f"[useful_compute_worker] backend error: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        f"[useful_compute_worker] mode=local-dry-run "
        f"request_id={result['request_id']} worker_id={result['worker_id']}"
    )
    print(
        f"[useful_compute_worker] task_type={result['task_type']} "
        f"compute_output_sha256={result['compute_output_sha256']}"
    )
    print(
        f"[useful_compute_worker] worker_result_id={result['worker_result_id']}"
    )
    print(
        f"[useful_compute_worker] elapsed_seconds={result['elapsed_seconds']} "
        f"validated={result['result_validated']} "
        f"duplicate={result['duplicate_result']}"
    )
    print(
        f"[useful_compute_worker] pending_reward_stocks="
        f"{pending['pending_reward_stocks']} "
        f"reason={pending['reason']!r} "
        f"manual_review={pending['requires_manual_review']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
