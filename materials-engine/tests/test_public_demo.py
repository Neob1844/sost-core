"""Tests for public demo: common names, plain language, smart search, known entities."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.release.common_names import resolve_query, normalize_query, COMMON_NAMES
from src.release.plain_language import explain_material, explain_known_entity


def _m(formula, elements, sg=None, fe=None, bg=None):
    m = Material(formula=formula, elements=sorted(elements), n_elements=len(elements),
                 spacegroup=sg, formation_energy=fe, band_gap=bg,
                 has_valid_structure=True, source="jarvis", source_id=formula, confidence=0.8)
    m.compute_canonical_id()
    return m


class TestNormalization:
    def test_articles_es(self):
        assert normalize_query("el agua") == "agua"
    def test_articles_en(self):
        assert normalize_query("the water") == "water"
    def test_articles_fr(self):
        assert normalize_query("le quartz") == "quartz"
    def test_articles_de(self):
        assert normalize_query("das wasser") == "wasser"
    def test_articles_it(self):
        assert normalize_query("il ferro") == "ferro"
    def test_accents(self):
        assert normalize_query("nitrógeno") == "nitrogeno"
    def test_trim_punct(self):
        assert normalize_query("¿agua?") == "agua"


class TestCommonNames:
    def test_water(self):
        assert resolve_query("water")["resolved"]
    def test_agua(self):
        assert resolve_query("agua")["resolved"]
    def test_wasser(self):
        assert resolve_query("wasser")["resolved"]
    def test_eau(self):
        assert resolve_query("eau")["resolved"]
    def test_acqua(self):
        assert resolve_query("acqua")["resolved"]
    def test_salt(self):
        assert resolve_query("salt")["formula"] == "NaCl"
    def test_air_mixture(self):
        r = resolve_query("air")
        assert not r["resolved"]
        assert r["entity_type"] == "mixture_or_everyday_material"
    def test_nitrogen_molecule(self):
        r = resolve_query("nitrogen")
        assert r["resolved"] and r["formula"] == "N2"
        assert r["entity_type"] == "known_molecule_not_in_corpus"
    def test_nitrogeno(self):
        r = resolve_query("nitrogeno")
        assert r["resolved"] and r["formula"] == "N2"
    def test_helium_noble(self):
        r = resolve_query("helium")
        assert r["resolved"] and r["formula"] == "He"
        assert r["entity_type"] == "elemental_gas_or_noble_gas"
    def test_helio(self):
        r = resolve_query("helio")
        assert r["resolved"]
    def test_steel_everyday(self):
        r = resolve_query("steel")
        assert not r["resolved"]
        assert r["entity_type"] == "mixture_or_everyday_material"
    def test_formula_direct(self):
        r = resolve_query("GaAs")
        assert r["resolved"] and r["formula"] == "GaAs"
    def test_registry_size(self):
        assert len(COMMON_NAMES) >= 80
    def test_uses_present(self):
        r = resolve_query("nitrogen")
        assert len(r.get("uses", [])) > 0
    def test_related_present(self):
        r = resolve_query("nitrogen")
        assert len(r.get("related", [])) > 0


class TestKnownEntityExplainer:
    def test_nitrogen(self):
        r = resolve_query("nitrogen")
        e = explain_known_entity(r)
        assert e["corpus_presence_status"] == "not_in_corpus"
        assert "N2" in e["formula"]
        assert len(e["real_world_uses"]) > 0
        json.dumps(e)

    def test_helium(self):
        r = resolve_query("helium")
        e = explain_known_entity(r)
        assert "noble" in e["title"].lower() or "gas" in e["title"].lower()

    def test_air_mixture(self):
        r = resolve_query("air")
        e = explain_known_entity(r)
        assert "mixture" in e["entity_type"].lower()


class TestPlainLanguage:
    def test_prudent_language(self):
        m = _m("GaAs", ["As", "Ga"], 216, -0.7, 1.4)
        e = explain_material(m)
        assert "heuristic" in e["honesty_note"].lower()
        assert e["_meta"]["not_market_price"] is True

    def test_limitations_not_empty(self):
        m = _m("Si", ["Si"], 227, 0.0, 1.1)
        e = explain_material(m)
        assert len(e["main_limitations"]) > 0
        # Should have some limitation, not just empty praise
        assert e["main_limitations"][0] != ""


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

    def test_nitrogen_known_entity(self):
        r = self._client().get("/smart-search?q=nitrogen")
        d = r.json()
        assert d["resolved"]
        assert "entity_explanation" in d

    def test_helium_known_entity(self):
        r = self._client().get("/smart-search?q=helio")
        d = r.json()
        assert "entity_explanation" in d

    def test_air_mixture(self):
        r = self._client().get("/smart-search?q=air")
        d = r.json()
        assert not d["resolved"]
        assert "entity_explanation" in d

    def test_formula_with_variants(self):
        r = self._client().get("/smart-search?q=GaAs")
        d = r.json()
        assert d["resolved"]
        assert "grouped" in d

    def test_explain_nitrogen(self):
        r = self._client().get("/explain-formula/nitrogen")
        d = r.json()
        assert d["corpus_presence_status"] == "not_in_corpus"

    def test_explain_air(self):
        r = self._client().get("/explain-formula/air")
        d = r.json()
        assert "mixture" in d.get("entity_type", "")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
