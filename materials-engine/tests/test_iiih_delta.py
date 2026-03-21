"""Tests for Phase III.H Delta — calibrated integration, evidence linking, API."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.features.fingerprint_store import FingerprintStore
from src.evidence.spec import EvidenceRecord, EvidenceRegistry
from src.evidence.linker import link_evidence_to_feedback, batch_link
from src.learning.feedback import FeedbackMemory
from src.calibration.confidence import (
    calibrate_from_benchmark, save_calibration, CONFIDENCE_HIGH, CONFIDENCE_UNKNOWN,
)
from src.intelligence.dossier import build_dossier
from src.validation.spec import ValidationCandidate
from src.validation.queue import ValidationQueue

NACL_CIF = """data_NaCl
_cell_length_a 5.64
_cell_length_b 5.64
_cell_length_c 5.64
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'F m -3 m'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na Na 0.0 0.0 0.0
Cl Cl 0.5 0.5 0.5
"""


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
    _make_material("NaCl", ["Cl", "Na"], 225, 8.5, -4.2, structure_data=NACL_CIF),
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5),
    _make_material("Si", ["Si"], 227, 1.1, 0.0),
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
def fp_store(test_db):
    d = tempfile.mkdtemp()
    store = FingerprintStore(store_dir=d)
    store.build(test_db)
    yield store
    shutil.rmtree(d)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def cal_dir(temp_dir):
    """Create calibration files for tests."""
    bench = {
        "benchmark_id": "test_fe_42",
        "target_property": "formation_energy",
        "sample_size": 50,
        "overall": {"mae": 0.25, "rmse": 0.35, "median_error": 0.2,
                    "p90_error": 0.5, "p95_error": 0.7, "max_error": 1.2},
        "by_element_count": {
            "2-2": {"count": 30, "mae": 0.2, "median": 0.15, "p90": 0.4},
        },
        "by_value_range": {},
    }
    cal = calibrate_from_benchmark(bench)
    save_calibration(cal, output_dir=temp_dir)
    return temp_dir


# ================================================================
# Dossier calibrated tests
# ================================================================

class TestDossierCalibrated:
    def test_dossier_has_calibration_field(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], spacegroup=225,
                          db=test_db, store=fp_store)
        assert "calibration" in d
        assert "confidence_source" in d["calibration"]

    def test_dossier_calibration_source(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        cs = d["calibration"]["confidence_source"]
        # May be benchmark_calibrated (if calibration files exist) or heuristic/no_cal
        assert cs in ("benchmark_calibrated", "heuristic_fallback",
                      "no_calibration_available")

    def test_dossier_still_has_all_fields(self, test_db, fp_store):
        """Verify calibration didn't break existing fields."""
        d = build_dossier("NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        assert "existence_status" in d
        assert "validation_priority" in d
        assert "evidence_summary" in d
        assert "limitations" in d
        assert "method_notes" in d


# ================================================================
# Validation queue calibration tests
# ================================================================

class TestQueueCalibrated:
    def test_candidate_has_calibration_fields(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        vc = ValidationCandidate(formula="KCl", elements=["Cl", "K"],
                                 novelty_score=0.5, evaluation_score=0.6)
        q.add(vc)
        c = q.get_top(1)[0]
        assert "benchmark_confidence_band" in c
        assert "expected_error_band" in c
        assert "evidence_count" in c

    def test_calibration_fields_persist(self, temp_dir):
        q = ValidationQueue(output_dir=temp_dir)
        vc = ValidationCandidate(formula="A", elements=["Fe"],
                                 benchmark_confidence_band="high",
                                 expected_error_band=0.25)
        q.add(vc)
        q.save()
        q2 = ValidationQueue(output_dir=temp_dir)
        q2.load()
        c = q2.get_top(1)[0]
        assert c["benchmark_confidence_band"] == "high"


# ================================================================
# Evidence ↔ Feedback linker tests
# ================================================================

class TestEvidenceLinker:
    def test_link_good_match(self, test_db, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        ev = EvidenceRecord(formula="NaCl", property_name="formation_energy",
                            observed_value=-4.3, evidence_level="known_external")
        result = link_evidence_to_feedback(ev, test_db, fm)
        assert result["linked"]
        assert result["decision"] in ("keep", "downgrade_confidence")
        assert fm.size == 1

    def test_link_large_error(self, test_db, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        ev = EvidenceRecord(formula="NaCl", property_name="formation_energy",
                            observed_value=5.0)  # Very different from -4.2
        result = link_evidence_to_feedback(ev, test_db, fm)
        assert result["linked"]
        assert result["decision"] == "needs_retrain"

    def test_no_link_without_observed(self, test_db, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        ev = EvidenceRecord(formula="NaCl", property_name="band_gap")
        result = link_evidence_to_feedback(ev, test_db, fm)
        assert not result["linked"]
        assert result["reason"] == "no_observed_value"

    def test_no_link_unknown_formula(self, test_db, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        ev = EvidenceRecord(formula="UnknownXYZ", property_name="band_gap",
                            observed_value=5.0)
        result = link_evidence_to_feedback(ev, test_db, fm)
        assert not result["linked"]
        assert result["reason"] == "no_corpus_match"

    def test_no_link_missing_property(self, test_db, temp_dir):
        fm = FeedbackMemory(output_dir=temp_dir)
        ev = EvidenceRecord(formula="NaCl", property_name="bulk_modulus",
                            observed_value=24.0)
        result = link_evidence_to_feedback(ev, test_db, fm)
        assert not result["linked"]
        assert result["reason"] == "no_predicted_value_for_property"

    def test_batch_link(self, test_db, temp_dir):
        reg = EvidenceRegistry(output_dir=temp_dir)
        reg.add(EvidenceRecord(formula="NaCl", property_name="formation_energy",
                               observed_value=-4.1))
        reg.add(EvidenceRecord(formula="Si", property_name="band_gap",
                               observed_value=1.17))
        reg.add(EvidenceRecord(formula="NoMatch", property_name="band_gap",
                               observed_value=5.0))
        fm = FeedbackMemory(output_dir=temp_dir)
        result = batch_link(reg, test_db, fm)
        assert result["linked"] == 2
        assert result["unlinked"] == 1
        assert fm.size == 2


# ================================================================
# API tests
# ================================================================

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        from src.validation.queue import ValidationQueue
        from src.learning.feedback import FeedbackMemory
        from src.evidence.spec import EvidenceRegistry
        srv._validation_queue = ValidationQueue(output_dir=tempfile.mkdtemp())
        srv._feedback_memory = FeedbackMemory(output_dir=tempfile.mkdtemp())
        srv._evidence_registry = EvidenceRegistry(output_dir=tempfile.mkdtemp())
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
        srv._evidence_registry = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_calibrated_queue(self):
        c = self._client()
        # Add something to queue first
        c.post("/validation/queue/add", json={
            "formula": "KCl", "elements": ["Cl", "K"],
            "novelty_score": 0.5})
        r = c.get("/validation/queue/calibrated")
        assert r.status_code == 200
        d = r.json()
        assert "calibrated_queue" in d
        assert "calibration_available" in d

    def test_intelligence_calibrated(self):
        c = self._client()
        r = c.get("/materials?limit=1")
        cid = r.json()["data"][0]["canonical_id"]
        r2 = c.get(f"/intelligence/material/{cid}/calibrated")
        assert r2.status_code == 200
        d = r2.json()
        assert "calibration" in d

    def test_intelligence_calibrated_not_found(self):
        c = self._client()
        r = c.get("/intelligence/material/nonexistent/calibrated")
        assert r.status_code == 404

    def test_report_calibrated(self):
        c = self._client()
        r = c.post("/intelligence/report/calibrated", json={
            "formula": "NaCl", "elements": ["Cl", "Na"]})
        assert r.status_code == 200
        assert "calibration" in r.json()

    def test_evidence_feedback_links(self):
        c = self._client()
        # Import some evidence
        c.post("/evidence/import/json", json={"records": [
            {"formula": "NaCl", "property_name": "formation_energy",
             "observed_value": -4.1}
        ]})
        r = c.get("/evidence/feedback-links")
        assert r.status_code == 200
        assert "linked" in r.json()

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/materials?limit=1").status_code == 200
        assert c.get("/generation/presets").status_code == 200
        assert c.get("/validation/presets").status_code == 200
        assert c.get("/evidence/status").status_code == 200
        assert c.get("/benchmark/presets").status_code == 200
        assert c.get("/calibration/status").status_code == 200
        assert c.get("/learning/status").status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "2.6.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
