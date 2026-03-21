"""Tests for the Dual-Target Frontier Engine."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.frontier.spec import (
    FrontierProfile, FrontierCandidate, ALL_FRONTIER_PRESETS,
    balanced_frontier, stable_semiconductor, wide_gap_exotic, high_novelty_watchlist,
)
from src.frontier.scoring import (
    stability_score, band_gap_fit_score, structure_quality_score,
    compute_frontier_score, assign_reason_codes,
)
from src.frontier.engine import FrontierEngine


def _make_material(formula, elements, spacegroup=None, band_gap=None,
                   formation_energy=None, structure_data=None,
                   source="test", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 band_gap=band_gap, formation_energy=formation_energy,
                 structure_data=structure_data,
                 has_valid_structure=structure_data is not None,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("Si", ["Si"], 227, 1.1, 0.0),
    _make_material("GaAs", ["As", "Ga"], 216, 1.4, -0.7),
    _make_material("NaCl", ["Cl", "Na"], 225, 8.5, -4.2),
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5),
    _make_material("TiO2", ["O", "Ti"], 136, 3.2, -3.4),
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


class TestProfiles:
    def test_all_presets_valid(self):
        for name, fn in ALL_FRONTIER_PRESETS.items():
            p = fn()
            p.validate()

    def test_weights_sum_to_one(self):
        for fn in ALL_FRONTIER_PRESETS.values():
            p = fn()
            s = p.w_stability + p.w_band_gap_fit + p.w_novelty + p.w_exotic + p.w_structure_quality + p.w_validation_priority
            assert abs(s - 1.0) < 0.02

    def test_stable_semiconductor_has_bg_target(self):
        p = stable_semiconductor()
        assert p.band_gap_target == 1.5

    def test_serialization_roundtrip(self):
        p = balanced_frontier()
        d = p.to_dict()
        p2 = FrontierProfile.from_dict(d)
        assert p2.name == p.name
        assert p2.w_stability == p.w_stability


class TestScoring:
    def test_stability_negative_fe(self):
        assert stability_score(-3.0) > 0.8

    def test_stability_positive_fe(self):
        assert stability_score(1.5) < 0.2

    def test_stability_none(self):
        assert stability_score(None) == 0.2

    def test_bg_fit_exact(self):
        assert band_gap_fit_score(1.5, 1.5) == 1.0

    def test_bg_fit_no_target(self):
        assert band_gap_fit_score(1.5, None) == 0.5

    def test_bg_fit_none(self):
        assert band_gap_fit_score(None, 1.5) == 0.2

    def test_structure_quality_with_struct(self):
        assert structure_quality_score(True, 5.0) == 1.0

    def test_structure_quality_none(self):
        assert structure_quality_score(False) == 0.0

    def test_reason_codes(self):
        c = FrontierCandidate(stability_score=0.9, band_gap_fit_score=0.8,
                              novelty_score=0.5, exotic_score=0.3)
        codes = assign_reason_codes(c)
        assert "strong_stability_signal" in codes
        assert "good_band_gap_window_fit" in codes
        assert "high_novelty" in codes


class TestEngine:
    def test_run_corpus(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        result = engine.run()
        assert "shortlist" in result
        assert result["summary"]["pool_size"] == 5
        assert result["summary"]["shortlist_size"] > 0

    def test_run_with_profile(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        result = engine.run(profile=stable_semiconductor())
        # Should filter by fe_max=0.0 — only Si (fe=0.0) and materials with fe<0
        for c in result["shortlist"]:
            fe = c["properties"]["formation_energy"]["value"]
            if fe is not None:
                assert fe <= 0.0

    def test_ranking_sorted(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        result = engine.run()
        scores = [c["scores"]["frontier"] for c in result["shortlist"]]
        assert scores == sorted(scores, reverse=True)

    def test_reason_codes_present(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        result = engine.run()
        for c in result["shortlist"]:
            assert isinstance(c["reason_codes"], list)

    def test_evidence_propagation(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        result = engine.run()
        for c in result["shortlist"]:
            assert "evidence" in c["properties"]["formation_energy"]
            assert "evidence" in c["properties"]["band_gap"]

    def test_run_and_save(self, test_db):
        td = tempfile.mkdtemp()
        engine = FrontierEngine(test_db, output_dir=td)
        result, path = engine.run_and_save()
        assert os.path.exists(path)
        loaded = engine.get_run(result["run_id"])
        assert loaded is not None
        shutil.rmtree(td)

    def test_generated_mode(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        gen = [{"candidate_id": "gen1", "formula": "XY", "elements": ["Fe", "O"],
                "predictions": {"formation_energy": -1.0, "band_gap": 1.5}}]
        result = engine.run(source="generated", generated_candidates=gen)
        assert result["summary"]["pool_size"] >= 1

    def test_mixed_mode(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        gen = [{"candidate_id": "gen2", "formula": "AB", "elements": ["Ti", "O"],
                "predictions": {"formation_energy": -2.0, "band_gap": 2.0}}]
        result = engine.run(source="mixed", generated_candidates=gen)
        assert result["summary"]["pool_size"] >= 6  # 5 corpus + 1 generated

    def test_reproducible(self, test_db):
        td = tempfile.mkdtemp()
        e1 = FrontierEngine(test_db, output_dir=td)
        e2 = FrontierEngine(test_db, output_dir=td)
        r1 = e1.run()
        r2 = e2.run()
        s1 = [c["scores"]["frontier"] for c in r1["shortlist"]]
        s2 = [c["scores"]["frontier"] for c in r2["shortlist"]]
        assert s1 == s2
        shutil.rmtree(td)

    def test_disclaimer_present(self, test_db):
        engine = FrontierEngine(test_db, output_dir=tempfile.mkdtemp())
        result = engine.run()
        assert "disclaimer" in result
        assert "NOT DFT" in result["disclaimer"]


class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
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

    def test_presets(self):
        r = self._client().get("/frontier/presets")
        assert r.status_code == 200
        assert "balanced_frontier" in r.json()["presets"]

    def test_run(self):
        r = self._client().post("/frontier/run", json={"top_k": 3})
        assert r.status_code == 200
        assert "shortlist" in r.json()

    def test_run_with_profile(self):
        r = self._client().post("/frontier/run", json={
            "profile": "stable_semiconductor", "top_k": 5})
        assert r.status_code == 200

    def test_status(self):
        r = self._client().get("/frontier/status")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/generation/presets").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.8.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
