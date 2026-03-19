"""Tests for structure backfill."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.backfill.structure_backfill import (
    pre_backfill_audit, post_backfill_audit, save_audit,
)


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   structure_data=None, source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy,
                 structure_data=structure_data,
                 has_valid_structure=structure_data is not None,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


@pytest.fixture
def test_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = MaterialsDB(f.name)
    # Mix of with/without structure
    db.insert_material(_make_material("NaCl", ["Cl", "Na"], 225, -4.2,
                                       structure_data="data_NaCl\n_cell_length_a 5.64"))
    db.insert_material(_make_material("Si", ["Si"], 227, 0.0))  # no structure
    db.insert_material(_make_material("Fe2O3", ["Fe", "O"], 167, -1.5))  # no structure
    yield db
    os.unlink(f.name)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


class TestAudit:
    def test_pre_audit(self, test_db):
        audit = pre_backfill_audit(test_db.db_path)
        assert audit["total_materials"] == 3
        assert audit["with_structure_data"] == 1
        assert audit["without_structure_data"] == 2

    def test_post_audit(self, test_db):
        audit = post_backfill_audit(test_db.db_path)
        assert audit["total_materials"] == 3

    def test_save_audit(self, test_db, temp_dir):
        audit = pre_backfill_audit(test_db.db_path)
        path = save_audit(audit, "test_audit", output_dir=temp_dir)
        assert os.path.exists(path)
        md_path = os.path.join(temp_dir, "test_audit.md")
        assert os.path.exists(md_path)

    def test_audit_coverage_pct(self, test_db):
        audit = pre_backfill_audit(test_db.db_path)
        assert audit["structure_coverage_pct"] > 0


class TestRealCorpusBackfill:
    """Tests against the real backfilled corpus."""

    def test_corpus_intact(self):
        db = MaterialsDB("materials.db")
        assert db.count() == 75993

    def test_all_have_structure(self):
        import sqlite3
        conn = sqlite3.connect("materials.db")
        without = conn.execute(
            "SELECT COUNT(*) FROM materials WHERE structure_data IS NULL OR structure_data=''").fetchone()[0]
        conn.close()
        assert without == 0

    def test_all_valid_structure(self):
        import sqlite3
        conn = sqlite3.connect("materials.db")
        valid = conn.execute(
            "SELECT COUNT(*) FROM materials WHERE has_valid_structure=1").fetchone()[0]
        conn.close()
        assert valid == 75993

    def test_sample_structure_parseable(self):
        """Verify a sample structure can be parsed by pymatgen."""
        from pymatgen.core import Structure
        import sqlite3
        conn = sqlite3.connect("materials.db")
        row = conn.execute(
            "SELECT structure_data FROM materials WHERE structure_data IS NOT NULL LIMIT 1 OFFSET 5000").fetchone()
        conn.close()
        struct = Structure.from_str(row[0], fmt="cif")
        assert len(struct) > 0

    def test_analytics_now_available(self):
        """After backfill, analytics should work on any corpus material."""
        from src.analytics.descriptors import compute_descriptors
        from src.normalization.structure import load_structure
        import sqlite3
        conn = sqlite3.connect("materials.db")
        row = conn.execute(
            "SELECT formula, structure_data FROM materials WHERE source_id='JVASP-10'").fetchone()
        conn.close()
        if row:
            struct = load_structure(row[1])
            desc = compute_descriptors(structure=struct, formula=row[0])
            assert "density_g_cm3" in desc
            assert desc["density_g_cm3"]["value"] is not None
            assert desc["density_g_cm3"]["value"] > 0


class TestBackwardCompatibility:
    """Verify nothing broke."""

    def test_api_status(self):
        from fastapi.testclient import TestClient
        import src.api.server as srv
        srv._db = MaterialsDB("materials.db")
        from src.api.server import app
        client = TestClient(app)
        r = client.get("/status")
        assert r.status_code == 200
        assert r.json()["materials_count"] == 75993
        srv._db = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
