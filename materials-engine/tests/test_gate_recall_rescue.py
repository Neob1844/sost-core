"""Tests for Phase IV.S: Gate Recall Rescue."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   band_gap=None, source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, band_gap=band_gap,
                 has_valid_structure=True,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


class TestSpec:
    def test_metal_threshold(self):
        from src.hierarchical_bandgap.spec import METAL_THRESHOLD
        assert METAL_THRESHOLD == 0.05

    def test_narrow_range(self):
        from src.hierarchical_bandgap.narrow_gap import NARROW_LOW, NARROW_HIGH
        assert NARROW_LOW == 0.05
        assert NARROW_HIGH == 1.0


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

    def test_status(self):
        r = self._client().get("/gate-recall-rescue/status")
        assert r.status_code == 200
        assert r.json()["phase"] == "IV.S"

    def test_challengers(self):
        assert self._client().get("/gate-recall-rescue/challengers").status_code == 200

    def test_thresholds(self):
        assert self._client().get("/gate-recall-rescue/thresholds").status_code == 200

    def test_benchmark(self):
        assert self._client().get("/gate-recall-rescue/benchmark").status_code == 200

    def test_decision(self):
        assert self._client().get("/gate-recall-rescue/decision").status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/three-tier-band-gap/status").status_code == 200
        assert c.get("/hierarchical-band-gap/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        assert self._client().get("/status").json()["version"] == "3.2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
