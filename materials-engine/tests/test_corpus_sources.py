"""Tests for Multi-Source Corpus Expansion + Dedup Foundation."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.corpus_sources.spec import (
    SourceRegistryEntry, NormalizedCandidate, DedupDecision, StagingReport,
    SOURCE_REGISTRY, DEDUP_EXACT, DEDUP_UNIQUE, DEDUP_SAME_FORMULA_DIFF_STRUCT,
)
from src.corpus_sources.dedup import check_dedup, batch_dedup
from src.corpus_sources.staging import stage_source, simulate_mp_staging, generate_expansion_recommendation, save_staging


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


class TestRegistry:
    def test_registry_has_entries(self):
        assert len(SOURCE_REGISTRY) >= 5

    def test_jarvis_active(self):
        jarvis = [s for s in SOURCE_REGISTRY if s.name == "jarvis"][0]
        assert jarvis.status == "active"

    def test_all_have_cost(self):
        for s in SOURCE_REGISTRY:
            assert "$0" in s.cost

    def test_serialization(self):
        for s in SOURCE_REGISTRY:
            d = s.to_dict()
            json.dumps(d)


class TestDedup:
    def test_exact_match(self, test_db):
        c = NormalizedCandidate(formula="Si", spacegroup=227, source_name="mp")
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_EXACT

    def test_same_formula_diff_sg(self, test_db):
        c = NormalizedCandidate(formula="Si", spacegroup=12, source_name="mp")
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_SAME_FORMULA_DIFF_STRUCT

    def test_unique(self, test_db):
        c = NormalizedCandidate(formula="UPu3", spacegroup=12, source_name="mp")
        d = check_dedup(c, test_db)
        # Has spacegroup (structure) but no props → unique_structure_only
        assert d.decision in (DEDUP_UNIQUE, "unique_structure_only")

    def test_batch_dedup(self, test_db):
        candidates = [
            NormalizedCandidate(formula="Si", spacegroup=227, source_name="mp"),
            NormalizedCandidate(formula="UPu3", spacegroup=12, source_name="mp"),
            NormalizedCandidate(formula="NaCl", spacegroup=225, source_name="mp"),
        ]
        result = batch_dedup(candidates, test_db)
        assert result["summary"]["exact"] == 2  # Si and NaCl
        # UPu3 has spacegroup → unique_structure_only
        unique_total = (result["summary"]["unique"] +
                        result["summary"].get("unique_structure_only", 0) +
                        result["summary"].get("unique_training_candidate", 0))
        assert unique_total == 1  # UPu3


class TestStaging:
    def test_stage_source(self, test_db):
        candidates = [
            NormalizedCandidate(formula="Si", spacegroup=227, elements=["Si"], source_name="test"),
            NormalizedCandidate(formula="XYZ", spacegroup=1, elements=["X", "Y", "Z"], source_name="test"),
        ]
        report = stage_source("test_source", candidates, test_db)
        assert report.total_candidates == 2
        assert report.exact_duplicates >= 1
        assert report.unique_new >= 0

    def test_simulate_mp(self, test_db):
        report = simulate_mp_staging(test_db, sample_size=50)
        assert report.source == "materials_project"
        assert report.total_candidates == 50
        assert report.normalized_ok > 0
        assert report.recommendation

    def test_expansion_recommendation(self, test_db):
        report = simulate_mp_staging(test_db, sample_size=50)
        rec = generate_expansion_recommendation([report])
        assert "ranked_sources" in rec
        assert len(rec["ranked_sources"]) >= 1
        assert "action" in rec["ranked_sources"][0]

    def test_save_staging(self, test_db):
        report = simulate_mp_staging(test_db, sample_size=20)
        td = tempfile.mkdtemp()
        path = save_staging(report, output_dir=td)
        assert os.path.exists(path)
        md_path = path.replace(".json", ".md")
        assert os.path.exists(md_path)

    def test_report_json_serializable(self, test_db):
        report = simulate_mp_staging(test_db, sample_size=20)
        json.dumps(report.to_dict())


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

    def test_registry(self):
        r = self._client().get("/corpus-sources/registry")
        assert r.status_code == 200
        assert len(r.json()["sources"]) >= 5

    def test_status(self):
        r = self._client().get("/corpus-sources/status")
        assert r.status_code == 200
        assert r.json()["active_sources"] >= 1

    def test_stage(self):
        r = self._client().post("/corpus-sources/stage?source=materials_project")
        assert r.status_code == 200
        assert "total_candidates" in r.json()

    def test_recommendation(self):
        r = self._client().get("/corpus-sources/recommendation")
        assert r.status_code == 200
        assert "ranked_sources" in r.json()

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/frontier/presets").status_code == 200
        assert c.get("/orchestrator/status").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "3.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
