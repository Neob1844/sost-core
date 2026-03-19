"""Tests for models, training, inference, and registry."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import torch
import numpy as np
from src.models.cgcnn import CGCNN
from src.features.crystal_graph import structure_to_graph, composition_fingerprint


def test_cgcnn_forward():
    """Smoke test: CGCNN forward pass on synthetic data."""
    model = CGCNN(n_elem=10, atom_dim=16, bond_dim=10, n_conv=1, fc_dim=8)
    atom_f = torch.randn(4, 10)
    bond_d = torch.rand(4, 12)
    nbr_i = torch.zeros(4, 12, dtype=torch.long)
    out = model(atom_f, bond_d, nbr_i)
    assert out.shape == torch.Size([])  # scalar output


def test_cgcnn_backward():
    """CGCNN can compute gradients."""
    model = CGCNN(n_elem=10, atom_dim=16, bond_dim=10, n_conv=1, fc_dim=8)
    atom_f = torch.randn(3, 10)
    bond_d = torch.rand(3, 12)
    nbr_i = torch.zeros(3, 12, dtype=torch.long)
    pred = model(atom_f, bond_d, nbr_i)
    loss = (pred - 1.0) ** 2
    loss.backward()
    assert model.embedding.weight.grad is not None


def test_composition_fingerprint():
    fp = composition_fingerprint(["Fe", "O", "O"])
    assert fp.shape[0] == 94
    assert abs(fp.sum() - 1.0) < 1e-5  # normalized


def test_composition_fingerprint_empty():
    fp = composition_fingerprint([])
    assert fp.sum() == 0.0


def test_structure_to_graph():
    """Convert a real pymatgen Structure to graph."""
    from pymatgen.core import Structure, Lattice
    lattice = Lattice.cubic(5.64)
    struct = Structure(lattice, ["Na", "Cl"], [[0, 0, 0], [0.5, 0.5, 0.5]])
    graph = structure_to_graph(struct)
    assert graph is not None
    assert graph["n_atoms"] == 2
    assert graph["atom_features"].shape == (2, 94)


def test_model_registry():
    """Registry stores and retrieves models."""
    import tempfile, json
    from src.models.registry import register_model, list_models, get_best_model
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        json.dump([], f)
        path = f.name
    try:
        register_model({"model": "test", "target": "bg", "test_mae": 0.5}, path=path)
        register_model({"model": "test2", "target": "bg", "test_mae": 0.3}, path=path)
        assert len(list_models(path)) == 2
        best = get_best_model("bg", path=path)
        assert best["test_mae"] == 0.3
    finally:
        os.unlink(path)


def test_predict_from_cif():
    """Prediction works if model is trained."""
    from src.models.registry import get_best_model
    best = get_best_model("band_gap")
    if best is None:
        pytest.skip("No trained model — run training first")
    from src.inference.predictor import predict_from_cif
    # Minimal CIF
    cif = """data_test
_cell_length_a 5.0
_cell_length_b 5.0
_cell_length_c 5.0
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'P m -3 m'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Fe Fe 0.0 0.0 0.0
"""
    result = predict_from_cif(cif, "band_gap")
    assert "prediction" in result
    assert isinstance(result["prediction"], float)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
