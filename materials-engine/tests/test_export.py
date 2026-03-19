"""Tests for dataset export."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.export.dataset import export_dataset


@pytest.fixture
def populated_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = MaterialsDB(f.name)
    for i in range(20):
        m = Material(formula=f"M{i}", source="test", source_id=str(i),
                     band_gap=float(i % 5), formation_energy=-float(i) / 10,
                     elements=[f"E{i%4}"], n_elements=1, confidence=0.8)
        m.compute_canonical_id()
        db.insert_material(m)
    yield db
    os.unlink(f.name)


def test_export_creates_files(populated_db):
    with tempfile.TemporaryDirectory() as td:
        manifest = export_dataset(populated_db, "test_bg", ["band_gap"], output_dir=td)
        assert manifest["total"] > 0
        assert os.path.exists(os.path.join(td, "test_bg_train.csv"))
        assert os.path.exists(os.path.join(td, "test_bg_val.csv"))
        assert os.path.exists(os.path.join(td, "test_bg_test.csv"))
        assert os.path.exists(os.path.join(td, "test_bg_manifest.json"))


def test_export_manifest_fields(populated_db):
    with tempfile.TemporaryDirectory() as td:
        manifest = export_dataset(populated_db, "test_fe", ["formation_energy"],
                                  output_dir=td, seed=123)
        assert manifest["seed"] == 123
        assert manifest["dataset_hash"]
        assert manifest["train"] + manifest["val"] + manifest["test"] == manifest["total"]


def test_export_reproducible(populated_db):
    with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
        m1 = export_dataset(populated_db, "repro", ["band_gap"], output_dir=td1, seed=42)
        m2 = export_dataset(populated_db, "repro", ["band_gap"], output_dir=td2, seed=42)
        assert m1["dataset_hash"] == m2["dataset_hash"]


def test_export_empty_dataset(populated_db):
    with tempfile.TemporaryDirectory() as td:
        manifest = export_dataset(populated_db, "empty", ["bulk_modulus"], output_dir=td)
        assert manifest.get("total", 0) == 0 or "error" in manifest


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
