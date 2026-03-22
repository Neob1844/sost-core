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
        assert len(COMMON_NAMES) >= 100

    # Multilingual: RU/ZH/JA/AR
    def test_ru_water(self):
        assert resolve_query("\u0432\u043e\u0434\u0430")["resolved"]
    def test_ru_gold(self):
        r = resolve_query("\u0437\u043e\u043b\u043e\u0442\u043e")
        assert r["resolved"] and r["formula"] == "Au"
    def test_ru_helium(self):
        r = resolve_query("\u0433\u0435\u043b\u0438\u0439")
        assert r["resolved"] and r["formula"] == "He"
    def test_zh_water(self):
        assert resolve_query("\u6c34")["resolved"]
    def test_zh_gold(self):
        r = resolve_query("\u91d1")
        assert r["resolved"] and r["formula"] == "Au"
    def test_ja_air(self):
        r = resolve_query("\u7a7a\u6c17")
        assert not r["resolved"]
        assert r["entity_type"] == "mixture_or_everyday_material"
    def test_ar_gold(self):
        r = resolve_query("\u0630\u0647\u0628")
        assert r["resolved"] and r["formula"] == "Au"
    def test_ar_salt(self):
        r = resolve_query("\u0645\u0644\u062d")
        assert r["resolved"] and r["formula"] == "NaCl"
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
        assert e["main_limitations"][0] != ""

    def test_au_not_metastable(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert e["stability_assessment"]["label"] != "metastable"
        assert "reference" in e["stability_assessment"]["label"]

    def test_au_elemental_reference(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert e["elemental_reference"] is True
        assert "PRECIOUS METAL" in e.get("material_tags", [])

    def test_au_not_low_value(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert e["practical_value"]["label"] != "low"

    def test_au_apps_no_structural(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert not any("structural component" in a.lower() for a in e["what_it_can_do"])

    def test_au_value_breakdown(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        vb = e.get("value_breakdown", {})
        assert vb["strategic_significance"]["label"] == "very_high"
        assert vb["bulk_vs_specialty"]["label"] == "specialty"

    def test_gaas_has_value_breakdown(self):
        m = _m("GaAs", ["As", "Ga"], 216, -0.7, 1.4)
        e = explain_material(m)
        assert "value_breakdown" in e


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

    def test_canonical_result_present(self):
        r = self._client().get("/smart-search?q=GaAs")
        d = r.json()
        assert "canonical_result" in d
        if d["canonical_result"]:
            assert "canonical_id" in d["canonical_result"] or "formula" in d["canonical_result"]

    def test_canonical_reason_present(self):
        r = self._client().get("/smart-search?q=NaCl")
        d = r.json()
        assert "canonical_reason" in d
        assert len(d["canonical_reason"]) > 0

    def test_ranking_in_grouped_variants(self):
        r = self._client().get("/smart-search?q=GaAs")
        d = r.json()
        if d.get("grouped") and d["grouped"][0]["variants"]:
            v = d["grouped"][0]["variants"][0]
            assert "_ranking" in v
            assert "score" in v["_ranking"]

    def test_visible_variants_limit(self):
        r = self._client().get("/smart-search?q=SiO2")
        d = r.json()
        if d.get("grouped"):
            g = d["grouped"][0]
            assert "visible_variants" in g
            assert "extra_variants_count" in g

    def test_explain_nitrogen(self):
        r = self._client().get("/explain-formula/nitrogen")
        d = r.json()
        assert d["corpus_presence_status"] == "not_in_corpus"

    def test_explain_air(self):
        r = self._client().get("/explain-formula/air")
        d = r.json()
        assert "mixture" in d.get("entity_type", "")


class TestRarity:
    def test_au_rarity(self):
        from src.release.rarity import get_rarity
        r = get_rarity(["Au"])
        assert r is not None
        assert "rare" in r["rarity"]["label"]
        assert r["crust_abundance"]["technical"]["value"] == 0.004

    def test_fe_abundant(self):
        from src.release.rarity import get_rarity
        r = get_rarity(["Fe"])
        assert "abundant" in r["rarity"]["label"]

    def test_compound_limiting(self):
        from src.release.rarity import get_rarity
        r = get_rarity(["Ga", "As"])
        assert r["crust_abundance"]["scope"] == "limiting_element_abundance"

    def test_rarity_in_explain(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert e.get("rarity") is not None
        assert "rare" in e["rarity"]["rarity"]["label"]


class TestFlagshipCuration:
    def test_ag_sectors(self):
        m = _m("Ag", ["Ag"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert e["industry_relevance"]["electronics"] == "high"
        assert e["industry_relevance"]["optics"] == "high"

    def test_si_strategic(self):
        m = _m("Si", ["Si"], 227, 0.0, 1.1)
        e = explain_material(m)
        vb = e["value_breakdown"]
        assert vb["strategic_significance"]["label"] == "very_high"

    def test_pt_catalysis(self):
        m = _m("Pt", ["Pt"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert e["industry_relevance"]["catalysis"] == "extra_high"
        assert "PRECIOUS METAL" in e["material_tags"]

    def test_gaas_sectors(self):
        m = _m("GaAs", ["As", "Ga"], 216, -0.7, 1.4)
        e = explain_material(m)
        assert e["industry_relevance"]["electronics"] == "extra_high"
        assert e["industry_relevance"]["construction"] == "extra_low"

    def test_comparisons_au(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert len(e["human_comparisons"]) >= 2
        assert any("rare" in c.lower() for c in e["human_comparisons"])

    def test_comparisons_si(self):
        m = _m("Si", ["Si"], 227, 0.0, 1.1)
        e = explain_material(m)
        assert len(e["human_comparisons"]) >= 2

    def test_public_importance_au(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        assert "strategically important" in e["public_importance_summary"]["label"]

    def test_public_importance_generic(self):
        m = _m("XYZ", ["X", "Y", "Z"], 62, -1.0, 2.0)
        e = explain_material(m)
        assert "public_importance_summary" in e

    def test_li_energy(self):
        m = _m("Li", ["Li"], 229, 0.0, 0.0)
        e = explain_material(m)
        assert e["industry_relevance"]["energy"] == "extra_high"
        assert "STRATEGIC MATERIAL" in e["material_tags"]


class TestTrustAndAbundance:
    def test_au_trust_breakdown(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        tb = e.get("trust_breakdown")
        assert tb is not None
        assert "formula" in tb["known_corpus_fields"]
        assert len(tb["heuristic_fields"]) > 0
        assert "elemental_reference_label" in tb["manual_override_fields"]
        assert tb["confidence_summary"]["overall"] == "high"

    def test_au_abundance_single_element(self):
        m = _m("Au", ["Au"], 225, 0.0, 0.0)
        e = explain_material(m)
        aa = e.get("abundance_analysis")
        assert aa is not None
        assert aa["elemental_abundance_basis"]["mode"] == "single_element"
        assert aa["confidence"] == "high"

    def test_gaas_abundance_proxy(self):
        m = _m("GaAs", ["As", "Ga"], 216, -0.7, 1.4)
        e = explain_material(m)
        aa = e.get("abundance_analysis")
        assert aa is not None
        assert aa["elemental_abundance_basis"]["mode"] == "rarest_element_proxy"
        assert "proxy" in aa["scope"].lower() or "not" in aa["scope"].lower()
        assert aa["confidence"] == "medium"

    def test_complex_compound_low_confidence(self):
        m = _m("LiMgAlSi", ["Al", "Li", "Mg", "Si"], 62, -0.5, 0.3)
        e = explain_material(m)
        aa = e.get("abundance_analysis")
        assert aa is not None
        assert aa["confidence"] == "low"

    def test_trust_has_heuristic_fields(self):
        m = _m("GaAs", ["As", "Ga"], 216, -0.7, 1.4)
        e = explain_material(m)
        tb = e["trust_breakdown"]
        assert "practical_value" in tb["heuristic_fields"]
        assert "industry_relevance" in tb["heuristic_fields"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
