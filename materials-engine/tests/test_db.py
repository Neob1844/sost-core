"""Tests for database storage and queries."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB


@pytest.fixture
def db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    d = MaterialsDB(f.name)
    yield d
    os.unlink(f.name)


def _mat(formula, bg=None, fe=None, bm=None, elements=None, sg=None,
         source="test", sid=None, cs=None):
    m = Material(
        formula=formula, formula_pretty=formula,
        elements=elements or [], n_elements=len(elements or []),
        band_gap=bg, formation_energy=fe, bulk_modulus=bm,
        spacegroup=sg, crystal_system=cs,
        source=source, source_id=sid or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


def test_insert_and_get(db):
    m = _mat("SiO2", bg=8.9, elements=["O", "Si"], sg=152, cs="Trigonal")
    assert db.insert_material(m)
    got = db.get_material(m.canonical_id)
    assert got is not None
    assert got.formula == "SiO2"
    assert got.band_gap == 8.9
    assert got.spacegroup == 152


def test_get_by_source(db):
    m = _mat("TiO2", source="mp", sid="mp-123")
    db.insert_material(m)
    got = db.get_by_source("mp", "mp-123")
    assert got is not None
    assert got.formula == "TiO2"


def test_upsert(db):
    m1 = _mat("Fe", bg=0.0, source="mp", sid="mp-1")
    db.insert_material(m1)
    m2 = _mat("Fe", bg=0.5, source="mp", sid="mp-1")  # same source+sid
    db.insert_material(m2)
    assert db.count() == 1  # upserted, not duplicated
    got = db.get_by_source("mp", "mp-1")
    assert got.band_gap == 0.5  # updated


def test_dedup_across_sources(db):
    """Same formula+spacegroup from different sources = same canonical_id, different records."""
    m1 = _mat("NaCl", sg=225, source="mp", sid="mp-1")
    m2 = _mat("NaCl", sg=225, source="aflow", sid="af-1")
    db.insert_material(m1)
    db.insert_material(m2)
    assert db.count() == 2  # different (source, source_id) = different records
    assert m1.canonical_id == m2.canonical_id  # but same canonical_id


def test_search_by_formula(db):
    db.insert_material(_mat("Fe2O3", elements=["Fe", "O"], sid="1"))
    db.insert_material(_mat("TiO2", elements=["O", "Ti"], sid="2"))
    db.insert_material(_mat("Fe2O3", elements=["Fe", "O"], source="aflow", sid="3"))
    results = db.search_materials(formula="Fe2O3")
    assert len(results) == 2


def test_search_by_elements(db):
    db.insert_material(_mat("Fe2O3", elements=["Fe", "O"], sid="1"))
    db.insert_material(_mat("FeS2", elements=["Fe", "S"], sid="2"))
    db.insert_material(_mat("NaCl", elements=["Cl", "Na"], sid="3"))
    results = db.search_materials(elements=["Fe"])
    assert len(results) == 2
    results = db.search_materials(elements=["Fe", "O"])
    assert len(results) == 1


def test_search_by_property_range(db):
    db.insert_material(_mat("A", bg=1.0, sid="1"))
    db.insert_material(_mat("B", bg=2.5, sid="2"))
    db.insert_material(_mat("C", bg=5.0, sid="3"))
    results = db.search_materials(band_gap_min=1.5, band_gap_max=4.0)
    assert len(results) == 1
    assert results[0].formula == "B"


def test_search_compound(db):
    db.insert_material(_mat("A", bg=2.0, elements=["Fe", "O"], sid="1"))
    db.insert_material(_mat("B", bg=3.0, elements=["Fe", "S"], sid="2"))
    db.insert_material(_mat("C", bg=1.0, elements=["Na", "Cl"], sid="3"))
    results = db.search_materials(elements=["Fe"], band_gap_min=2.5)
    assert len(results) == 1
    assert results[0].formula == "B"


def test_stats(db):
    db.insert_material(_mat("A", source="mp", sid="1", cs="Cubic"))
    db.insert_material(_mat("B", source="mp", sid="2", cs="Cubic"))
    db.insert_material(_mat("C", source="aflow", sid="3", cs="Hexagonal"))
    s = db.stats()
    assert s["total"] == 3
    assert s["by_source"]["mp"] == 2
    assert s["by_crystal_system"]["Cubic"] == 2


def test_list_materials_pagination(db):
    for i in range(5):
        db.insert_material(_mat(f"M{i}", sid=str(i)))
    page1 = db.list_materials(limit=2, offset=0)
    page2 = db.list_materials(limit=2, offset=2)
    assert len(page1) == 2
    assert len(page2) == 2
    assert page1[0].formula != page2[0].formula


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
