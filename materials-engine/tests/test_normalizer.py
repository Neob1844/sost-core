"""Tests for normalization from each source to canonical schema."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.normalization.normalizer import normalize
from src.normalization.unit_converter import ev_to_kj_per_mol, gpa_to_bar


def test_normalize_mp():
    raw = {
        "material_id": "mp-19006",
        "formula_pretty": "Fe2O3",
        "elements": ["Fe", "O"],
        "nsites": 10,
        "symmetry": {"number": 167, "symbol": "R-3c", "crystal_system": "Trigonal"},
        "band_gap": 2.1,
        "is_gap_direct": False,
        "formation_energy_per_atom": -1.65,
        "energy_above_hull": 0.0,
        "k_vrh": 210.0,
        "g_vrh": 85.0,
        "total_magnetization": 10.0,
    }
    m = normalize(raw, "materials_project")
    assert m.formula == "Fe2O3"
    assert m.source == "materials_project"
    assert m.source_id == "mp-19006"
    assert m.band_gap == 2.1
    assert m.spacegroup == 167
    assert m.spacegroup_symbol == "R-3c"
    assert m.nsites == 10
    assert m.formation_energy == -1.65
    assert m.bulk_modulus == 210.0
    assert m.confidence == 0.8
    assert m.canonical_id  # computed
    assert m.raw_payload_sha256  # provenance
    assert m.normalizer_version


def test_normalize_aflow_egap_not_conflated():
    """Verify Egap (float) is NOT confused with Egap_type (string)."""
    raw = {
        "compound": "TiO2",
        "Egap": 3.2,
        "Egap_type": "insulator_direct",
        "Bvoigt": 180.5,
        "sg2": 136,
        "auid": "aflow:abc123",
    }
    m = normalize(raw, "aflow")
    assert m.band_gap == 3.2  # numeric value
    assert m.band_gap_direct is True  # derived from Egap_type string
    assert m.formula == "TiO2"


def test_normalize_aflow_metal():
    raw = {"compound": "Cu", "Egap": 0.0, "Egap_type": "metal", "auid": "aflow:cu1"}
    m = normalize(raw, "aflow")
    assert m.band_gap == 0.0
    assert m.band_gap_direct is False  # "metal" doesn't contain "direct"


def test_normalize_cod_no_computed_properties():
    """COD provides structure only — no band gap, no formation energy."""
    raw = {"formula": "NaCl", "sg": 225, "sgHM": "Fm-3m",
           "a": 5.64, "b": 5.64, "c": 5.64,
           "alpha": 90.0, "beta": 90.0, "gamma": 90.0, "file": "1000041"}
    m = normalize(raw, "cod")
    assert m.formula == "NaCl"
    assert m.spacegroup == 225
    assert m.spacegroup_symbol == "Fm-3m"
    assert m.lattice_params["a"] == 5.64
    assert m.band_gap is None  # COD has no computed properties
    assert m.formation_energy is None
    assert m.confidence == 1.0


def test_normalize_cod_chemname_fallback():
    """When COD has no formula, chemname is used as fallback."""
    raw = {"chemname": "Iron oxide", "sg": 167, "file": "9999"}
    m = normalize(raw, "cod")
    assert m.formula == "Iron oxide"  # fallback from chemname


def test_normalize_jarvis():
    raw = {
        "jid": "JVASP-1002",
        "formula": "Si",
        "spg_number": 227,
        "spg_symbol": "Fd-3m",
        "optb88vdw_bandgap": 0.61,
        "formation_energy_peratom": 0.0,
        "ehull": 0.0,
        "kv": 88.0,
        "gv": 52.0,
        "nat": 2,
    }
    m = normalize(raw, "jarvis")
    assert m.formula == "Si"
    assert m.source == "jarvis"
    assert m.band_gap == 0.61
    assert m.bulk_modulus == 88.0
    assert m.nsites == 2
    assert m.spacegroup == 227


def test_normalize_unknown_source():
    import pytest
    with pytest.raises(ValueError, match="Unknown source"):
        normalize({}, "nonexistent_db")


def test_unit_conversions():
    assert abs(ev_to_kj_per_mol(1.0) - 96.485) < 0.01
    assert abs(gpa_to_bar(1.0) - 10000.0) < 0.01


def test_provenance_fields():
    raw = {"material_id": "mp-1", "formula_pretty": "H", "elements": ["H"],
           "symmetry": {}}
    m = normalize(raw, "materials_project")
    assert m.raw_payload_sha256 is not None
    assert len(m.raw_payload_sha256) == 64
    assert m.ingested_at is not None
    assert m.normalized_at is not None
    assert m.source_url is not None


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
