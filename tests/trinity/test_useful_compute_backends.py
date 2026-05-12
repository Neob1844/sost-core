"""Trinity / Useful Compute backend registry v0.1 — invariants."""

from __future__ import annotations

import importlib.util
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
def backends_mod():
    return _load(
        "ucb", SCRIPTS_DIR / "useful_compute_backends.py",
    )


# ---------------------------------------------------------------------------
# Registry surface
# ---------------------------------------------------------------------------


def test_list_includes_every_placeholder(backends_mod):
    names = {b["name"] for b in backends_mod.list_available_backends()}
    for t in ("dft", "quantum", "structure_relaxation",
              "scoring", "simulation", "other"):
        assert f"placeholder_{t}" in names


def test_list_includes_three_toy_backends(backends_mod):
    names = {b["name"] for b in backends_mod.list_available_backends()}
    assert "local_python_numeric_v01" in names
    assert "local_structure_relaxation_toy_v01" in names
    assert "local_dft_toy_v01" in names


def test_no_backend_uses_real_backend_kind_in_v01(backends_mod):
    for b in backends_mod.list_available_backends():
        assert b["kind"] != backends_mod.REAL_BACKEND_KIND, (
            f"backend {b['name']!r} claims real_backend kind in v0.1"
        )


def test_kinds_enum_complete(backends_mod):
    assert set(backends_mod.BACKEND_KIND_ENUM) == {
        "placeholder", "sandbox_toy", "real_backend",
    }


def test_placeholders_are_not_experimental(backends_mod):
    for b in backends_mod.list_available_backends():
        if b["kind"] == "placeholder":
            assert b["experimental"] is False


def test_sandbox_toys_are_experimental(backends_mod):
    for b in backends_mod.list_available_backends():
        if b["kind"] == "sandbox_toy":
            assert b["experimental"] is True


# ---------------------------------------------------------------------------
# select_backend
# ---------------------------------------------------------------------------


def test_select_placeholder_magic_resolves_per_task(backends_mod):
    for t in ("dft", "quantum", "structure_relaxation",
              "scoring", "simulation", "other"):
        spec = backends_mod.select_backend(t, "placeholder")
        assert spec.name == f"placeholder_{t}"
        assert spec.kind == "placeholder"


def test_select_experimental_rejected_without_flag(backends_mod):
    with pytest.raises(ValueError, match="experimental"):
        backends_mod.select_backend(
            "scoring", "local_python_numeric_v01",
            allow_experimental=False,
        )


def test_select_experimental_accepted_with_flag(backends_mod):
    spec = backends_mod.select_backend(
        "scoring", "local_python_numeric_v01",
        allow_experimental=True,
    )
    assert spec.name == "local_python_numeric_v01"
    assert spec.kind == "sandbox_toy"


def test_select_unknown_task_type_rejected(backends_mod):
    with pytest.raises(ValueError, match="task_type"):
        backends_mod.select_backend(
            "nonsense", "placeholder",
        )


def test_select_unknown_backend_rejected(backends_mod):
    with pytest.raises(ValueError, match="unknown backend"):
        backends_mod.select_backend(
            "dft", "definitely_not_a_backend",
        )


def test_select_task_type_mismatch_rejected(backends_mod):
    # local_python_numeric_v01 supports scoring + simulation only.
    with pytest.raises(ValueError, match="does not support"):
        backends_mod.select_backend(
            "dft", "local_python_numeric_v01",
            allow_experimental=True,
        )


# ---------------------------------------------------------------------------
# run_backend determinism
# ---------------------------------------------------------------------------


def _req(task_type="scoring"):
    return {
        "schema": "trinity-useful-compute-request/v0.1",
        "request_id": "uc-0123456789abcdef",
        "task_type": task_type,
    }


def test_placeholder_runtime_is_zero(backends_mod):
    spec = backends_mod.select_backend("scoring", "placeholder")
    r = backends_mod.run_backend(
        spec, request=_req("scoring"), deterministic_seed=42,
    )
    assert r.runtime_seconds == 0.0


def test_placeholder_byte_identical_across_runs(backends_mod):
    spec = backends_mod.select_backend("dft", "placeholder")
    a = backends_mod.run_backend(
        spec, request=_req("dft"), deterministic_seed=99,
    )
    b = backends_mod.run_backend(
        spec, request=_req("dft"), deterministic_seed=99,
    )
    assert a.output_obj == b.output_obj


def test_toy_byte_identical_across_runs(backends_mod):
    spec = backends_mod.select_backend(
        "structure_relaxation",
        "local_structure_relaxation_toy_v01",
        allow_experimental=True,
    )
    a = backends_mod.run_backend(
        spec, request=_req("structure_relaxation"),
        deterministic_seed=99,
    )
    b = backends_mod.run_backend(
        spec, request=_req("structure_relaxation"),
        deterministic_seed=99,
    )
    assert a.output_obj == b.output_obj


def test_toy_runtime_is_non_negative(backends_mod):
    spec = backends_mod.select_backend(
        "dft", "local_dft_toy_v01", allow_experimental=True,
    )
    r = backends_mod.run_backend(
        spec, request=_req("dft"), deterministic_seed=7,
    )
    assert r.runtime_seconds >= 0.0


def test_toy_seed_change_changes_output(backends_mod):
    spec = backends_mod.select_backend(
        "dft", "local_dft_toy_v01", allow_experimental=True,
    )
    a = backends_mod.run_backend(
        spec, request=_req("dft"), deterministic_seed=1,
    )
    b = backends_mod.run_backend(
        spec, request=_req("dft"), deterministic_seed=2,
    )
    assert a.output_obj != b.output_obj


def test_disclaimer_attached_to_every_spec(backends_mod):
    for b in backends_mod.list_available_backends():
        assert b["disclaimer"]
        assert len(b["disclaimer"]) >= 1


def test_placeholder_disclaimer_does_not_claim_real_science(
    backends_mod,
):
    for b in backends_mod.list_available_backends():
        if b["kind"] == "placeholder":
            low = b["disclaimer"].lower()
            assert "not real" in low or "not a real" in low \
                or "not validated" in low


def test_toy_disclaimer_warns_not_scientific(backends_mod):
    for b in backends_mod.list_available_backends():
        if b["kind"] == "sandbox_toy":
            low = b["disclaimer"].lower()
            # "not real ... computation" OR "not a real" OR similar
            assert "not a real" in low or "not real" in low \
                or "not scientific" in low \
                or "not validated" in low
