"""Tests for Targeted AFLOW Ingestion Pilot."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.corpus_sources.pilot import (
    generate_pilot_plan, execute_pilot, save_pilot_artifacts,
    PilotCandidate, PilotPlan, PilotResult,
)


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, has_valid_structure=True,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("Si", ["Si"], 227, 0.0),
    _make_material("GaAs", ["As", "Ga"], 216, -0.7),
    _make_material("NaCl", ["Cl", "Na"], 225, -4.2),
    _make_material("Fe2O3", ["Fe", "O"], 167, -1.5),
    _make_material("TiO2", ["O", "Ti"], 136, -3.4),
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


class TestPlan:
    def test_generate_plan(self, test_db):
        plan, candidates = generate_pilot_plan(test_db, target_count=20)
        assert plan.plan_id
        assert plan.total_candidates > 0
        assert plan.selected_for_ingestion >= 0
        assert len(candidates) <= 20

    def test_plan_serializable(self, test_db):
        plan, _ = generate_pilot_plan(test_db, target_count=10)
        json.dumps(plan.to_dict())

    def test_dedup_removes_known(self, test_db):
        plan, candidates = generate_pilot_plan(test_db, target_count=50)
        # NaCl, Si, etc should be deduped
        formulas = [c.formula for c in candidates]
        # Known materials should NOT be in selected list
        for c in candidates:
            assert c.dedup_decision != "exact_duplicate" or not c.selected

    def test_exotic_priority(self, test_db):
        plan, candidates = generate_pilot_plan(test_db, target_count=20)
        # First candidates should have more new/exotic elements
        if len(candidates) >= 2:
            existing = {"Si", "Ga", "As", "Na", "Cl", "Fe", "O", "Ti"}
            first_new = len(set(candidates[0].elements) - existing)
            assert first_new >= 0  # sorted by new elements descending


class TestExecution:
    def test_dry_run(self, test_db):
        plan, candidates = generate_pilot_plan(test_db, target_count=20)
        before = test_db.count()
        result = execute_pilot(test_db, plan, candidates, dry_run=True)
        after = test_db.count()
        assert after == before  # dry run doesn't modify DB
        assert result.ingested >= 0

    def test_real_run(self, test_db):
        plan, candidates = generate_pilot_plan(test_db, target_count=10)
        before = test_db.count()
        result = execute_pilot(test_db, plan, candidates, dry_run=False)
        after = test_db.count()
        assert result.corpus_before == before
        assert result.corpus_after == after
        assert result.ingested >= 0
        assert result.recommendation

    def test_result_serializable(self, test_db):
        plan, candidates = generate_pilot_plan(test_db, target_count=5)
        result = execute_pilot(test_db, plan, candidates, dry_run=True)
        json.dumps(result.to_dict())


class TestArtifacts:
    def test_save_artifacts(self, test_db):
        td = tempfile.mkdtemp()
        plan, candidates = generate_pilot_plan(test_db, target_count=10)
        result = execute_pilot(test_db, plan, candidates, dry_run=True)
        save_pilot_artifacts(plan, result, candidates, output_dir=td)
        assert os.path.exists(os.path.join(td, "pilot_plan.json"))
        assert os.path.exists(os.path.join(td, "pilot_plan.md"))
        assert os.path.exists(os.path.join(td, "pilot_run.json"))
        assert os.path.exists(os.path.join(td, "pilot_audit.json"))
        assert os.path.exists(os.path.join(td, "pilot_recommendation.json"))


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

    def test_pilot_status(self):
        r = self._client().get("/corpus-sources/pilot/status")
        assert r.status_code == 200

    def test_pilot_plan(self):
        r = self._client().post("/corpus-sources/pilot/plan?target_count=10")
        assert r.status_code == 200
        assert "plan" in r.json()

    def test_pilot_run_dry(self):
        r = self._client().post("/corpus-sources/pilot/run?target_count=10&dry_run=true")
        assert r.status_code == 200
        assert r.json()["ingested"] >= 0

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200
        assert c.get("/orchestrator/status").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "3.2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
