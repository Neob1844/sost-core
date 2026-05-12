"""Trinity / Useful Compute benchmark ledger v0.1 — invariants."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "trinity"


def _load(modname, path):
    spec = importlib.util.spec_from_file_location(modname, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bench_mod():
    return _load(
        "ucb_bench", SCRIPTS_DIR / "useful_compute_benchmark.py",
    )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_benchmark_id_stable_across_worker_ids(bench_mod):
    a = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=100, worker_id="miner-A",
    )
    b = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=100, worker_id="miner-B",
    )
    assert a["benchmark_id"] == b["benchmark_id"]
    assert a["normalized_work_score"] == b["normalized_work_score"]
    assert a["deterministic_work_units"] == \
        b["deterministic_work_units"]
    # worker_id_hash differs because worker_id differs.
    assert a["worker_id_hash"] != b["worker_id_hash"]


def test_benchmark_id_changes_with_iterations(bench_mod):
    a = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=100, worker_id="m",
    )
    b = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=200, worker_id="m",
    )
    assert a["benchmark_id"] != b["benchmark_id"]


def test_benchmark_id_changes_with_backend(bench_mod):
    a = bench_mod.run_benchmark(
        backend_name="placeholder_scoring", task_type="scoring",
        iterations=100, worker_id="m",
    )
    b = bench_mod.run_benchmark(
        backend_name="local_python_numeric_v01", task_type="scoring",
        iterations=100, worker_id="m",
    )
    assert a["benchmark_id"] != b["benchmark_id"]
    assert a["backend_kind"] == "placeholder"
    assert b["backend_kind"] == "sandbox_toy"


def test_worker_id_never_appears_in_clear(bench_mod):
    """The benchmark report must NOT carry the worker_id verbatim;
    only worker_id_hash (sha16) is allowed."""
    raw = "miner-secret-001"
    report = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=10, worker_id=raw,
    )
    blob = json.dumps(report)
    assert raw not in blob, (
        "worker_id appeared verbatim in benchmark report"
    )
    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    assert report["worker_id_hash"] == expected


def test_normalized_work_score_within_bounds(bench_mod):
    for n in (1, 10, 1000):
        report = bench_mod.run_benchmark(
            backend_name="placeholder", task_type="scoring",
            iterations=n, worker_id="m",
        )
        s = report["normalized_work_score"]
        assert 0.1 <= s <= 10.0, (
            f"normalized_work_score {s} outside [0.1, 10.0]"
        )


def test_machine_fingerprint_hash_is_sha16(bench_mod):
    report = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=10, worker_id="m",
    )
    fp = report["machine_fingerprint_hash"]
    assert isinstance(fp, str) and len(fp) == 16
    # All hex
    assert all(c in "0123456789abcdef" for c in fp)


# ---------------------------------------------------------------------------
# Validation / rejection
# ---------------------------------------------------------------------------


def test_iterations_must_be_positive(bench_mod):
    with pytest.raises(ValueError, match="iterations"):
        bench_mod.run_benchmark(
            backend_name="placeholder", task_type="scoring",
            iterations=0, worker_id="m",
        )


def test_iterations_capped(bench_mod):
    with pytest.raises(ValueError, match="iterations"):
        bench_mod.run_benchmark(
            backend_name="placeholder", task_type="scoring",
            iterations=10_000_001, worker_id="m",
        )


def test_unknown_backend_rejected(bench_mod):
    with pytest.raises(ValueError, match="unknown backend"):
        bench_mod.run_benchmark(
            backend_name="not_a_backend", task_type="scoring",
            iterations=10, worker_id="m",
        )


def test_task_type_mismatch_rejected(bench_mod):
    # local_python_numeric_v01 supports scoring + simulation only.
    with pytest.raises(ValueError, match="does not support"):
        bench_mod.run_benchmark(
            backend_name="local_python_numeric_v01", task_type="dft",
            iterations=10, worker_id="m",
        )


def test_empty_worker_id_rejected(bench_mod):
    with pytest.raises(ValueError, match="worker_id"):
        bench_mod.run_benchmark(
            backend_name="placeholder", task_type="scoring",
            iterations=10, worker_id="",
        )


# ---------------------------------------------------------------------------
# CLI safety
# ---------------------------------------------------------------------------


def test_cli_rejects_non_local_mode(tmp_path, bench_mod):
    with pytest.raises(SystemExit):
        bench_mod.main([
            "--mode", "live", "--backend", "placeholder",
            "--task-type", "scoring", "--iterations", "10",
            "--worker-id", "m", "--out-dir", str(tmp_path),
        ])


def test_cli_rejects_payout(tmp_path, bench_mod):
    rc = bench_mod.main([
        "--mode", "local-dry-run", "--backend", "placeholder",
        "--task-type", "scoring", "--iterations", "10",
        "--worker-id", "m", "--out-dir", str(tmp_path),
        "--payout",
    ])
    assert rc == 2


def test_cli_rejects_broadcast(tmp_path, bench_mod):
    rc = bench_mod.main([
        "--mode", "local-dry-run", "--backend", "placeholder",
        "--task-type", "scoring", "--iterations", "10",
        "--worker-id", "m", "--out-dir", str(tmp_path),
        "--broadcast",
    ])
    assert rc == 2


def test_cli_rejects_wallet(tmp_path, bench_mod):
    rc = bench_mod.main([
        "--mode", "local-dry-run", "--backend", "placeholder",
        "--task-type", "scoring", "--iterations", "10",
        "--worker-id", "m", "--out-dir", str(tmp_path),
        "--wallet", "/dev/null",
    ])
    assert rc == 2


def test_cli_rejects_network(tmp_path, bench_mod):
    rc = bench_mod.main([
        "--mode", "local-dry-run", "--backend", "placeholder",
        "--task-type", "scoring", "--iterations", "10",
        "--worker-id", "m", "--out-dir", str(tmp_path),
        "--network",
    ])
    assert rc == 2


def test_cli_writes_benchmark_file(tmp_path, bench_mod):
    rc = bench_mod.main([
        "--mode", "local-dry-run", "--backend", "placeholder",
        "--task-type", "scoring", "--iterations", "10",
        "--worker-id", "miner-cli-001",
        "--out-dir", str(tmp_path),
    ])
    assert rc == 0
    files = list(tmp_path.glob(
        "TRINITY_USEFUL_COMPUTE_BENCHMARK_*.json"
    ))
    assert len(files) == 1
    obj = json.loads(files[0].read_text(encoding="utf-8"))
    assert obj["schema"] == "trinity-useful-compute-benchmark/v0.1"


# ---------------------------------------------------------------------------
# Safety status
# ---------------------------------------------------------------------------


def test_safety_status_const_true(bench_mod):
    report = bench_mod.run_benchmark(
        backend_name="placeholder", task_type="scoring",
        iterations=10, worker_id="m",
    )
    for flag in (
        "no_wallet_access", "no_private_keys",
        "no_network_required", "no_automatic_payout",
        "benchmark_only",
    ):
        assert report["safety_status"][flag] is True
