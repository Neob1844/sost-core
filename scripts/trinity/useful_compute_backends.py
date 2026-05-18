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
from pathlib import Path
from typing import Any, Dict, List, Optional


PLACEHOLDER_KIND  = "placeholder"
SANDBOX_TOY_KIND  = "sandbox_toy"
REAL_BACKEND_KIND = "real_backend"   # reserved; no backend uses this in v0.1

_BACKEND_KINDS = (PLACEHOLDER_KIND, SANDBOX_TOY_KIND, REAL_BACKEND_KIND)

_TASK_TYPES = (
    "dft", "quantum", "structure_relaxation",
    "scoring", "simulation", "other",
    # Sprint 5.22b — scientific prompt intake bridge (5.20 → 5.21).
    # The backend for this task_type does NOT interpret the prompt
    # semantically and does NOT call any LLM or remote API. It
    # produces a deterministic hash manifest derived from
    # metadata.scientific_intake so the rest of the pipeline
    # (worker → replay → governance → budget → proposal → draft)
    # can carry the scientific context end-to-end in dry-run.
    "scientific_intake",
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


def _placeholder_scientific_intake(
    seed64: int, request: Dict[str, Any],
) -> Dict[str, Any]:
    """Deterministic backend for task_type=scientific_intake.

    Does NOT interpret the prompt. Does NOT call any LLM. Does NOT
    open a network connection. The output is a stable byte-string
    that carries the request identifiers + the intake's hash
    manifest forward so replay / governance / budget / proposal /
    draft can pass the scientific context through the pipeline in
    dry-run.

    Two workers given the same request MUST produce the same
    output bytes — that is the cross-worker replay contract.
    """
    md = (request.get("metadata") or {}).get(
        "scientific_intake", {}
    )
    return {
        "kind": "placeholder_scientific_intake_v0",
        "note": (
            "deterministic hash manifest only; v0.1 does NOT "
            "interpret the prompt semantically and does NOT call "
            "any LLM, network or remote API. Output is a stable "
            "byte-string derived from the request's identifiers "
            "and the intake's hashes."
        ),
        "source_tool": request.get("source_tool"),
        "task_type":   request.get("task_type"),
        "request_id":  request.get("request_id"),
        "input_bundle_sha256":     request.get(
            "input_bundle_sha256"
        ),
        "intake_id":               md.get("intake_id"),
        "combined_context_sha256": md.get(
            "combined_context_sha256"
        ),
        "prompt_sha256":           md.get("prompt_sha256"),
        "documents_count":         md.get("documents_count"),
        "intake_task_kind":        md.get("intake_task_kind"),
        "intake_artifact_sha256":  md.get(
            "intake_artifact_sha256"
        ),
        "validation_status": "hash_manifest_only",
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
# Sprint 5.32 — Materials Engine deterministic backend
# ---------------------------------------------------------------------------
#
# A real-semantic local backend: it reads the Sprint 5.31 classifier
# metadata in the request and produces a deterministic materials
# comparison output using a CURATED local properties table.
#
# This is NOT DFT. NOT quantum. NOT a real simulation. The values in
# the table are illustrative and explicitly labelled as such — they
# come from a hand-curated review, not from a measured dataset, and
# they are pinned in source so two workers always agree on the same
# numbers. The point of v0.1 is to start emitting materials-specific
# semantic output (ranking, score, property breakdown) instead of
# the placeholder hash-only stub.

# Sprint 5.32 — local curated materials properties table v0.1.
# Each entry is a small dict of named properties. Higher-is-better
# unless explicitly stated. Optimal-temperature is the temperature
# at which the property reading is taken; the scorer reads it as
# "lower is better" for rapid-cycling oxygen-storage use cases.
# These numbers are deliberately illustrative — labelled as such
# in the disclaimer and the result schema's `limitations` field.
_MATERIALS_PROPERTIES_TABLE_V01 = {
    "CeO2":  {
        "oxygen_storage_mmol_g":  1.7,
        "optimal_temperature_c":  500,
        "redox_support":          0.90,
        "stability":              0.85,
        "conductivity":           0.65,
        "surface_area_m2_g":      120.0,
    },
    "PrOx":  {
        "oxygen_storage_mmol_g":  2.3,
        "optimal_temperature_c":  450,
        "redox_support":          0.95,
        "stability":              0.75,
        "conductivity":           0.55,
        "surface_area_m2_g":      90.0,
    },
    "Sm2O3": {
        "oxygen_storage_mmol_g":  0.9,
        "optimal_temperature_c":  600,
        "redox_support":          0.60,
        "stability":              0.90,
        "conductivity":           0.40,
        "surface_area_m2_g":      60.0,
    },
    "Y2O3":  {
        "oxygen_storage_mmol_g":  0.7,
        "optimal_temperature_c":  700,
        "redox_support":          0.50,
        "stability":              0.95,
        "conductivity":           0.30,
        "surface_area_m2_g":      40.0,
    },
    "ZrO2":  {
        "oxygen_storage_mmol_g":  0.5,
        "optimal_temperature_c":  800,
        "redox_support":          0.40,
        "stability":              0.98,
        "conductivity":           0.25,
        "surface_area_m2_g":      50.0,
    },
    "TiO2":  {
        "oxygen_storage_mmol_g":  0.3,
        "optimal_temperature_c":  600,
        "redox_support":          0.30,
        "stability":              0.95,
        "conductivity":           0.35,
        "surface_area_m2_g":      80.0,
    },
}

# Map every classifier-output metric label we recognise → a (prop,
# direction) pair. Direction is "higher_is_better" or
# "lower_is_better". Unknown metric labels are scored 0 and recorded
# as warnings.
_METRIC_TO_PROPERTY = {
    "oxygen_storage_capacity":  ("oxygen_storage_mmol_g", "higher_is_better"),
    "oxygen_storage_mmol_g":    ("oxygen_storage_mmol_g", "higher_is_better"),
    "temperature":              ("optimal_temperature_c", "lower_is_better"),
    "temperature_c":            ("optimal_temperature_c", "lower_is_better"),
    "redox_potential":          ("redox_support",         "higher_is_better"),
    "redox":                    ("redox_support",         "higher_is_better"),
    "stability":                ("stability",             "higher_is_better"),
    "conductivity":             ("conductivity",          "higher_is_better"),
    "surface_area":             ("surface_area_m2_g",     "higher_is_better"),
}

# Property normalisation bounds — drawn from the curated table so
# v0.1 stays self-contained. If a new property is added to the
# table, add an entry here too (a static test would catch the gap).
_PROPERTY_BOUNDS = {
    "oxygen_storage_mmol_g":   (0.0,  3.0),
    "optimal_temperature_c":   (300,  900),
    "redox_support":           (0.0,  1.0),
    "stability":               (0.0,  1.0),
    "conductivity":            (0.0,  1.0),
    "surface_area_m2_g":       (0.0, 200.0),
}

_MATERIALS_ENGINE_SCHEMA = "trinity-materials-engine-result/v0.1"
_MATERIALS_ENGINE_BACKEND_NAME = "local_materials_engine_v01"
_MATERIALS_ENGINE_BACKEND_VERSION = "v0.1"


def _normalise_property(prop: str, value: float, direction: str) -> float:
    """Clamp value into [0,1] using _PROPERTY_BOUNDS. Inverts when
    direction is lower_is_better. Returns 0.0 for unknown property
    (the caller will also record a warning)."""
    bounds = _PROPERTY_BOUNDS.get(prop)
    if bounds is None:
        return 0.0
    lo, hi = bounds
    if hi <= lo:
        return 0.0
    raw = (float(value) - lo) / (hi - lo)
    if raw < 0.0:
        raw = 0.0
    elif raw > 1.0:
        raw = 1.0
    if direction == "lower_is_better":
        raw = 1.0 - raw
    return round(raw, 6)


def _canonical_request_sha256(request: Dict[str, Any]) -> str:
    """Deterministic source-request fingerprint. Used as
    source_request_sha256 in the materials_engine result so two
    workers binding to the same request bind to the same fingerprint."""
    blob = json.dumps(
        request, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Sprint 5.34 - Materials Project cached reference dataset
# ---------------------------------------------------------------------------
#
# LOCAL cache only. The resolver loads the file once at first use,
# verifies every hash (cache_sha256 over the file, record_sha256
# per record, property_hash_sha256 per property block) and refuses
# to serve any record if any hash mismatches. There is NO network
# fetch, NO live API call, NO child process. The cache exists so the
# materials_engine result can carry provenance hashes alongside
# its ranking; v0.1 hand-curated values are clearly labelled in
# the cache file's cache_source_notice.

_MATERIALS_PROJECT_CACHE_SCHEMA = "trinity-materials-project-cache/v0.1"
_MATERIALS_PROJECT_CACHE_FILE = (
    "materials_project_cache_v01.json"
)
_materials_project_cache_state: Dict[str, Any] = {
    "loaded": False,
    "cache":   None,
    "alias_index": None,
    "load_error": None,
}


def _canon_inner(o: Any) -> str:
    return json.dumps(
        o, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _verify_cache_hashes(cache_obj: Dict[str, Any]) -> None:
    """Raise ValueError if any cache_sha256 / record_sha256 /
    property_hash_sha256 does not match the canonical content."""
    # File-level sha256: recompute over the file without the
    # cache_sha256 field, which is the same way the writer did it.
    declared_file_sha = cache_obj.get("cache_sha256")
    body = {k: v for k, v in cache_obj.items() if k != "cache_sha256"}
    computed_file_sha = hashlib.sha256(
        _canon_inner(body).encode("utf-8"),
    ).hexdigest()
    if declared_file_sha != computed_file_sha:
        raise ValueError(
            "materials_project_cache cache_sha256 mismatch: "
            "declared=" + str(declared_file_sha)
            + " computed=" + str(computed_file_sha)
        )
    for rec in cache_obj.get("records", []):
        # property_hash_sha256
        decl_prop = rec.get("property_hash_sha256")
        comp_prop = hashlib.sha256(
            _canon_inner(rec["properties"]).encode("utf-8"),
        ).hexdigest()
        if decl_prop != comp_prop:
            raise ValueError(
                "materials_project_cache property_hash_sha256 "
                "mismatch for material_id="
                + str(rec.get("material_id"))
            )
        # record_sha256 (excludes itself)
        decl_rec = rec.get("record_sha256")
        rec_body = {k: v for k, v in rec.items() if k != "record_sha256"}
        comp_rec = hashlib.sha256(
            _canon_inner(rec_body).encode("utf-8"),
        ).hexdigest()
        if decl_rec != comp_rec:
            raise ValueError(
                "materials_project_cache record_sha256 mismatch "
                "for material_id=" + str(rec.get("material_id"))
            )


def _load_materials_project_cache() -> Dict[str, Any]:
    """Lazily load + verify the cache. Cached in
    _materials_project_cache_state. Returns the cache dict.

    On load failure (file missing, JSON invalid, hash mismatch),
    returns a sentinel cache with records=[] and load_error set so
    the resolver can still report cache_miss for everything without
    crashing the worker."""
    st = _materials_project_cache_state
    if st["loaded"]:
        return st["cache"]
    # Look in two places: data/trinity/ (repo root) and
    # config/trinity/ as a future operator-override location.
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "data" / "trinity" / _MATERIALS_PROJECT_CACHE_FILE,
        repo_root / "config" / "trinity" / _MATERIALS_PROJECT_CACHE_FILE,
    ]
    cache_path: Optional[Path] = None
    for c in candidates:
        if c.exists():
            cache_path = c
            break

    if cache_path is None:
        st["cache"] = {
            "schema":               _MATERIALS_PROJECT_CACHE_SCHEMA,
            "cache_version":        "missing",
            "cache_generated_at":   "missing",
            "cache_source_notice":  "cache file not found on disk",
            "record_count":         0,
            "records":              [],
            "cache_sha256":         "0" * 64,
        }
        st["alias_index"] = {}
        st["load_error"]  = "cache file not found"
        st["loaded"]      = True
        return st["cache"]

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            raise ValueError("cache top-level is not a JSON object")
        if obj.get("schema") != _MATERIALS_PROJECT_CACHE_SCHEMA:
            raise ValueError(
                "cache schema mismatch: " + repr(obj.get("schema"))
            )
        _verify_cache_hashes(obj)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        st["cache"] = {
            "schema":               _MATERIALS_PROJECT_CACHE_SCHEMA,
            "cache_version":        "load_error",
            "cache_generated_at":   "load_error",
            "cache_source_notice":  "cache load failed: " + str(exc)[:200],
            "record_count":         0,
            "records":              [],
            "cache_sha256":         "0" * 64,
        }
        st["alias_index"] = {}
        st["load_error"]  = str(exc)[:200]
        st["loaded"]      = True
        return st["cache"]

    alias_index: Dict[str, Dict[str, Any]] = {}
    for rec in obj.get("records", []):
        for a in [rec.get("formula_pretty", "")] + list(
            rec.get("aliases", []) or [],
        ):
            if isinstance(a, str) and a:
                alias_index[a.lower()] = rec

    st["cache"]       = obj
    st["alias_index"] = alias_index
    st["load_error"]  = None
    st["loaded"]      = True
    return st["cache"]


def _resolve_material_in_cache(label: str) -> Optional[Dict[str, Any]]:
    """Return the cache record matching `label` (case-insensitive
    alias lookup) or None on miss."""
    if not isinstance(label, str) or not label:
        return None
    _load_materials_project_cache()
    return _materials_project_cache_state["alias_index"].get(label.lower())


def materials_project_cache_info() -> Dict[str, Any]:
    """Read-only introspection: load + return small descriptor of
    the loaded cache. Useful for tests + the dashboard."""
    c = _load_materials_project_cache()
    st = _materials_project_cache_state
    return {
        "cache_version":  c.get("cache_version", "missing"),
        "cache_sha256":   c.get("cache_sha256", "0" * 64),
        "record_count":   int(c.get("record_count", 0)),
        "alias_count":    len(st["alias_index"] or {}),
        "load_error":     st.get("load_error"),
    }


def _materials_engine_v01(
    seed64: int, request: Dict[str, Any],
) -> Dict[str, Any]:
    """Deterministic local materials_engine backend handler.

    Reads request.metadata.scientific_task_classification (Sprint 5.31)
    to obtain candidate_materials, candidate_metrics, task_kind.
    Reads request.metadata.scientific_reader_manifest (Sprint 5.30)
    for the audit trail. Looks each material up in the curated
    properties table; for each requested metric maps it to a
    property + direction and computes a normalised 0-1 score.
    Final score per material is the arithmetic mean of metric scores.
    Ranking sorts by score descending with material name as tiebreaker.

    NEVER opens a network connection. NEVER calls an LLM. NEVER
    invokes a child process. Pure dict-of-dict arithmetic.
    """
    md = request.get("metadata") or {}
    classification = md.get("scientific_task_classification") or {}
    candidate_materials = list(
        classification.get("candidate_materials", []) or []
    )
    candidate_metrics = list(
        classification.get("candidate_metrics", []) or []
    )
    task_kind = classification.get("task_kind", "extraction")
    classification_id = classification.get("classification_id", "")

    warnings: List[str] = []
    limitations: List[str] = [
        "v0.1 uses a curated local properties table; values are "
        "illustrative, NOT measured data, NOT publishable.",
        "no DFT, no quantum, no real simulation, no network.",
        "metric → property mapping is hand-curated; unknown metric "
        "labels are dropped from the scoring with a warning.",
    ]

    # Bin materials.
    known: List[str] = []
    unknown: List[str] = []
    for m in candidate_materials:
        if m in _MATERIALS_PROPERTIES_TABLE_V01:
            if m not in known:
                known.append(m)
        else:
            if m not in unknown:
                unknown.append(m)
    if unknown:
        warnings.append(
            "unknown material(s) absent from the curated table: "
            + ",".join(unknown)
        )

    # Project metrics to properties + directions, dropping unknowns.
    resolved_metrics: List[Dict[str, str]] = []
    seen_property = set()
    for metric in candidate_metrics:
        entry = _METRIC_TO_PROPERTY.get(metric)
        if entry is None:
            warnings.append(
                "metric label not recognised by v0.1: " + repr(metric)
            )
            continue
        prop, direction = entry
        if prop in seen_property:
            # Same property reached via two metric labels (e.g. both
            # 'temperature' and 'temperature_c' map to
            # optimal_temperature_c); keep the first.
            continue
        seen_property.add(prop)
        resolved_metrics.append({
            "metric": metric,
            "property": prop,
            "direction": direction,
        })
    if not resolved_metrics:
        warnings.append(
            "no recognised metrics; ranking falls back to "
            "oxygen_storage_capacity"
        )
        resolved_metrics.append({
            "metric": "oxygen_storage_capacity",
            "property": "oxygen_storage_mmol_g",
            "direction": "higher_is_better",
        })

    # Build property_table for known materials only (unknowns appear
    # in warnings; including them in property_table would imply we
    # have data for them).
    property_table: Dict[str, Dict[str, float]] = {}
    for m in sorted(known):
        property_table[m] = dict(
            _MATERIALS_PROPERTIES_TABLE_V01[m]
        )

    # Score each known material.
    ranking: List[Dict[str, Any]] = []
    for m in sorted(known):
        per_metric: List[Dict[str, Any]] = []
        scores: List[float] = []
        for rm in resolved_metrics:
            value = _MATERIALS_PROPERTIES_TABLE_V01[m].get(
                rm["property"]
            )
            if value is None:
                per_metric.append({
                    "metric": rm["metric"],
                    "property": rm["property"],
                    "value": None,
                    "normalised_score": 0.0,
                    "direction": rm["direction"],
                })
                continue
            ns = _normalise_property(
                rm["property"], float(value), rm["direction"],
            )
            scores.append(ns)
            per_metric.append({
                "metric": rm["metric"],
                "property": rm["property"],
                "value": float(value),
                "normalised_score": ns,
                "direction": rm["direction"],
            })
        mean_score = (
            round(sum(scores) / len(scores), 6) if scores else 0.0
        )
        ranking.append({
            "material": m,
            "score": mean_score,
            "metric_breakdown": per_metric,
        })
    # Sort by score descending, then material ascending for stable
    # tiebreaking.
    ranking.sort(key=lambda r: (-r["score"], r["material"]))

    score_explanation = (
        "score per material = mean over resolved metrics of "
        "(value normalised to [0,1] within property bounds, "
        "inverted for lower_is_better directions). Property "
        "bounds and metric→property mapping are pinned in "
        + _MATERIALS_ENGINE_BACKEND_NAME + "."
    )

    # Sprint 5.34 - Materials Project cache resolution. For every
    # material the classifier asked about (known + unknown to the
    # curated table), try to find a cached reference record. Cache
    # hits attach provenance fields (material_id + record_sha256 +
    # property_hash_sha256) to the result; cache misses are
    # recorded but never block. The cache is loaded + hash-verified
    # at module import time; here we just consult the in-memory
    # alias index. Both workers see the same cache file on disk
    # (same bytes, same sha256, same alias resolution), so adding
    # these fields keeps compute_output_sha256 cross-worker stable.
    cache_info = materials_project_cache_info()
    cache_hits: List[Dict[str, Any]] = []
    cache_misses: List[str] = []
    for m in candidate_materials:
        rec = _resolve_material_in_cache(m)
        if rec is None:
            if m not in cache_misses:
                cache_misses.append(m)
            continue
        cache_hits.append({
            "query":                m,
            "material_id":          rec.get("material_id", ""),
            "formula_pretty":       rec.get("formula_pretty", ""),
            "source":               rec.get("source", ""),
            "source_url_text":      rec.get("source_url_text", ""),
            "source_retrieved_at":  rec.get("source_retrieved_at", ""),
            "record_sha256":        rec.get("record_sha256", ""),
            "property_hash_sha256": rec.get("property_hash_sha256", ""),
        })
    if cache_info.get("load_error"):
        warnings.append(
            "materials_project_cache load_error: "
            + str(cache_info["load_error"])
        )
        limitations.append(
            "materials_project_cache_used=false; no provenance "
            "anchors attached this run."
        )

    return {
        "schema": _MATERIALS_ENGINE_SCHEMA,
        "backend": "materials_engine",
        "backend_version": _MATERIALS_ENGINE_BACKEND_VERSION,
        "mode": "local-dry-run",
        "task_kind": task_kind,
        "materials_compared": list(candidate_materials),
        "metrics_requested": list(candidate_metrics),
        "known_materials": known,
        "unknown_materials": unknown,
        "resolved_metrics": resolved_metrics,
        "property_table": property_table,
        "ranking": ranking,
        "score_explanation": score_explanation,
        "limitations": limitations,
        "warnings": warnings,
        "source_request_sha256": _canonical_request_sha256(request),
        "classification_id": classification_id,
        "marker_hex": "%016x" % (seed64 & ((1 << 64) - 1)),
        # Sprint 5.34 cache surfacing.
        "materials_project_cache_used":
            cache_info.get("load_error") is None,
        "materials_project_cache_version":
            cache_info.get("cache_version", "missing"),
        "materials_project_cache_sha256":
            cache_info.get("cache_sha256", "0" * 64),
        "materials_project_cache_hits":   cache_hits,
        "materials_project_cache_misses": cache_misses,
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_PLACEHOLDER_DISCLAIMER = (
    "Placeholder backend. Deterministic, zero-cost surrogate for "
    "the requested task_type. NOT a real scientific computation."
)

_MATERIALS_ENGINE_DISCLAIMER = (
    "Local deterministic materials_engine backend (Sprint 5.32). "
    "Reads classifier metadata + a curated local properties table "
    "and emits a ranked materials comparison. NOT DFT. NOT a real "
    "simulation. Property values are illustrative, hand-curated, "
    "pinned in source. No network, no LLM, no child process."
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
        name="placeholder_scientific_intake", version="v0.1",
        kind=PLACEHOLDER_KIND, task_types=["scientific_intake"],
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

    # Sprint 5.32 — first non-placeholder, non-toy backend.
    # Real semantic output via a curated local table; explicitly
    # NOT DFT.
    BackendSpec(
        name=_MATERIALS_ENGINE_BACKEND_NAME,
        version=_MATERIALS_ENGINE_BACKEND_VERSION,
        kind=REAL_BACKEND_KIND,
        task_types=["scientific_intake"],
        disclaimer=_MATERIALS_ENGINE_DISCLAIMER,
        experimental=False,
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
        if task_type == "scientific_intake":
            # The scientific-intake handler reads identifiers and
            # hashes from the request, so it takes a different
            # signature than the other placeholders.
            output_obj = _placeholder_scientific_intake(
                deterministic_seed, request,
            )
        else:
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

    # Sprint 5.32 — REAL_BACKEND_KIND dispatch. The materials_engine
    # handler reads classifier metadata from the request and is
    # deterministic; we pin runtime_seconds to 0.0 the same way
    # placeholders do so byte-identical tests stay stable.
    if spec.kind == REAL_BACKEND_KIND:
        if spec.name == _MATERIALS_ENGINE_BACKEND_NAME:
            output_obj = _materials_engine_v01(
                deterministic_seed, request,
            )
            return BackendResult(
                output_obj=output_obj,
                runtime_seconds=0.0,
                spec=spec,
            )
        raise ValueError(
            f"unknown real backend: {spec.name!r}"
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
