"""Tests for Phase IV.T: Engine Stabilization + Release Candidate."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.release.manifest import (
    generate_release_manifest, generate_production_freeze,
    generate_api_audit, save_all_release_artifacts,
)


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   band_gap=None, source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, band_gap=band_gap,
                 has_valid_structure=True,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


class TestManifest:
    @pytest.fixture(autouse=True)
    def setup(self):
        from src.api.server import app
        self.app = app
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        self.db = MaterialsDB(f.name)
        m = _make_material("Si", ["Si"], 227, 0.0, 1.1)
        self.db.insert_material(m)
        yield
        os.unlink(f.name)

    def test_manifest_structure(self):
        m = generate_release_manifest(self.db, self.app)
        assert "version" in m
        assert "corpus" in m
        assert "production_models" in m
        assert "api" in m
        assert "limitations" in m
        json.dumps(m)

    def test_manifest_has_corpus(self):
        m = generate_release_manifest(self.db, self.app)
        assert m["corpus"]["total_materials"] > 0

    def test_freeze_structure(self):
        f = generate_production_freeze(self.db)
        assert "production_models" in f
        assert "formation_energy" in f["production_models"]
        assert "band_gap" in f["production_models"]
        assert "do_not_change" in f
        json.dumps(f)

    def test_freeze_models(self):
        f = generate_production_freeze(self.db)
        assert f["production_models"]["formation_energy"]["test_mae"] == 0.1528
        assert f["production_models"]["band_gap"]["test_mae"] == 0.3422

    def test_api_audit(self):
        audit = generate_api_audit(self.app)
        assert len(audit) > 50
        stabilities = set(e["stability"] for e in audit)
        assert "production" in stabilities
        json.dumps(audit)

    def test_save_artifacts(self):
        td = tempfile.mkdtemp()
        m = generate_release_manifest(self.db, self.app)
        f = generate_production_freeze(self.db)
        a = generate_api_audit(self.app)
        save_all_release_artifacts(m, f, a, output_dir=td)
        for fname in ("materials_engine_release_manifest.json",
                      "materials_engine_release_manifest.md",
                      "production_freeze.json", "production_freeze.md",
                      "api_audit.json", "api_audit.md"):
            assert os.path.exists(os.path.join(td, fname)), f"Missing: {fname}"


class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        m = _make_material("Si", ["Si"], 227, 0.0, 1.1)
        srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_release_status(self):
        r = self._client().get("/release/status")
        assert r.status_code == 200
        assert "3.2.0" in r.json()["version"]

    def test_release_manifest(self):
        assert self._client().get("/release/manifest").status_code == 200

    def test_release_api_audit(self):
        assert self._client().get("/release/api-audit").status_code == 200

    def test_release_production_freeze(self):
        assert self._client().get("/release/production-freeze").status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200
        assert c.get("/hierarchical-band-gap/status").status_code == 200
        assert c.get("/gate-recall-rescue/status").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert "3.2.0" in d["version"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
