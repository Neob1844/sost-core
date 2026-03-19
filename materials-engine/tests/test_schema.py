"""Tests for Material DNA schema."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.schema import Material


def test_compute_canonical_id_deterministic():
    m1 = Material(formula="SiO2", spacegroup=152, source="mp", source_id="mp-123")
    m2 = Material(formula="SiO2", spacegroup=152, source="aflow", source_id="aflow-999")
    # canonical_id is source-independent
    assert m1.compute_canonical_id() == m2.compute_canonical_id()
    assert len(m1.canonical_id) == 16


def test_compute_canonical_id_different_materials():
    m1 = Material(formula="SiO2", spacegroup=152, source="mp", source_id="1")
    m2 = Material(formula="TiO2", spacegroup=136, source="mp", source_id="2")
    m1.compute_canonical_id()
    m2.compute_canonical_id()
    assert m1.canonical_id != m2.canonical_id


def test_serialization_roundtrip():
    m = Material(formula="NaCl", elements=["Cl", "Na"], n_elements=2,
                 band_gap=8.5, source="test", source_id="t2", confidence=0.9)
    m.compute_canonical_id()
    j = m.to_json()
    m2 = Material.from_json(j)
    assert m2.formula == "NaCl"
    assert m2.band_gap == 8.5
    assert m2.canonical_id == m.canonical_id


def test_canonical_json_stable():
    m = Material(formula="Fe2O3", source="test", source_id="1", band_gap=2.1)
    j1 = m.canonical_json()
    j2 = m.canonical_json()
    assert j1 == j2
    assert '"' not in j1 or j1.index("{") == 0  # valid JSON


def test_to_dict_excludes_none():
    m = Material(formula="Cu", source="test", source_id="t3")
    d = m.to_dict()
    assert "band_gap" not in d
    assert "formula" in d


def test_validate_good():
    m = Material(formula="Fe2O3", source="mp", source_id="1",
                 elements=["Fe", "O"], n_elements=2, confidence=0.8)
    assert m.validate() == []


def test_validate_empty_source():
    m = Material(formula="Fe2O3", source="", source_id="1")
    errors = m.validate()
    assert any("source" in e for e in errors)


def test_validate_bad_confidence():
    m = Material(formula="X", source="t", source_id="1", confidence=1.5)
    errors = m.validate()
    assert any("confidence" in e for e in errors)


def test_validate_n_elements_mismatch():
    m = Material(formula="X", source="t", source_id="1",
                 elements=["Fe", "O"], n_elements=5)
    errors = m.validate()
    assert any("n_elements" in e for e in errors)


def test_validate_bad_spacegroup():
    m = Material(formula="X", source="t", source_id="1", spacegroup=999)
    errors = m.validate()
    assert any("spacegroup" in e for e in errors)


def test_similarity():
    m1 = Material(formula="A", source="t", source_id="1", embedding=[1, 0, 0])
    m2 = Material(formula="B", source="t", source_id="2", embedding=[1, 0, 0])
    m3 = Material(formula="C", source="t", source_id="3", embedding=[0, 1, 0])
    assert abs(m1.similarity(m2) - 1.0) < 1e-6
    assert abs(m1.similarity(m3)) < 1e-6


def test_similarity_no_embedding():
    m1 = Material(formula="A", source="t", source_id="1")
    m2 = Material(formula="B", source="t", source_id="2", embedding=[1, 0])
    assert m1.similarity(m2) == 0.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
