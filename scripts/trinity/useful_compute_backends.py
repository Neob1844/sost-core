#!/usr/bin/env python3
"""Trinity / Useful Compute — Backend Adapter Registry v0.1.

A single place where every Useful Compute backend is registered.
Sprint 5.12 introduces two kinds of backend:

- ``placeholder`` (default): the deterministic, zero-cost handlers
  that Sprint 5.7 shipped inside ``useful_compute_worker.py``. They
  are moved here so the worker becomes a thin orchestrator.
- ``sandbox_toy`` (opt-in, ``--allow-experimental-backends``): three
  local, deterministic, stdlib-only toy backends that perform more
  substantial computation than the placeholders but are NOT real
  scientific simulators. Honest disclaimers are attached to every
  result.

There is NO ``real_backend`` kind in v0.1. The enum reserves it for
future sprints that plug in actual DFT / quantum / simulation
back-ends.

Hard invariants
---------------
- Pure Python stdlib. No subprocess, no shell, no network, no third-
  party scientific packages.
- All backends are deterministic functions of
  ``(request_id, input_bundle_sha256)`` — worker identity does NOT
  perturb the technical output. This preserves the Sprint 5.8
  cross-worker replay contract.
- Backend selection happens through ``select_backend()``; the
  experimental check is enforced here, not in the worker.
- ``BackendResult.runtime_seconds`` is wall-clock for sandbox toys
  and pinned to ``0.0`` for placeholders so byte-identical tests on
  placeholder remain stable.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Dict, List, Optional


PLACEHOLDER_KIND  = "placeholder"
SANDBOX_TOY_KIND  = "sandbox_toy"
REAL_BACKEND_KIND = "real_backend"   # reserved; no backend uses this in v0.1

_BACKEND_KINDS = (PLACEHOLDER_KIND, SANDBOX_TOY_KIND, REAL_BACKEND_KIND)

_TASK_TYPES = (
    "dft", "quantum", "structure_relaxation",
    "scoring", "simulation", "other",
)


# ---------------------------------------------------------------------------
# Spec + result types (lightweight; no external deps)
# ---------------------------------------------------------------------------


class BackendSpec:
    """Static metadata for one backend implementation."""
    __slots__ = (
        "name", "version", "kind", "task_types",
        "disclaimer", "experimental",
    )

    def __init__(
        self, *,
        name: str,
        version: str,
        kind: str,
        task_types: List[str],
        disclaimer: str,
        experimental: bool,
    ) -> None:
        if kind not in _BACKEND_KINDS:
            raise ValueError(f"unknown backend kind: {kind!r}")
        for t in task_types:
            if t not in _TASK_TYPES:
                raise ValueError(f"unknown task_type: {t!r}")
        self.name = name
        self.version = version
        self.kind = kind
        self.task_types = list(task_types)
        self.disclaimer = disclaimer
        self.experimental = experimental

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name":         self.name,
            "version":      self.version,
            "kind":         self.kind,
            "task_types":   list(self.task_types),
            "disclaimer":   self.disclaimer,
            "experimental": bool(self.experimental),
        }


class BackendResult:
    """Carries the technical output plus wall-clock metrics."""
    __slots__ = ("output_obj", "runtime_seconds", "spec")

    def __init__(
        self, *,
        output_obj: Dict[str, Any],
        runtime_seconds: float,
        spec: BackendSpec,
    ) -> None:
        self.output_obj = output_obj
        self.runtime_seconds = float(runtime_seconds)
        self.spec = spec


# ---------------------------------------------------------------------------
# Placeholder backends (moved from useful_compute_worker.py)
# ---------------------------------------------------------------------------


def _placeholder_dft(seed64: int) -> Dict[str, Any]:
    energies = []
    s = seed64
    for _ in range(16):
        s = (s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        energies.append(round(((s >> 32) / (1 << 32)) * 20.0 - 10.0, 6))
    return {
        "kind": "placeholder_dft_spectrum_v0",
        "note": "deterministic placeholder; not real DFT",
        "n_levels": 16,
        "energies_ev": energies,
    }


def _placeholder_quantum(seed64: int) -> Dict[str, Any]:
    s = seed64
    bits = []
    for _ in range(32):
        s = (s * 2862933555777941757 + 3037000493) & ((1 << 64) - 1)
        bits.append(int(s & 1))
    return {
        "kind": "placeholder_quantum_register_v0",
        "note": "deterministic placeholder; not a quantum simulator",
        "n_qubits": 32,
        "measurement_bits": bits,
    }


def _placeholder_structure_relaxation(seed64: int) -> Dict[str, Any]:
    s = seed64
    coords = []
    for _ in range(8):
        triple = []
        for _ in range(3):
            s = (s * 1103515245 + 12345) & ((1 << 64) - 1)
            triple.append(round((s & 0xFFFF) / 65535.0 * 8.0 - 4.0, 4))
        coords.append(triple)
    return {
        "kind": "placeholder_relaxed_coords_v0",
        "note": "deterministic placeholder; not a real relaxation",
        "atoms": 8,
        "coords_angstrom": coords,
    }


def _placeholder_scoring(seed64: int) -> Dict[str, Any]:
    s = seed64
    score = ((s >> 16) & 0xFFFF) / 65535.0
    return {
        "kind": "placeholder_scoring_v0",
        "note": "deterministic placeholder; not a real scoring run",
        "score_0_1": round(score, 6),
    }


def _placeholder_simulation(seed64: int) -> Dict[str, Any]:
    s = seed64
    steps = []
    val = (s & 0xFFFF) / 65535.0
    for _ in range(10):
        s = (s * 48271) & 0x7FFFFFFF
        val = round((val * 0.7 + (s & 0xFFFF) / 65535.0 * 0.3), 6)
        steps.append(val)
    return {
        "kind": "placeholder_simulation_v0",
        "note": "deterministic placeholder; not a real simulation",
        "steps": steps,
    }


def _placeholder_other(seed64: int) -> Dict[str, Any]:
    return {
        "kind": "placeholder_generic_v0",
        "note": "deterministic placeholder for task_type=other",
        "marker_hex": f"{seed64:016x}",
    }


_PLACEHOLDER_HANDLERS = {
    "dft":                   _placeholder_dft,
    "quantum":               _placeholder_quantum,
    "structure_relaxation":  _placeholder_structure_relaxation,
    "scoring":               _placeholder_scoring,
    "simulation":            _placeholder_simulation,
    "other":                 _placeholder_other,
}


# ---------------------------------------------------------------------------
# Sandbox toy backends — opt-in, deterministic, stdlib only
# ---------------------------------------------------------------------------
#
# These are intentionally NOT real scientific code. They exist so the
# pipeline (worker → replay → governance) can exercise non-trivial
# compute with the same determinism guarantees as the placeholders.
# When real DFT / quantum back-ends land they will:
#
#   - register here with kind = REAL_BACKEND_KIND
#   - carry the same backend_runtime_seconds + disclaimer contract
#   - flip the replay validator's "real_backend_count" counter to > 0


def _toy_python_numeric(
    seed64: int, task_type: str, request: Dict[str, Any],
) -> Dict[str, Any]:
    """Stdlib-only deterministic numeric loop. Supports scoring and
    simulation. The 'work' is real (more cycles than the placeholder)
    but the result is NOT a scientific measurement — it is a
    reproducible byte-string."""
    n_iters = 4096
    s = seed64
    acc = 0.0
    samples: List[float] = []
    for i in range(n_iters):
        # Two linear-congruential mixers + a transcendental step for
        # bit diffusion. All stdlib.
        s = (s * 6364136223846793005 + 1442695040888963407) & ((1 << 64) - 1)
        x = (s >> 32) / (1 << 32)
        y = math.sin(x * 6.2831853 + i * 0.001)
        acc = acc * 0.97 + y * 0.03
        if i % 256 == 0:
            samples.append(round(acc, 8))
    return {
        "kind": "sandbox_toy_python_numeric_v01",
        "task_type": task_type,
        "n_iters": n_iters,
        "samples": samples,
        "final_acc": round(acc, 8),
        "note": (
            "deterministic sandbox toy backend; NOT a real scientific "
            "computation. For replay-validator pipeline testing only."
        ),
    }


def _toy_structure_relaxation(seed64: int) -> Dict[str, Any]:
    """Deterministic toy relaxation: 32 atoms, 64 gradient steps,
    stdlib only. NOT a real force-field minimisation."""
    n_atoms = 32
    n_steps = 64
    s = seed64
    coords: List[List[float]] = []
    # Initialise coordinates.
    for _ in range(n_atoms):
        triple = []
        for _ in range(3):
            s = (s * 1103515245 + 12345) & ((1 << 64) - 1)
            triple.append(((s & 0xFFFF) / 65535.0) * 10.0 - 5.0)
        coords.append(triple)
    # Toy relaxation: pull every atom slightly toward the centroid.
    for step in range(n_steps):
        cx = sum(c[0] for c in coords) / n_atoms
        cy = sum(c[1] for c in coords) / n_atoms
        cz = sum(c[2] for c in coords) / n_atoms
        damping = 0.98 - step * 0.001
        for c in coords:
            c[0] = c[0] * damping + cx * (1 - damping)
            c[1] = c[1] * damping + cy * (1 - damping)
            c[2] = c[2] * damping + cz * (1 - damping)
    # Round for canonicalisation stability.
    coords_rounded = [
        [round(c[0], 6), round(c[1], 6), round(c[2], 6)]
        for c in coords
    ]
    return {
        "kind": "sandbox_toy_structure_relaxation_v01",
        "n_atoms": n_atoms,
        "n_steps": n_steps,
        "coords_angstrom": coords_rounded,
        "note": (
            "deterministic sandbox toy relaxation; NOT a real "
            "force-field minimisation. Replay-pipeline only."
        ),
    }


def _toy_dft(seed64: int) -> Dict[str, Any]:
    """Deterministic toy 'Hamiltonian' eigenvalue surrogate: build a
    small symmetric matrix and iterate power method by hand. Stdlib
    only. NOT a real DFT calculation."""
    n = 8
    s = seed64
    # Build a symmetric n×n matrix from the seed.
    rows: List[List[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i, n):
            s = (s * 2862933555777941757 + 3037000493) & ((1 << 64) - 1)
            v = ((s >> 32) / (1 << 32)) * 2.0 - 1.0
            rows[i][j] = round(v, 6)
            rows[j][i] = rows[i][j]
    # Power iteration for the dominant eigenvalue.
    vec = [1.0 / math.sqrt(n)] * n
    for _ in range(64):
        new_vec = [0.0] * n
        for i in range(n):
            for j in range(n):
                new_vec[i] += rows[i][j] * vec[j]
        norm = math.sqrt(sum(x * x for x in new_vec))
        if norm <= 0:
            break
        vec = [x / norm for x in new_vec]
    # Rayleigh quotient.
    num = 0.0
    for i in range(n):
        for j in range(n):
            num += vec[i] * rows[i][j] * vec[j]
    dominant = round(num, 6)
    return {
        "kind": "sandbox_toy_dft_v01",
        "n_basis": n,
        "dominant_eigenvalue": dominant,
        "eigenvector_rounded": [round(x, 4) for x in vec],
        "note": (
            "deterministic sandbox toy 'DFT' surrogate. NOT a real "
            "density functional theory calculation. Replay pipeline "
            "only."
        ),
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_PLACEHOLDER_DISCLAIMER = (
    "Placeholder backend. Deterministic, zero-cost surrogate for "
    "the requested task_type. NOT a real scientific computation."
)

_SANDBOX_TOY_DISCLAIMER_NUMERIC = (
    "Sandbox toy backend (stdlib-only). Performs more work than the "
    "placeholder but is NOT a real scientific computation, NOT "
    "validated science, NOT publishable."
)
_SANDBOX_TOY_DISCLAIMER_STRUCT = (
    "Sandbox toy relaxation. Iterates a centroid-pull damping loop "
    "on synthetic coordinates. NOT a real force-field minimisation."
)
_SANDBOX_TOY_DISCLAIMER_DFT = (
    "Sandbox toy 'DFT' surrogate. Power-method eigenvalue of a "
    "small symmetric matrix. NOT a real density functional theory "
    "calculation. Real DFT requires a separate sprint."
)


_BACKENDS: List[BackendSpec] = [
    BackendSpec(
        name="placeholder_dft", version="v0.1",
        kind=PLACEHOLDER_KIND, task_types=["dft"],
        disclaimer=_PLACEHOLDER_DISCLAIMER, experimental=False,
    ),
    BackendSpec(
        name="placeholder_quantum", version="v0.1",
        kind=PLACEHOLDER_KIND, task_types=["quantum"],
        disclaimer=_PLACEHOLDER_DISCLAIMER, experimental=False,
    ),
    BackendSpec(
        name="placeholder_structure_relaxation", version="v0.1",
        kind=PLACEHOLDER_KIND, task_types=["structure_relaxation"],
        disclaimer=_PLACEHOLDER_DISCLAIMER, experimental=False,
    ),
    BackendSpec(
        name="placeholder_scoring", version="v0.1",
        kind=PLACEHOLDER_KIND, task_types=["scoring"],
        disclaimer=_PLACEHOLDER_DISCLAIMER, experimental=False,
    ),
    BackendSpec(
        name="placeholder_simulation", version="v0.1",
        kind=PLACEHOLDER_KIND, task_types=["simulation"],
        disclaimer=_PLACEHOLDER_DISCLAIMER, experimental=False,
    ),
    BackendSpec(
        name="placeholder_other", version="v0.1",
        kind=PLACEHOLDER_KIND, task_types=["other"],
        disclaimer=_PLACEHOLDER_DISCLAIMER, experimental=False,
    ),

    BackendSpec(
        name="local_python_numeric_v01", version="v0.1",
        kind=SANDBOX_TOY_KIND, task_types=["scoring", "simulation"],
        disclaimer=_SANDBOX_TOY_DISCLAIMER_NUMERIC, experimental=True,
    ),
    BackendSpec(
        name="local_structure_relaxation_toy_v01", version="v0.1",
        kind=SANDBOX_TOY_KIND, task_types=["structure_relaxation"],
        disclaimer=_SANDBOX_TOY_DISCLAIMER_STRUCT, experimental=True,
    ),
    BackendSpec(
        name="local_dft_toy_v01", version="v0.1",
        kind=SANDBOX_TOY_KIND, task_types=["dft"],
        disclaimer=_SANDBOX_TOY_DISCLAIMER_DFT, experimental=True,
    ),
]


def list_available_backends() -> List[Dict[str, Any]]:
    """Return a list of {name, version, kind, task_types,
    disclaimer, experimental} dicts."""
    return [b.as_dict() for b in _BACKENDS]


def _find_backend(name: str) -> Optional[BackendSpec]:
    for b in _BACKENDS:
        if b.name == name:
            return b
    return None


def select_backend(
    task_type: str,
    backend_name: str,
    allow_experimental: bool = False,
) -> BackendSpec:
    """Resolve a backend name to a BackendSpec.

    ``backend_name == "placeholder"`` is a special form that maps to
    ``placeholder_<task_type>``. Otherwise the name must match a
    registered backend, the backend must support the given task_type,
    and experimental backends require ``allow_experimental=True``.
    """
    if task_type not in _TASK_TYPES:
        raise ValueError(f"unknown task_type: {task_type!r}")

    resolved = (
        f"placeholder_{task_type}"
        if backend_name == "placeholder"
        else backend_name
    )

    spec = _find_backend(resolved)
    if spec is None:
        raise ValueError(f"unknown backend: {backend_name!r}")
    if task_type not in spec.task_types:
        raise ValueError(
            f"backend {spec.name!r} does not support "
            f"task_type {task_type!r}"
        )
    if spec.experimental and not allow_experimental:
        raise ValueError(
            f"backend {spec.name!r} is experimental and requires "
            f"--allow-experimental-backends to use"
        )
    return spec


def run_backend(
    spec: BackendSpec,
    *,
    request: Dict[str, Any],
    deterministic_seed: int,
    input_bundle_bytes: Optional[bytes] = None,
    sandbox_dir: Optional[Any] = None,
) -> BackendResult:
    """Execute the backend handler for the resolved spec.

    Placeholder backends report runtime_seconds = 0.0 (they are
    essentially free; keeping this pinned lets byte-identical tests
    on placeholder remain stable). Sandbox toy backends use
    ``time.monotonic`` to record real wall-clock — tests that compare
    full result bytes must therefore use placeholder, not toy.
    """
    task_type = request.get("task_type")
    if task_type not in _TASK_TYPES:
        raise ValueError(f"unknown request task_type: {task_type!r}")
    if task_type not in spec.task_types:
        raise ValueError(
            f"backend {spec.name!r} does not support "
            f"task_type {task_type!r}"
        )

    if spec.kind == PLACEHOLDER_KIND:
        handler = _PLACEHOLDER_HANDLERS[task_type]
        output_obj = handler(deterministic_seed)
        return BackendResult(
            output_obj=output_obj,
            runtime_seconds=0.0,
            spec=spec,
        )

    if spec.kind == SANDBOX_TOY_KIND:
        start = time.monotonic()
        if spec.name == "local_python_numeric_v01":
            output_obj = _toy_python_numeric(
                deterministic_seed, task_type, request,
            )
        elif spec.name == "local_structure_relaxation_toy_v01":
            output_obj = _toy_structure_relaxation(deterministic_seed)
        elif spec.name == "local_dft_toy_v01":
            output_obj = _toy_dft(deterministic_seed)
        else:
            raise ValueError(
                f"unknown sandbox toy backend: {spec.name!r}"
            )
        runtime = round(time.monotonic() - start, 6)
        return BackendResult(
            output_obj=output_obj,
            runtime_seconds=runtime,
            spec=spec,
        )

    raise ValueError(f"unsupported backend kind: {spec.kind!r}")


# ---------------------------------------------------------------------------
# Constants exposed for the rest of the pipeline (validator, gate,
# tests). The string values are part of the schema contract — do not
# rename without bumping schemas.
# ---------------------------------------------------------------------------

BACKEND_KIND_PLACEHOLDER  = PLACEHOLDER_KIND
BACKEND_KIND_SANDBOX_TOY  = SANDBOX_TOY_KIND
BACKEND_KIND_REAL_BACKEND = REAL_BACKEND_KIND
BACKEND_KIND_ENUM         = list(_BACKEND_KINDS)
