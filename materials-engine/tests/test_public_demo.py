"""Tests for public demo: common names, plain language, smart search."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.release.common_names import resolve_query, COMMON_NAMES
from src.release.plain_language import explain_material


def _m(formula, elements, sg=None, fe=None, bg=None):
    m = Material(formula=formula, elements=sorted(elements), n_elements=len(elements),
                 spacegroup=sg, formation_energy=fe, band_gap=bg,
                 has_valid_structure=True, source="jarvis", source_id=formula, confidence=0.8)
    m.compute_canonical_id()
    return m


class TestCommonNames:
    def test_water(self):
        r = resolve_query("water")
        assert r["resolved"] and r["formula"] == "H2O"

    def test_agua(self):
        r = resolve_query("agua")
        assert r["resolved"] and r["formula"] == "H2O"

    def test_salt(self):
        r = resolve_query("salt")
        assert r["resolved"] and r["formula"] == "NaCl"

    def test_quartz(self):
        r = resolve_query("quartz")
        assert r["resolved"] and r["formula"] == "SiO2"

    def test_air_is_mixture(self):
        r = resolve_query("air")
        assert not r["resolved"]
        assert r["entity_type"] == "mixture"
        assert "mixture" in r["note"].lower() or "mezcla" in r["note"].lower()

    def test_steel_is_everyday(self):
        r = resolve_query("steel")
        assert not r["resolved"]
        assert r["entity_type"] == "everyday"

    def test_formula_direct(self):
        r = resolve_query("GaAs")
        assert r["resolved"] and r["formula"] == "GaAs"

    def test_unknown(self):
        r = resolve_query("xyznotreal")
        assert not r["resolved"]

    def test_registry_size(self):
        assert len(COMMON_NAMES) >= 50


class TestPlainLanguage:
    def test_semiconductor(self):
        m = _m("GaAs", ["As", "Ga"], 216, -0.7, 1.4)
        e = explain_material(m)
        assert e["electronic_behavior"]["label"] == "semiconductor"
        assert "high" in json.dumps(e["industry_relevance"])

    def test_metal(self):
        m = _m("Fe", ["Fe"], 229, -0.5, 0.0)
        e = explain_material(m)
        assert e["electronic_behavior"]["label"] == "metal"

    def test_insulator(self):
        m = _m("NaCl", ["Cl", "Na"], 225, -4.0, 5.0)
        e = explain_material(m)
        assert e["electronic_behavior"]["label"] in ("insulator", "wide-gap semiconductor")

    def test_exotic(self):
        m = _m("HfZrTiNiSn", ["Hf", "Ni", "Sn", "Ti", "Zr"], 216, -0.3, 0.5)
        e = explain_material(m)
        assert e["is_it_exotic"]["label"] == "highly exotic"

    def test_honesty_note(self):
        m = _m("Si", ["Si"], 227, 0.0, 1.1)
        e = explain_material(m)
        assert "heuristic" in e["honesty_note"].lower()
        assert e["_meta"]["not_market_price"] is True

    def test_serializable(self):
        m = _m("GaAs", ["As", "Ga"], 216, -0.7, 1.4)
        json.dumps(explain_material(m))


class TestSmartSearchAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        for m in [_m("GaAs", ["As", "Ga"], 216, -0.7, 1.4),
                  _m("NaCl", ["Cl", "Na"], 225, -4.0, 5.0),
                  _m("SiO2", ["O", "Si"], 152, -3.0, 6.0)]:
            srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_smart_search_formula(self):
        r = self._client().get("/smart-search?q=GaAs")
        assert r.status_code == 200
        assert r.json()["resolved"]
        assert len(r.json()["results"]) >= 1

    def test_smart_search_common_name(self):
        r = self._client().get("/smart-search?q=salt")
        assert r.status_code == 200
        assert r.json()["resolved"]

    def test_smart_search_mixture(self):
        r = self._client().get("/smart-search?q=air")
        assert r.status_code == 200
        assert not r.json()["resolved"]
        assert r.json()["resolution"]["entity_type"] == "mixture"

    def test_explain_formula(self):
        r = self._client().get("/explain-formula/GaAs")
        assert r.status_code == 200
        assert "electronic_behavior" in r.json()

    def test_explain_common(self):
        r = self._client().get("/explain-formula/quartz")
        assert r.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
