"""Tests for Active Learning + Corpus Expansion Orchestrator."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.orchestrator.spec import (
    ErrorHotspot, CoverageSummary, RetrainingProposal, CorpusExpansionItem, SOURCES,
    PRIORITY_HIGH, PRIORITY_MEDIUM,
)
from src.orchestrator.coverage import analyze_coverage, identify_exotic_niches
from src.orchestrator.learning import detect_error_hotspots, generate_retraining_proposals, plan_corpus_expansion
from src.orchestrator.report import generate_orchestrator_report


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
    _make_material("UO2", ["O", "U"], 225, 2.0, -3.0, source_id="UO2_test"),
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


class TestCoverage:
    def test_analyze_coverage(self, test_db):
        cov = analyze_coverage(test_db)
        assert cov.total_materials == 6
        assert cov.total_elements_seen >= 6
        assert len(cov.element_counts) > 0

    def test_n_element_distribution(self, test_db):
        cov = analyze_coverage(test_db)
        assert 1 in cov.n_element_distribution  # Si has 1 element
        assert 2 in cov.n_element_distribution  # Most have 2

    def test_exotic_niches(self, test_db):
        cov = analyze_coverage(test_db)
        niches = identify_exotic_niches(cov)
        assert len(niches) > 0
        for n in niches:
            assert "niche" in n
            assert "recommendation" in n

    def test_serialization(self, test_db):
        cov = analyze_coverage(test_db)
        d = cov.to_dict()
        json.dumps(d)  # must not raise


class TestLearning:
    def test_detect_hotspots(self):
        hotspots = detect_error_hotspots()
        assert isinstance(hotspots, list)
        for h in hotspots:
            assert h.target in ("formation_energy", "band_gap")

    def test_generate_proposals(self):
        hotspots = detect_error_hotspots()
        proposals = generate_retraining_proposals(hotspots)
        assert len(proposals) > 0
        for p in proposals:
            assert p.target
            assert p.priority

    def test_plan_expansion(self):
        items = plan_corpus_expansion()
        assert len(items) >= 3  # At least COD, AFLOW, MP
        for item in items:
            assert item.source
            assert "$0" in item.cost  # "$0" or "$0 (API key)"

    def test_sources_defined(self):
        assert "jarvis" in SOURCES
        assert "materials_project" in SOURCES
        assert "cod" in SOURCES
        assert SOURCES["jarvis"]["status"] == "integrated"


class TestReport:
    def test_generate_report(self, test_db):
        td = tempfile.mkdtemp()
        report = generate_orchestrator_report(test_db, output_dir=td)
        assert "coverage" in report
        assert "error_hotspots" in report
        assert "retraining_proposals" in report
        assert "corpus_expansion_plan" in report
        assert "action_summary" in report
        assert "disclaimer" in report
        # Check files created
        assert os.path.exists(os.path.join(td, "orchestrator_report.json"))
        assert os.path.exists(os.path.join(td, "orchestrator_report.md"))
        assert os.path.exists(os.path.join(td, "coverage_summary.json"))
        assert os.path.exists(os.path.join(td, "coverage_summary.md"))
        assert os.path.exists(os.path.join(td, "retraining_proposals.json"))
        assert os.path.exists(os.path.join(td, "retraining_proposals.md"))

    def test_action_summary_structure(self, test_db):
        td = tempfile.mkdtemp()
        report = generate_orchestrator_report(test_db, output_dir=td)
        actions = report["action_summary"]
        assert "improve_now" in actions
        assert "dont_touch" in actions
        assert "data_to_seek" in actions
        assert "target_attention" in actions

    def test_json_serializable(self, test_db):
        td = tempfile.mkdtemp()
        report = generate_orchestrator_report(test_db, output_dir=td)
        json.dumps(report)  # must not raise


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

    def test_status(self):
        r = self._client().get("/orchestrator/status")
        assert r.status_code == 200
        assert "corpus_size" in r.json()
        assert "error_hotspots" in r.json()

    def test_coverage(self):
        r = self._client().get("/orchestrator/coverage")
        assert r.status_code == 200
        assert "coverage" in r.json()
        assert "exotic_niches" in r.json()

    def test_proposals(self):
        r = self._client().get("/orchestrator/retraining-proposals")
        assert r.status_code == 200
        assert "proposals" in r.json()

    def test_run(self):
        r = self._client().post("/orchestrator/run")
        assert r.status_code == 200
        assert "action_summary" in r.json()

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/frontier/presets").status_code == 200
        assert c.get("/niche/presets").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
