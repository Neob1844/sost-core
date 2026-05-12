#!/usr/bin/env python3
"""Trinity / Useful Compute — Benchmark Ledger v0.1.

Runs a deterministic, local, stdlib-only micro-benchmark for one
(backend, task_type) pair and emits a benchmark report:

  TRINITY_USEFUL_COMPUTE_BENCHMARK_<benchmark_id>.json

The worker may consume that report via ``--benchmark-report`` to
override its reward-model inputs. The reward model treats placeholder
benchmarks as worth 0 stocks and sandbox_toy benchmarks as
experimental (manual review required). Real backends do not exist in
v0.1; the kind is reserved.

Hard invariants
---------------
- No network, no subprocess, no shell, no wallet, no keys.
- Worker identity is NEVER stored verbatim — only as
  ``worker_id_hash`` (sha16 of the worker_id).
- Machine identity is stored as ``machine_fingerprint_hash`` (sha16
  of platform.platform() + platform.machine() + platform.processor()).
- ``benchmark_id`` is deterministic over only the deterministic
  fields: backend (name, version, kind), task_type, iterations and
  deterministic_work_units. It does NOT include wall_time_seconds,
  worker_id_hash or machine_fingerprint_hash so two honest workers
  on different machines comparing the same backend produce the same
  benchmark_id.
- ``normalized_work_score`` is bounded to [0.1, 10.0] (matching the
  reward model's existing benchmark_score band).

What the benchmark IS NOT
-------------------------
- It is NOT a measure of scientific output quality.
- It is NOT a measure of correctness.
- It is NOT a proof-of-work in the consensus sense.

It is a comparable measurement of how much deterministic work a
specific backend does for a given iteration count on a given
machine. The reward model uses it as a normalisation factor, capped
by the per-task ``max_reward_stocks``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


SCHEMA_BENCHMARK = "trinity-useful-compute-benchmark/v0.1"

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent

# Bounds inherited from the existing reward model.
_NORMALIZED_MIN = 0.1
_NORMALIZED_MAX = 10.0

# Soft constant — divides deterministic_work_units / iterations into
# a 0..10 band where the placeholder backend lands near 1.0 and the
# heavier sandbox_toy backends land at 2..5.
_NORMALIZATION_DIVISOR = 100.0


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


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


def _backends_mod():
    return _load(
        "ucb_for_bench",
        _SCRIPTS_DIR / "useful_compute_backends.py",
    )


def _machine_fingerprint_hash() -> str:
    fp = "|".join((
        platform.platform(),
        platform.machine(),
        platform.processor() or "",
        platform.python_implementation(),
        platform.python_version(),
    ))
    return _sha16(fp)


def _fake_request(task_type: str) -> Dict[str, Any]:
    """Build a minimal request object the backend handler will
    accept. Only ``task_type`` is read by the registered backends."""
    return {
        "schema": "trinity-useful-compute-request/v0.1",
        "request_id": "uc-benchmark0000",
        "task_type": task_type,
    }


def run_benchmark(
    *,
    backend_name: str,
    task_type: str,
    iterations: int,
    worker_id: str,
    allow_experimental: bool = True,
) -> Dict[str, Any]:
    """Execute the micro-benchmark in-process. Returns the canonical
    report dict. The caller writes it to disk."""
    if iterations < 1 or iterations > 1_000_000:
        raise ValueError(
            f"iterations must be in [1, 1_000_000], got {iterations}"
        )
    if not (isinstance(worker_id, str) and 1 <= len(worker_id) <= 128):
        raise ValueError("worker_id must be 1..128 chars")

    backends = _backends_mod()
    spec = backends.select_backend(
        task_type=task_type,
        backend_name=backend_name,
        allow_experimental=allow_experimental,
    )

    request = _fake_request(task_type)
    work_acc = 0
    start_wall = time.monotonic()
    for i in range(iterations):
        # Each iteration runs the backend handler with a fresh seed.
        # The seed sequence is deterministic so the
        # deterministic_work_units field is stable across machines.
        result = backends.run_backend(
            spec,
            request=request,
            deterministic_seed=int(i),
        )
        blob = canonical_dumps(result.output_obj).encode("utf-8")
        work_acc = (work_acc + len(blob)) & ((1 << 64) - 1)
    wall_time = time.monotonic() - start_wall

    deterministic_work_units = int(work_acc)
    raw_score = (
        deterministic_work_units / max(1, iterations)
    ) / _NORMALIZATION_DIVISOR
    normalized_work_score = max(
        _NORMALIZED_MIN, min(_NORMALIZED_MAX, raw_score)
    )

    benchmark_id = "bench-" + _sha16(canonical_dumps({
        "backend_name":            spec.name,
        "backend_version":         spec.version,
        "backend_kind":            spec.kind,
        "task_type":               task_type,
        "iterations":              int(iterations),
        "deterministic_work_units": deterministic_work_units,
    }))

    report = {
        "schema": SCHEMA_BENCHMARK,
        "benchmark_id": benchmark_id,
        "mode": "local-dry-run",
        "backend_name":    spec.name,
        "backend_version": spec.version,
        "backend_kind":    spec.kind,
        "task_type":       task_type,
        "iterations":      int(iterations),
        "wall_time_seconds": round(float(wall_time), 6),
        "operations_count": int(iterations),
        "deterministic_work_units": deterministic_work_units,
        "normalized_work_score": round(float(normalized_work_score), 6),
        "machine_fingerprint_hash": _machine_fingerprint_hash(),
        "worker_id_hash":           _sha16(worker_id),
        "safety_status": {
            "no_wallet_access":    True,
            "no_private_keys":     True,
            "no_network_required": True,
            "no_automatic_payout": True,
            "benchmark_only":      True,
        },
    }
    return report


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="useful_compute_benchmark",
        description=(
            "Trinity Useful Compute benchmark ledger v0.1. "
            "Runs a deterministic local micro-benchmark for one "
            "(backend, task_type) pair and emits a benchmark report. "
            "NEVER pays, NEVER touches a wallet, NEVER broadcasts."
        ),
    )
    p.add_argument("--mode", required=True, choices=["local-dry-run"])
    p.add_argument("--backend", required=True)
    p.add_argument(
        "--task-type", required=True,
        choices=("dft", "quantum", "structure_relaxation",
                 "scoring", "simulation", "other"),
    )
    p.add_argument("--iterations", type=int, default=1000)
    p.add_argument("--worker-id", required=True)
    p.add_argument("--out-dir", required=True)

    # Hard-rejection guards.
    p.add_argument("--broadcast", action="store_true", help="REJECTED")
    p.add_argument("--payout",    action="store_true", help="REJECTED")
    p.add_argument("--send",      action="store_true", help="REJECTED")
    p.add_argument("--wallet",    type=str, default=None, help="REJECTED")
    p.add_argument("--network",   action="store_true", help="REJECTED")
    args = p.parse_args(argv)

    if args.mode != "local-dry-run":
        print(
            "[useful_compute_benchmark] only local-dry-run is "
            "supported in v0.1",
            file=sys.stderr,
        )
        return 2
    for flag_value, flag_name in (
        (args.broadcast, "--broadcast"),
        (args.payout,    "--payout"),
        (args.send,      "--send"),
        (args.network,   "--network"),
    ):
        if flag_value:
            print(
                f"[useful_compute_benchmark] flag {flag_name} is "
                "rejected in v0.1",
                file=sys.stderr,
            )
            return 2
    if args.wallet is not None:
        print(
            "[useful_compute_benchmark] --wallet is rejected in v0.1",
            file=sys.stderr,
        )
        return 2

    try:
        report = run_benchmark(
            backend_name=args.backend,
            task_type=args.task_type,
            iterations=args.iterations,
            worker_id=args.worker_id,
            allow_experimental=True,
        )
    except ValueError as exc:
        print(
            f"[useful_compute_benchmark] benchmark error: {exc}",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bid = report["benchmark_id"]
    out_path = (
        out_dir / f"TRINITY_USEFUL_COMPUTE_BENCHMARK_{bid}.json"
    )
    out_path.write_text(canonical_dumps(report), encoding="utf-8")

    print(
        f"[useful_compute_benchmark] benchmark_id={bid} "
        f"backend={report['backend_name']} "
        f"task_type={report['task_type']} "
        f"iterations={report['iterations']} "
        f"work_units={report['deterministic_work_units']} "
        f"score={report['normalized_work_score']}"
    )
    print(
        f"[useful_compute_benchmark] wall_time_seconds="
        f"{report['wall_time_seconds']} "
        f"machine={report['machine_fingerprint_hash']} "
        f"worker_hash={report['worker_id_hash']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
