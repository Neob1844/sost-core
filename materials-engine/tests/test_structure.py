"""Tests for crystal structure validation and JARVIS adapter."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.normalization.structure import (
    validate_structure, validate_structure_obj, jarvis_atoms_to_pymatgen,
    structure_to_cif, load_structure, structure_sha256
)

VALID_CIF = """data_NaCl
_cell_length_a 5.64
_cell_length_b 5.64
_cell_length_c 5.64
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'F m -3 m'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na Na 0.0 0.0 0.0
Cl Cl 0.5 0.5 0.5
"""

JARVIS_ATOMS = {
    "lattice_mat": [[5.64, 0.0, 0.0], [0.0, 5.64, 0.0], [0.0, 0.0, 5.64]],
    "coords": [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
    "elements": ["Na", "Cl"],
    "cartesian": False,
}


def test_valid_cif():
    valid, err = validate_structure(VALID_CIF)
    assert valid is True
    assert err is None


def test_empty_cif():
    valid, err = validate_structure("")
    assert valid is False


def test_invalid_cif():
    valid, err = validate_structure("not a cif")
    assert valid is False


def test_jarvis_to_pymatgen():
    struct = jarvis_atoms_to_pymatgen(JARVIS_ATOMS)
    assert struct is not None
    assert len(struct) == 2  # Na + Cl


def test_jarvis_to_pymatgen_validates():
    struct = jarvis_atoms_to_pymatgen(JARVIS_ATOMS)
    valid, err = validate_structure_obj(struct)
    assert valid is True


def test_jarvis_to_pymatgen_empty():
    assert jarvis_atoms_to_pymatgen({}) is None
    assert jarvis_atoms_to_pymatgen(None) is None


def test_jarvis_roundtrip():
    """JARVIS atoms → pymatgen → CIF → pymatgen roundtrip."""
    struct = jarvis_atoms_to_pymatgen(JARVIS_ATOMS)
    cif = structure_to_cif(struct)
    assert cif is not None
    assert len(cif) > 50
    struct2 = load_structure(cif)
    assert struct2 is not None
    assert len(struct2) == 2


def test_structure_sha256():
    h = structure_sha256("test")
    assert len(h) == 64


def test_structure_sha256_deterministic():
    assert structure_sha256("x") == structure_sha256("x")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
