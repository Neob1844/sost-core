"""Tests for data audit module."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.audit.data_audit import run_audit


@pytest.fixture
def populated_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = MaterialsDB(f.name)
    for i, (formula, bg, fe) in enumerate([
        ("Fe2O3", 2.1, -1.5),
        ("TiO2", 3.2, -2.0),
        ("NaCl", 8.5, None),
        ("Si", 1.1, 0.0),
        ("Cu", None, None),
    ]):
        m = Material(formula=formula, source="test", source_id=str(i),
                     band_gap=bg, formation_energy=fe,
                     elements=[formula[:2]], n_elements=1, confidence=0.8)
        m.compute_canonical_id()
        db.insert_material(m)
    yield db
    os.unlink(f.name)


def test_audit_counts(populated_db):
    counts = populated_db.audit_counts()
    assert counts["total"] == 5
    assert counts["with_band_gap"] == 4
    assert counts["with_formation_energy"] == 3
    assert counts["ml_ready_bg"] == 4


def test_run_audit_produces_artifacts(populated_db):
    with tempfile.TemporaryDirectory() as td:
        result = run_audit(populated_db, output_dir=td)
        assert result["total_materials"] == 5
        assert os.path.exists(os.path.join(td, "data_audit.json"))
        assert os.path.exists(os.path.join(td, "data_audit.md"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
