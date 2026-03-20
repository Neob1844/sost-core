"""Tests for shortlist engine, criteria, ranking, T/P proxy screening, and API.

Phase III.B: Comprehensive tests for candidate selection pipeline.
"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.shortlist.criteria import (
    ShortlistCriteria, CriteriaValidationError,
    default_criteria, stability_focused, novelty_focused,
)
from src.shortlist.ranking import (
    CandidateResult, compute_stability_score, compute_property_fit,
    assign_decision, ACCEPTED_THRESHOLD, WATCHLIST_THRESHOLD,
)
from src.shortlist.engine import ShortlistEngine
from src.thermo.conditions import ThermoPressureConditions
from src.thermo.proxies import screen_tp_proxy, screen_tp_batch


# ================================================================
# Helpers
# ================================================================

def _make_material(formula, elements, spacegroup=None, band_gap=None,
                   formation_energy=None, crystal_system=None,
                   has_valid_structure=True, source="test", source_id=None):
    m = Material(
        formula=formula, elements=sorted(elements), n_elements=len(elements),
        spacegroup=spacegroup, band_gap=band_gap,
        formation_energy=formation_energy, crystal_system=crystal_system,
        has_valid_structure=has_valid_structure,
        source=source, source_id=source_id or formula,
        confidence=0.8,
    )
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("Fe2O3", ["Fe", "O"], spacegroup=167, band_gap=2.1,
                   formation_energy=-1.5, crystal_system="hexagonal"),
    _make_material("TiO2", ["O", "Ti"], spacegroup=136, band_gap=3.2,
                   formation_energy=-3.4, crystal_system="tetragonal"),
    _make_material("NaCl", ["Cl", "Na"], spacegroup=225, band_gap=8.5,
                   formation_energy=-4.2, crystal_system="cubic"),
    _make_material("Si", ["Si"], spacegroup=227, band_gap=1.1,
                   formation_energy=0.0, crystal_system="cubic"),
    _make_material("GaAs", ["As", "Ga"], spacegroup=216, band_gap=1.4,
                   formation_energy=-0.7, crystal_system="cubic"),
    _make_material("UPu3", ["Pu", "U"], spacegroup=12, band_gap=0.0,
                   formation_energy=1.5, crystal_system="monoclinic"),
    _make_material("FeS", ["Fe", "S"], spacegroup=62, band_gap=0.0,
                   formation_energy=-0.5, crystal_system="orthorhombic",
                   has_valid_structure=False, source_id="FeS_broken"),
]


@pytest.fixture
def test_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = MaterialsDB(f.name)
    for m in CORPUS:
        db.insert_material(m)
    yield db
    os.unlink(f.name)


# ================================================================
# Criteria tests
# ================================================================

class TestCriteria:
    def test_default_valid(self):
        c = default_criteria()
        c.validate()

    def test_stability_focused_valid(self):
        c = stability_focused()
        c.validate()

    def test_novelty_focused_valid(self):
        c = novelty_focused()
        c.validate()

    def test_weights_must_sum_to_one(self):
        c = ShortlistCriteria(w_novelty=0.5, w_exotic=0.5,
                              w_stability=0.5, w_property_fit=0.5)
        with pytest.raises(CriteriaValidationError, match="sum to 1.0"):
            c.validate()

    def test_negative_weight_rejected(self):
        c = ShortlistCriteria(w_novelty=-0.1, w_exotic=0.4,
                              w_stability=0.4, w_property_fit=0.3)
        with pytest.raises(CriteriaValidationError):
            c.validate()

    def test_top_k_must_be_positive(self):
        c = ShortlistCriteria(top_k=0)
        with pytest.raises(CriteriaValidationError, match="top_k"):
            c.validate()

    def test_novelty_min_range(self):
        c = ShortlistCriteria(novelty_min=1.5)
        with pytest.raises(CriteriaValidationError, match="novelty_min"):
            c.validate()

    def test_to_dict(self):
        c = default_criteria()
        d = c.to_dict()
        assert "w_novelty" in d
        assert "top_k" in d

    def test_from_dict(self):
        d = {"top_k": 10, "max_formation_energy": 0.5}
        c = ShortlistCriteria.from_dict(d)
        assert c.top_k == 10
        assert c.max_formation_energy == 0.5

    def test_to_json_roundtrip(self):
        c = default_criteria()
        j = c.to_json()
        c2 = ShortlistCriteria.from_dict(json.loads(j))
        assert c2.top_k == c.top_k
        assert c2.w_novelty == c.w_novelty


# ================================================================
# Ranking tests
# ================================================================

class TestRanking:
    def test_stability_score_negative_fe(self):
        s = compute_stability_score(-3.0)
        assert s > 0.8

    def test_stability_score_zero_fe(self):
        s = compute_stability_score(0.0)
        assert 0.3 < s < 0.6

    def test_stability_score_positive_fe(self):
        s = compute_stability_score(1.5)
        assert s < 0.2

    def test_stability_score_none(self):
        s = compute_stability_score(None)
        assert s == 0.3

    def test_stability_score_with_hull(self):
        base = compute_stability_score(-1.0)
        boosted = compute_stability_score(-1.0, energy_above_hull=0.01)
        assert boosted > base

    def test_property_fit_exact_match(self):
        s = compute_property_fit(1.5, target=1.5)
        assert s == 1.0

    def test_property_fit_no_target(self):
        s = compute_property_fit(1.5, target=None)
        assert s == 0.5

    def test_property_fit_missing_data(self):
        s = compute_property_fit(None, target=1.5)
        assert s == 0.3

    def test_property_fit_distance(self):
        s = compute_property_fit(3.0, target=1.0, tolerance=2.0)
        assert s == 0.0

    def test_decision_accepted(self):
        d = assign_decision(0.5, [])
        assert d == "accepted"

    def test_decision_watchlist(self):
        d = assign_decision(0.2, [])
        assert d == "watchlist"

    def test_decision_rejected_low_score(self):
        d = assign_decision(0.05, [])
        assert d == "rejected"

    def test_decision_rejected_hard_filter(self):
        d = assign_decision(0.9, ["missing_required_property"])
        assert d == "rejected"

    def test_candidate_to_dict(self):
        c = CandidateResult(canonical_id="abc", formula="Fe2O3",
                            shortlist_score=0.5, decision="accepted")
        d = c.to_dict()
        assert d["decision"] == "accepted"
        assert "scores" in d


# ================================================================
# T/P Proxy tests
# ================================================================

class TestTPProxy:
    def test_ambient_low_risk(self):
        m = _make_material("Si", ["Si"], spacegroup=227, crystal_system="cubic")
        cond = ThermoPressureConditions()
        r = screen_tp_proxy(m, cond)
        assert r["risk_level"] == "low"
        assert r["reliability"] == "baseline_ambient"

    def test_high_temp_risk(self):
        m = _make_material("NaCl", ["Cl", "Na"], spacegroup=225, crystal_system="cubic")
        cond = ThermoPressureConditions(temperature_K=2000.0)
        r = screen_tp_proxy(m, cond)
        assert r["risk_level"] in ("medium", "high")
        assert r["reliability"] == "experimental_proxy"

    def test_high_pressure_risk(self):
        m = _make_material("FeS", ["Fe", "S"], spacegroup=62, crystal_system="orthorhombic")
        cond = ThermoPressureConditions(pressure_GPa=50.0)
        r = screen_tp_proxy(m, cond)
        assert r["risk_level"] in ("medium", "high")

    def test_extreme_conditions(self):
        m = _make_material("TiO2", ["O", "Ti"], crystal_system="tetragonal")
        cond = ThermoPressureConditions(temperature_K=3000.0, pressure_GPa=100.0)
        r = screen_tp_proxy(m, cond)
        assert r["risk_level"] == "high"
        assert r["phase_transition_risk"] == "high"

    def test_triclinic_sensitivity(self):
        m = _make_material("X", ["Fe"], crystal_system="triclinic")
        cond = ThermoPressureConditions(temperature_K=800.0)
        r = screen_tp_proxy(m, cond)
        # Triclinic is most sensitive
        assert r["note"]  # has method documentation

    def test_batch_screening(self):
        materials = [
            _make_material("Si", ["Si"], crystal_system="cubic"),
            _make_material("NaCl", ["Cl", "Na"], crystal_system="cubic"),
        ]
        cond = ThermoPressureConditions(temperature_K=1000.0)
        results = screen_tp_batch(materials, cond)
        assert len(results) == 2
        assert all("risk_level" in r for r in results)

    def test_proxy_has_method_note(self):
        m = _make_material("Fe2O3", ["Fe", "O"], crystal_system="hexagonal")
        cond = ThermoPressureConditions(temperature_K=500.0, pressure_GPa=5.0)
        r = screen_tp_proxy(m, cond)
        assert "heuristic" in r["note"].lower()
        assert r["method"] == "heuristic_proxy"

    def test_cubic_high_symmetry_resilient(self):
        m = _make_material("NaCl", ["Cl", "Na"], spacegroup=225, crystal_system="cubic")
        cond = ThermoPressureConditions(pressure_GPa=15.0)
        r = screen_tp_proxy(m, cond)
        # Cubic with moderate pressure should be low risk
        assert r["risk_level"] == "low"

    def test_low_symmetry_pressure_sensitive(self):
        m = _make_material("X", ["Fe"], spacegroup=2, crystal_system="triclinic")
        cond = ThermoPressureConditions(pressure_GPa=15.0)
        r = screen_tp_proxy(m, cond)
        assert r["risk_level"] in ("medium", "high")


# ================================================================
# Engine integration tests
# ================================================================

class TestShortlistEngine:
    def test_build_default(self, test_db):
        engine = ShortlistEngine(test_db)
        result = engine.build()
        assert "pool_size" in result
        assert "shortlist" in result
        assert "decisions" in result
        assert "disclaimer" in result

    def test_build_has_decisions(self, test_db):
        engine = ShortlistEngine(test_db)
        result = engine.build()
        d = result["decisions"]
        assert d["accepted"] + d["watchlist"] + d["rejected"] == result["evaluated"]

    def test_invalid_structure_rejected(self, test_db):
        engine = ShortlistEngine(test_db)
        criteria = ShortlistCriteria(require_valid_structure=True)
        result = engine.build(criteria=criteria)
        # FeS_broken has has_valid_structure=False → rejected when required
        assert result["decisions"]["rejected"] >= 1

    def test_formation_energy_filter(self, test_db):
        engine = ShortlistEngine(test_db)
        criteria = ShortlistCriteria(max_formation_energy=0.0)
        result = engine.build(criteria=criteria)
        # UPu3 (fe=1.5) and Si (fe=0.0 but not > 0.0) should be filtered
        for c in result["shortlist"]:
            if c["formation_energy"] is not None:
                assert c["formation_energy"] <= 0.0

    def test_with_conditions(self, test_db):
        engine = ShortlistEngine(test_db)
        cond = ThermoPressureConditions(temperature_K=1500.0, pressure_GPa=10.0)
        result = engine.build(conditions=cond)
        assert result["conditions"] is not None
        # Check that screening_reliability is set
        for c in result["shortlist"]:
            assert c["screening_reliability"] != "not_available"

    def test_ranking_is_sorted(self, test_db):
        engine = ShortlistEngine(test_db)
        result = engine.build()
        scores = [c["scores"]["shortlist"] for c in result["shortlist"]]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_respected(self, test_db):
        engine = ShortlistEngine(test_db)
        criteria = ShortlistCriteria(top_k=2)
        result = engine.build(criteria=criteria)
        assert len(result["shortlist"]) <= 2

    def test_custom_weights(self, test_db):
        engine = ShortlistEngine(test_db)
        criteria = ShortlistCriteria(
            w_novelty=0.0, w_exotic=0.0,
            w_stability=1.0, w_property_fit=0.0)
        result = engine.build(criteria=criteria)
        # Should rank by stability only
        for c in result["shortlist"]:
            assert c["scores"]["stability"] > 0

    def test_band_gap_target(self, test_db):
        engine = ShortlistEngine(test_db)
        criteria = ShortlistCriteria(band_gap_target=1.5, band_gap_tolerance=1.0)
        result = engine.build(criteria=criteria)
        # Materials close to 1.5 eV should rank higher
        assert len(result["shortlist"]) > 0

    def test_reason_codes_present(self, test_db):
        engine = ShortlistEngine(test_db)
        result = engine.build()
        # At least some candidates should have reason codes
        has_reasons = any(c["reason_codes"] for c in result["shortlist"])
        assert has_reasons or result["shortlist_size"] == 0

    def test_reproducible(self, test_db):
        engine = ShortlistEngine(test_db)
        r1 = engine.build()
        r2 = engine.build()
        scores1 = [c["scores"]["shortlist"] for c in r1["shortlist"]]
        scores2 = [c["scores"]["shortlist"] for c in r2["shortlist"]]
        assert scores1 == scores2


# ================================================================
# Edge cases
# ================================================================

class TestEdgeCases:
    def test_empty_corpus(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        engine = ShortlistEngine(db)
        result = engine.build()
        assert result["pool_size"] == 0
        assert result["shortlist_size"] == 0
        os.unlink(f.name)

    def test_single_material(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        m = _make_material("Si", ["Si"], spacegroup=227, formation_energy=0.0)
        db.insert_material(m)
        engine = ShortlistEngine(db)
        result = engine.build()
        assert result["pool_size"] == 1
        os.unlink(f.name)

    def test_all_rejected(self, test_db):
        engine = ShortlistEngine(test_db)
        # Impossible criteria → all rejected
        criteria = ShortlistCriteria(novelty_min=0.99)
        result = engine.build(criteria=criteria)
        assert result["shortlist_size"] == 0
        assert result["decisions"]["rejected"] > 0

    def test_materials_without_properties(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        m = Material(formula="X", elements=["Fe"], n_elements=1,
                     source="test", source_id="bare")
        m.compute_canonical_id()
        db.insert_material(m)
        engine = ShortlistEngine(db)
        result = engine.build()
        # Missing formation_energy → rejected by default criteria
        assert result["decisions"]["rejected"] >= 1
        os.unlink(f.name)

    def test_provided_materials(self, test_db):
        engine = ShortlistEngine(test_db)
        custom = [_make_material("Si", ["Si"], spacegroup=227,
                                 formation_energy=-0.5, band_gap=1.1)]
        result = engine.build(materials=custom)
        assert result["pool_size"] == 1


# ================================================================
# Serialization tests
# ================================================================

class TestSerialization:
    def test_shortlist_json_serializable(self, test_db):
        engine = ShortlistEngine(test_db)
        result = engine.build()
        json.dumps(result)  # must not raise

    def test_criteria_roundtrip(self):
        c = default_criteria()
        j = c.to_json()
        c2 = ShortlistCriteria.from_dict(json.loads(j))
        assert c2.to_dict() == c.to_dict()

    def test_tp_result_serializable(self):
        m = _make_material("Si", ["Si"], crystal_system="cubic")
        cond = ThermoPressureConditions(temperature_K=1000.0)
        r = screen_tp_proxy(m, cond)
        json.dumps(r)  # must not raise


# ================================================================
# API endpoint tests
# ================================================================

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        import src.api.server as srv
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        for m in CORPUS:
            srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_get_default_criteria(self):
        client = self._client()
        r = client.get("/shortlist/default-criteria")
        assert r.status_code == 200
        d = r.json()
        assert "criteria" in d
        assert "w_novelty" in d["criteria"]

    def test_build_shortlist(self):
        client = self._client()
        r = client.post("/shortlist/build", json={})
        assert r.status_code == 200
        d = r.json()
        assert "shortlist" in d
        assert "decisions" in d
        assert "disclaimer" in d

    def test_build_shortlist_with_criteria(self):
        client = self._client()
        r = client.post("/shortlist/build", json={
            "criteria": {"top_k": 3, "max_formation_energy": 0.0}})
        assert r.status_code == 200
        assert len(r.json()["shortlist"]) <= 3

    def test_build_shortlist_with_tp(self):
        client = self._client()
        r = client.post("/shortlist/build", json={
            "temperature_K": 1000.0, "pressure_GPa": 5.0})
        assert r.status_code == 200
        assert r.json()["conditions"] is not None

    def test_build_shortlist_invalid_criteria(self):
        client = self._client()
        r = client.post("/shortlist/build", json={
            "criteria": {"w_novelty": 5.0}})
        assert r.status_code == 400

    def test_screen_tp(self):
        client = self._client()
        r = client.get("/materials?limit=1")
        cid = r.json()["data"][0]["canonical_id"]
        r2 = client.post("/screening/thermo-pressure", json={
            "material_id": cid, "temperature_K": 1500.0, "pressure_GPa": 10.0})
        assert r2.status_code == 200
        d = r2.json()
        assert "risk_level" in d
        assert "method" in d
        assert d["method"] == "heuristic_proxy"

    def test_screen_tp_not_found(self):
        client = self._client()
        r = client.post("/screening/thermo-pressure", json={
            "material_id": "nonexistent", "temperature_K": 300.0})
        assert r.status_code == 404

    def test_screen_tp_batch(self):
        client = self._client()
        r = client.get("/materials?limit=3")
        ids = [m["canonical_id"] for m in r.json()["data"]]
        r2 = client.post("/screening/thermo-pressure/batch", json={
            "material_ids": ids, "temperature_K": 1000.0, "pressure_GPa": 5.0})
        assert r2.status_code == 200
        d = r2.json()
        assert len(d["results"]) == len(ids)
        assert "disclaimer" in d

    def test_screen_tp_batch_with_missing(self):
        client = self._client()
        r = client.post("/screening/thermo-pressure/batch", json={
            "material_ids": ["nonexistent"],
            "temperature_K": 300.0})
        assert r.status_code == 200
        assert r.json()["results"][0].get("error") == "not_found"

    def test_backward_compatibility(self):
        """All existing endpoints still work."""
        client = self._client()
        assert client.get("/status").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/stats").status_code == 200
        assert client.get("/materials?limit=2").status_code == 200
        assert client.get("/search?formula=Fe2O3").status_code == 200
        assert client.get("/audit/summary").status_code == 200
        assert client.get("/candidates/exotic?top_k=2").status_code == 200

    def test_status_version(self):
        client = self._client()
        d = client.get("/status").json()
        assert d["version"] == "2.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
