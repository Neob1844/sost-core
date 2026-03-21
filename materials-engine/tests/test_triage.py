"""Tests for Pre-DFT Triage Gate."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.triage.spec import (
    TriageProfile, TriageResult, ALL_TRIAGE_PRESETS,
    strict_budget_gate, balanced_review_gate, exotic_patience_gate,
    DECISION_APPROVED, DECISION_MANUAL, DECISION_WATCHLIST, DECISION_REJECT,
    ACTION_PROMOTE, ACTION_REVIEW, ACTION_DROP,
)
from src.triage.engine import TriageEngine
from src.validation_pack.spec import ValidationPack, RISK_KNOWN, RISK_GEN_UNVAL, RISK_WEAK_STRUCT
from src.frontier.engine import FrontierEngine
from src.frontier.spec import balanced_frontier
from src.validation_pack.builder import ValidationPackBuilder


def _make_material(formula, elements, spacegroup=None, band_gap=None,
                   formation_energy=None, source="test", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 band_gap=band_gap, formation_energy=formation_energy,
                 has_valid_structure=True, source=source,
                 source_id=source_id or formula, confidence=0.8)
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


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


class TestProfiles:
    def test_all_presets_valid(self):
        for fn in ALL_TRIAGE_PRESETS.values():
            p = fn()
            p.validate()

    def test_weights_sum(self):
        for fn in ALL_TRIAGE_PRESETS.values():
            p = fn()
            s = p.w_frontier + p.w_calibration + p.w_evidence + p.w_novelty + p.w_structure + p.w_risk_penalty
            assert abs(s - 1.0) < 0.02

    def test_serialization(self):
        p = strict_budget_gate()
        d = p.to_dict()
        p2 = TriageProfile.from_dict(d)
        assert p2.name == p.name


class TestEngine:
    def _get_packs(self, db, temp_dir, n=5):
        fe = FrontierEngine(db, output_dir=temp_dir)
        result = fe.run(profile=balanced_frontier())
        builder = ValidationPackBuilder(db, output_dir=temp_dir)
        return builder.build_from_frontier(result, top_k=n)

    def test_run_balanced(self, test_db, temp_dir):
        packs = self._get_packs(test_db, temp_dir)
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run(packs, balanced_review_gate())
        assert result["summary"]["total"] == len(packs)
        assert "decisions" in result["summary"]

    def test_run_strict(self, test_db, temp_dir):
        packs = self._get_packs(test_db, temp_dir)
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run(packs, strict_budget_gate())
        # Strict gate should reject more
        assert result["summary"]["total"] == len(packs)

    def test_decisions_assigned(self, test_db, temp_dir):
        packs = self._get_packs(test_db, temp_dir)
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run(packs)
        valid = {DECISION_APPROVED, DECISION_MANUAL, DECISION_WATCHLIST, DECISION_REJECT}
        for r in result["results"]:
            assert r["decision"] in valid

    def test_reason_codes(self, test_db, temp_dir):
        packs = self._get_packs(test_db, temp_dir)
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run(packs)
        for r in result["results"]:
            assert len(r["reason_codes"]) > 0

    def test_known_material_penalty(self, test_db, temp_dir):
        pack = ValidationPack(formula="Si", source_type="known_corpus_candidate",
                              frontier_score=0.5, novelty_score=0.01,
                              risk_flags=[RISK_KNOWN],
                              properties={"formation_energy": {"value": 0, "evidence": "known"}})
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run([pack])
        assert result["results"][0]["decision"] == DECISION_REJECT

    def test_generated_needs_review(self, test_db, temp_dir):
        pack = ValidationPack(formula="XY", source_type="generated_hypothesis",
                              frontier_score=0.4, novelty_score=0.5,
                              has_structure=True,
                              risk_flags=[RISK_GEN_UNVAL],
                              properties={"formation_energy": {"value": -1.0, "evidence": "predicted"},
                                          "band_gap": {"value": 1.5, "evidence": "predicted"}})
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run([pack])
        assert result["results"][0]["decision"] in (DECISION_MANUAL, DECISION_APPROVED)

    def test_save_and_load(self, test_db, temp_dir):
        packs = self._get_packs(test_db, temp_dir, 3)
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result, path = engine.run_and_save(packs)
        assert os.path.exists(path)
        loaded = engine.get_run(result["run_id"])
        assert loaded is not None

    def test_sorted_by_triage_score(self, test_db, temp_dir):
        packs = self._get_packs(test_db, temp_dir)
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run(packs)
        scores = [r["triage_score"] for r in result["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_disclaimer(self, test_db, temp_dir):
        packs = self._get_packs(test_db, temp_dir, 1)
        engine = TriageEngine(test_db, output_dir=temp_dir)
        result = engine.run(packs)
        assert "NOT DFT" in result["disclaimer"]

    def test_markdown_export(self, test_db, temp_dir):
        tr = TriageResult(formula="Si", decision=DECISION_APPROVED,
                          frontier_score=0.5, triage_score=0.6,
                          next_action=ACTION_PROMOTE)
        md = tr.to_markdown()
        assert "Si" in md
        assert "approved" in md.lower()


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
        r = self._client().get("/triage/presets")
        assert r.status_code == 200
        assert "strict_budget_gate" in r.json()["presets"]

    def test_status(self):
        r = self._client().get("/triage/status")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/frontier/presets").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.8.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
