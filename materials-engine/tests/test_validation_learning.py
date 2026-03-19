"""Tests for validation queue, learning feedback, and API endpoints."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.validation.spec import (
    ValidationCandidate, VALIDATION_STAGES, compute_roi_score,
    PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW,
    RC_DUPLICATE, RC_HIGH_INFO,
)
from src.validation.queue import ValidationQueue
from src.learning.feedback import FeedbackEntry, FeedbackMemory
from src.learning.memory import (
    build_learning_queue, rank_learning_candidates,
    summarize_model_failures, summarize_promising_regions,
    generate_learning_summary,
)


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   source="test", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("NaCl", ["Cl", "Na"], 225, -4.2),
    _make_material("Fe2O3", ["Fe", "O"], 167, -1.5),
    _make_material("Si", ["Si"], 227, 0.0),
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


# ================================================================
# Spec tests
# ================================================================

class TestSpec:
    def test_validation_candidate_fields(self):
        vc = ValidationCandidate(formula="NaCl", elements=["Cl", "Na"],
                                 novelty_score=0.5, evaluation_score=0.6)
        d = vc.to_dict()
        assert d["formula"] == "NaCl"
        assert d["novelty_score"] == 0.5

    def test_from_dict_roundtrip(self):
        vc = ValidationCandidate(formula="Fe2O3", spacegroup=167)
        d = vc.to_dict()
        vc2 = ValidationCandidate.from_dict(d)
        assert vc2.formula == "Fe2O3"
        assert vc2.spacegroup == 167

    def test_validation_stages_exist(self):
        assert len(VALIDATION_STAGES) >= 5
        assert VALIDATION_STAGES[0]["name"] == "dedup_rejection"
        assert VALIDATION_STAGES[3]["name"] == "ready_for_dft"

    def test_roi_score_range(self):
        s = compute_roi_score(0.5, 0.5, 0.5, 0.5, 0.5)
        assert 0.0 <= s <= 1.0

    def test_roi_high_info(self):
        high = compute_roi_score(1.0, 1.0, 1.0, 1.0, 1.0)
        low = compute_roi_score(0.0, 0.0, 0.0, 0.0, 0.0)
        assert high > low

    def test_roi_duplicate_penalty(self):
        base = compute_roi_score(0.5, 0.5, 0.5, 0.5, 0.5)
        penalized = compute_roi_score(0.5, 0.5, 0.5, 0.5, 0.5,
                                      duplicate_penalty=0.9)
        assert penalized < base


# ================================================================
# Queue tests
# ================================================================

class TestQueue:
    def test_add_candidate(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        vc = ValidationCandidate(formula="KCl", elements=["Cl", "K"],
                                 novelty_score=0.5, evaluation_score=0.6)
        result = q.add(vc)
        assert result["status"] == "queued"
        assert q.size == 1

    def test_dedup(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        vc1 = ValidationCandidate(formula="KCl", elements=["Cl", "K"])
        vc2 = ValidationCandidate(formula="KCl", elements=["Cl", "K"])
        q.add(vc1)
        result = q.add(vc2)
        assert result["reason"] == RC_DUPLICATE
        assert q.size == 1  # only first one added

    def test_priority_scoring(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        vc = ValidationCandidate(formula="UPu3", elements=["Pu", "U"],
                                 novelty_score=0.8, exotic_score=0.7,
                                 evaluation_score=0.65)
        result = q.add(vc)
        assert result["priority"] in (PRIORITY_HIGH, PRIORITY_MEDIUM)

    def test_status(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        for f in ["A", "B", "C"]:
            q.add(ValidationCandidate(formula=f, elements=["Fe"]))
        s = q.status()
        assert s["total"] == 3

    def test_get_top(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        for i, f in enumerate(["A", "B", "C"]):
            q.add(ValidationCandidate(formula=f, elements=["Fe"],
                                      evaluation_score=float(i) / 10))
        top = q.get_top(n=2)
        assert len(top) == 2

    def test_get_by_id(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        vc = ValidationCandidate(formula="KBr", elements=["Br", "K"])
        result = q.add(vc)
        found = q.get(result["validation_id"])
        assert found is not None
        assert found.formula == "KBr"

    def test_save_load(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        q.add(ValidationCandidate(formula="A", elements=["Fe"]))
        q.add(ValidationCandidate(formula="B", elements=["O"]))
        q.save()

        q2 = ValidationQueue(output_dir=temp_dir)
        assert q2.load()
        assert q2.size == 2


# ================================================================
# Feedback tests
# ================================================================

class TestFeedback:
    def test_add_entry(self, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        entry = FeedbackEntry(formula="NaCl", target_property="formation_energy",
                              predicted_value=-4.0, observed_value=-4.2,
                              decision="keep")
        fid = fm.add(entry)
        assert fid
        assert fm.size == 1

    def test_auto_error(self, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        entry = FeedbackEntry(formula="NaCl", target_property="band_gap",
                              predicted_value=8.0, observed_value=8.5)
        fm.add(entry)
        assert fm._entries[0].error == 0.5

    def test_status(self, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        fm.add(FeedbackEntry(formula="A", predicted_value=1.0,
                              observed_value=1.5, decision="keep"))
        fm.add(FeedbackEntry(formula="B", predicted_value=2.0,
                              observed_value=5.0, decision="needs_retrain"))
        s = fm.status()
        assert s["total_entries"] == 2
        assert s["entries_with_error"] == 2

    def test_filter_by_decision(self, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        fm.add(FeedbackEntry(formula="A", decision="keep"))
        fm.add(FeedbackEntry(formula="B", decision="needs_retrain"))
        retrain = fm.get_entries(decision="needs_retrain")
        assert len(retrain) == 1

    def test_save_load(self, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        fm.add(FeedbackEntry(formula="X", decision="promote"))
        fm.save()
        fm2 = FeedbackMemory(output_dir=temp_dir)
        assert fm2.load()
        assert fm2.size == 1


# ================================================================
# Learning memory tests
# ================================================================

class TestLearningMemory:
    def _make_feedback(self, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        fm.add(FeedbackEntry(formula="A", elements=["Fe", "O"],
                              target_property="formation_energy",
                              predicted_value=-1.0, observed_value=-2.0,
                              decision="needs_retrain"))
        fm.add(FeedbackEntry(formula="B", elements=["Ti", "O"],
                              target_property="band_gap",
                              predicted_value=3.0, observed_value=3.2,
                              decision="keep"))
        fm.add(FeedbackEntry(formula="C", elements=["Cu", "O"],
                              target_property="formation_energy",
                              predicted_value=-0.5, observed_value=-0.3,
                              decision="promote"))
        return fm

    def test_build_learning_queue(self, temp_dir):
        fm = self._make_feedback(temp_dir)
        q = build_learning_queue(fm)
        assert len(q) > 0
        # A has needs_retrain + large error → should be first
        assert q[0]["formula"] == "A"

    def test_rank_learning_candidates(self, temp_dir):
        fm = self._make_feedback(temp_dir)
        ranked = rank_learning_candidates(fm, top_k=2)
        assert len(ranked) <= 2

    def test_summarize_failures(self, temp_dir):
        fm = self._make_feedback(temp_dir)
        s = summarize_model_failures(fm)
        assert "by_property" in s
        assert s["total_failures"] >= 1  # A has error=1.0 > 0.5

    def test_summarize_promising(self, temp_dir):
        fm = self._make_feedback(temp_dir)
        s = summarize_promising_regions(fm)
        assert "promoted_elements" in s
        assert "Cu" in s["promoted_elements"]  # C was promoted

    def test_generate_summary(self, temp_dir):
        fm = self._make_feedback(temp_dir)
        s = generate_learning_summary(fm, output_dir=temp_dir)
        assert "total_feedback" in s
        assert os.path.exists(os.path.join(temp_dir, "learning_queue.json"))
        assert os.path.exists(os.path.join(temp_dir, "learning_summary.md"))


# ================================================================
# API tests
# ================================================================

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        from src.validation.queue import ValidationQueue
        from src.learning.feedback import FeedbackMemory
        srv._validation_queue = ValidationQueue(output_dir=tempfile.mkdtemp())
        srv._feedback_memory = FeedbackMemory(output_dir=tempfile.mkdtemp())
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        for m in CORPUS:
            srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None
        srv._validation_queue = None
        srv._feedback_memory = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_presets(self):
        c = self._client()
        r = c.get("/validation/presets")
        assert r.status_code == 200
        assert "stages" in r.json()

    def test_queue_add(self):
        c = self._client()
        r = c.post("/validation/queue/add", json={
            "formula": "KCl", "elements": ["Cl", "K"],
            "novelty_score": 0.5, "evaluation_score": 0.4})
        assert r.status_code == 200
        assert r.json()["status"] == "queued"

    def test_queue_add_dedup(self):
        c = self._client()
        c.post("/validation/queue/add", json={
            "formula": "KCl", "elements": ["Cl", "K"]})
        r2 = c.post("/validation/queue/add", json={
            "formula": "KCl", "elements": ["Cl", "K"]})
        assert r2.json()["reason"] == RC_DUPLICATE

    def test_queue_status(self):
        c = self._client()
        c.post("/validation/queue/add", json={
            "formula": "A", "elements": ["Fe"]})
        r = c.get("/validation/queue/status")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_queue_get(self):
        c = self._client()
        r = c.post("/validation/queue/add", json={
            "formula": "X", "elements": ["Fe"]})
        vid = r.json()["validation_id"]
        r2 = c.get(f"/validation/queue/{vid}")
        assert r2.status_code == 200
        assert r2.json()["formula"] == "X"

    def test_queue_get_not_found(self):
        c = self._client()
        r = c.get("/validation/queue/nonexistent")
        assert r.status_code == 404

    def test_feedback_add(self):
        c = self._client()
        r = c.post("/validation/feedback/add", json={
            "formula": "NaCl", "target_property": "formation_energy",
            "predicted_value": -4.0, "observed_value": -4.2,
            "decision": "keep"})
        assert r.status_code == 200
        assert "feedback_id" in r.json()

    def test_learning_status(self):
        c = self._client()
        r = c.get("/learning/status")
        assert r.status_code == 200
        assert "total_entries" in r.json()

    def test_learning_queue(self):
        c = self._client()
        r = c.get("/learning/queue")
        assert r.status_code == 200
        assert "queue" in r.json()

    def test_learning_summary(self):
        c = self._client()
        r = c.get("/learning/summary")
        assert r.status_code == 200
        assert "total_feedback" in r.json()

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/materials?limit=1").status_code == 200
        assert c.get("/generation/presets").status_code == 200
        assert c.get("/campaigns/presets").status_code == 200
        assert c.get("/intelligence/status").status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "1.2.1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
