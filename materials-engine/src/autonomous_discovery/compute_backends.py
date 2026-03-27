"""Phase XIII: Compute backend placeholders for stronger validation.

Defines the interface and expected I/O for future compute backends.
None of these are operational yet — they are architectural placeholders
that document what the validation bridge will connect to.

Honest limitation: NO actual DFT, M3GNet, or CHGNet computation happens
here. These are specifications for future integration.
"""
import time


class ComputeBackendPlaceholder:
    """Base class for compute backend placeholders."""

    def __init__(self, name, backend_type, status="placeholder"):
        self.name = name
        self.backend_type = backend_type
        self.status = status  # placeholder | testing | operational
        self.version = "0.0.1"

    def can_run(self):
        return self.status == "operational"

    def expected_input(self):
        raise NotImplementedError

    def expected_output(self):
        raise NotImplementedError

    def submit(self, job):
        if not self.can_run():
            return {
                "status": "not_operational",
                "backend": self.name,
                "message": f"{self.name} is a placeholder — no compute performed.",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        raise NotImplementedError

    def info(self):
        return {
            "name": self.name,
            "backend_type": self.backend_type,
            "status": self.status,
            "version": self.version,
        }


class RelaxationBackend(ComputeBackendPlaceholder):
    """Placeholder for structural relaxation backend (M3GNet/CHGNet)."""

    def __init__(self):
        super().__init__("relaxation_backend", "ml_potential", "placeholder")

    def expected_input(self):
        return {
            "cif_text": "str — CIF of lifted structure",
            "formula": "str — chemical formula",
            "max_steps": "int — max relaxation steps (default 500)",
            "force_threshold": "float — convergence criterion in eV/Å (default 0.05)",
        }

    def expected_output(self):
        return {
            "relaxed_cif": "str — CIF of relaxed structure",
            "final_energy": "float — total energy in eV",
            "energy_per_atom": "float — eV/atom",
            "converged": "bool",
            "steps_taken": "int",
            "max_force": "float — max residual force in eV/Å",
            "volume_change_pct": "float",
            "relaxation_time_seconds": "float",
        }


class StrongerComputeBackend(ComputeBackendPlaceholder):
    """Placeholder for stronger ML compute (next-gen GNN, fine-tuned models)."""

    def __init__(self):
        super().__init__("stronger_compute_backend", "advanced_gnn", "placeholder")

    def expected_input(self):
        return {
            "cif_text": "str — CIF of structure (relaxed preferred)",
            "formula": "str",
            "properties_requested": "list — ['formation_energy', 'band_gap', 'bulk_modulus']",
        }

    def expected_output(self):
        return {
            "predictions": "dict — {property: {value, uncertainty, model_used}}",
            "model_ensemble_agreement": "float — 0-1",
            "prediction_time_seconds": "float",
        }


class DFTBackend(ComputeBackendPlaceholder):
    """Placeholder for DFT backend (VASP, QE, etc)."""

    def __init__(self):
        super().__init__("dft_backend", "first_principles", "placeholder")

    def expected_input(self):
        return {
            "cif_text": "str — CIF of structure (preferably relaxed)",
            "formula": "str",
            "calculation_type": "str — 'relax' | 'static' | 'band_structure'",
            "functional": "str — 'PBE' | 'PBE+U' | 'HSE06'",
            "kpoints_density": "int — k-points per reciprocal atom",
        }

    def expected_output(self):
        return {
            "total_energy": "float — eV",
            "formation_energy_per_atom": "float — eV/atom",
            "band_gap": "float — eV",
            "is_metal": "bool",
            "forces": "list — residual forces per atom",
            "stress_tensor": "list — 3x3 stress in GPa",
            "converged": "bool",
            "wall_time_seconds": "float",
        }


# Registry of all backends
COMPUTE_BACKENDS = {
    "relaxation": RelaxationBackend(),
    "stronger_compute": StrongerComputeBackend(),
    "dft": DFTBackend(),
}


def get_backend(name):
    """Get a compute backend by name."""
    return COMPUTE_BACKENDS.get(name)


def list_backends():
    """List all registered compute backends with status."""
    return {name: b.info() for name, b in COMPUTE_BACKENDS.items()}


def get_operational_backends():
    """Get only operational backends."""
    return {name: b for name, b in COMPUTE_BACKENDS.items() if b.can_run()}
