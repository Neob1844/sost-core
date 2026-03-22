"""Tests for evidence bridge, benchmark suite, confidence calibration, and API."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.evidence.spec import (
    EvidenceRecord, EvidenceRegistry, EvidenceValidationError,
    SOURCE_TYPES, EVIDENCE_LEVELS,
)
from src.benchmark.runner import run_benchmark, save_benchmark, list_benchmarks
from src.calibration.confidence import (
    calibrate_from_benchmark, get_calibrated_confidence,
    save_calibration, load_calibration,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_UNKNOWN,
)

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
    _make_material("Si", ["Si"], 227, 1.1, 0.0),
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5),
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
# Evidence tests
# ================================================================

class TestEvidence:
    def test_create_record(self):
        r = EvidenceRecord(formula="NaCl", property_name="band_gap",
                           observed_value=8.5, evidence_level="known_external")
        r.validate()
        assert r.formula == "NaCl"

    def test_validate_missing_formula(self):
        r = EvidenceRecord(property_name="band_gap")
        with pytest.raises(EvidenceValidationError, match="formula"):
            r.validate()

    def test_validate_bad_source_type(self):
        r = EvidenceRecord(formula="X", property_name="bg", source_type="magic")
        with pytest.raises(EvidenceValidationError):
            r.validate()

    def test_registry_add(self, temp_dir):
        reg = EvidenceRegistry(output_dir=temp_dir)
        r = EvidenceRecord(formula="NaCl", property_name="band_gap",
                           observed_value=8.5)
        eid = reg.add(r)
        assert eid
        assert reg.size == 1

    def test_registry_find(self, temp_dir):
        reg = EvidenceRegistry(output_dir=temp_dir)
        reg.add(EvidenceRecord(formula="NaCl", property_name="band_gap",
                               observed_value=8.5))
        reg.add(EvidenceRecord(formula="Si", property_name="band_gap",
                               observed_value=1.17))
        found = reg.find_by_formula("NaCl")
        assert len(found) == 1

    def test_import_json(self, temp_dir):
        reg = EvidenceRegistry(output_dir=temp_dir)
        data = [
            {"formula": "NaCl", "property_name": "band_gap", "observed_value": 8.5},
            {"formula": "Si", "property_name": "band_gap", "observed_value": 1.17},
        ]
        result = reg.import_json(data)
        assert result["added"] == 2
        assert result["errors"] == 0

    def test_import_csv_rows(self, temp_dir):
        reg = EvidenceRegistry(output_dir=temp_dir)
        rows = [
            {"formula": "NaCl", "property_name": "band_gap", "observed_value": 8.5},
            {"formula": "Fe2O3", "property_name": "formation_energy", "observed_value": -1.5},
        ]
        result = reg.import_csv_rows(rows)
        assert result["added"] == 2

    def test_save_load(self, temp_dir):
        reg = EvidenceRegistry(output_dir=temp_dir)
        reg.add(EvidenceRecord(formula="X", property_name="bg"))
        reg.save()
        reg2 = EvidenceRegistry(output_dir=temp_dir)
        assert reg2.load()
        assert reg2.size == 1

    def test_status(self, temp_dir):
        reg = EvidenceRegistry(output_dir=temp_dir)
        reg.add(EvidenceRecord(formula="A", property_name="bg",
                               source_type="manual_entry"))
        reg.add(EvidenceRecord(formula="B", property_name="fe",
                               source_type="json_import"))
        s = reg.status()
        assert s["total"] == 2
        assert "manual_entry" in s["by_source_type"]

    def test_to_dict_roundtrip(self):
        r = EvidenceRecord(formula="NaCl", property_name="band_gap",
                           observed_value=8.5, evidence_level="known_external")
        d = r.to_dict()
        r2 = EvidenceRecord.from_dict(d)
        assert r2.formula == "NaCl"
        assert r2.observed_value == 8.5


# ================================================================
# Benchmark tests
# ================================================================

class TestBenchmark:
    def test_run_benchmark(self, test_db):
        report = run_benchmark(test_db, target_property="formation_energy",
                               sample_size=10, seed=42)
        assert "benchmark_id" in report
        assert "overall" in report
        assert report["sample_size"] >= 0  # may be 0 if no structures

    def test_benchmark_has_buckets(self, test_db):
        report = run_benchmark(test_db, target_property="formation_energy",
                               sample_size=10, seed=42)
        assert "by_element_count" in report
        assert "by_value_range" in report

    def test_save_and_list(self, test_db, temp_dir):
        report = run_benchmark(test_db, sample_size=5, seed=42)
        path = save_benchmark(report, output_dir=temp_dir)
        assert os.path.exists(path)
        listed = list_benchmarks(output_dir=temp_dir)
        assert len(listed) >= 1

    def test_reproducible(self, test_db):
        r1 = run_benchmark(test_db, sample_size=5, seed=42)
        r2 = run_benchmark(test_db, sample_size=5, seed=42)
        assert r1["overall"]["mae"] == r2["overall"]["mae"]


# ================================================================
# Calibration tests
# ================================================================

class TestCalibration:
    def _make_benchmark(self):
        return {
            "benchmark_id": "test_fe_42",
            "target_property": "formation_energy",
            "sample_size": 100,
            "overall": {"mae": 0.25, "rmse": 0.35, "median_error": 0.2,
                        "p90_error": 0.5, "p95_error": 0.7, "max_error": 1.2},
            "by_element_count": {
                "1-1": {"count": 10, "mae": 0.15, "median": 0.1, "p90": 0.3},
                "2-2": {"count": 40, "mae": 0.22, "median": 0.18, "p90": 0.4},
                "3-3": {"count": 30, "mae": 0.35, "median": 0.3, "p90": 0.6},
            },
            "by_value_range": {
                "-3.0--1.0": {"count": 50, "mae": 0.2, "median": 0.15, "p90": 0.4},
                "-1.0-0.0": {"count": 30, "mae": 0.4, "median": 0.35, "p90": 0.7},
            },
        }

    def test_calibrate(self):
        cal = calibrate_from_benchmark(self._make_benchmark())
        assert cal["target_property"] == "formation_energy"
        assert cal["overall_mae"] == 0.25
        assert cal["overall_confidence_band"] == CONFIDENCE_HIGH

    def test_confidence_by_bucket(self):
        cal = calibrate_from_benchmark(self._make_benchmark())
        result = get_calibrated_confidence(cal, n_elements=1)
        assert result["confidence_band"] == CONFIDENCE_HIGH

    def test_confidence_low_bucket(self):
        cal = calibrate_from_benchmark(self._make_benchmark())
        # 3-element bucket has MAE=0.35 → medium for formation_energy
        result = get_calibrated_confidence(cal, n_elements=3)
        assert result["confidence_band"] == CONFIDENCE_MEDIUM

    def test_confidence_no_calibration(self):
        result = get_calibrated_confidence(None)
        assert result["confidence_band"] == CONFIDENCE_UNKNOWN

    def test_save_load(self, temp_dir):
        cal = calibrate_from_benchmark(self._make_benchmark())
        save_calibration(cal, output_dir=temp_dir)
        loaded = load_calibration("formation_energy", output_dir=temp_dir)
        assert loaded is not None
        assert loaded["overall_mae"] == 0.25

    def test_note_present(self):
        cal = calibrate_from_benchmark(self._make_benchmark())
        assert "NOT statistical probability" in cal["note"]


# ================================================================
# API tests
# ================================================================

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        srv._evidence_registry = None
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        for m in CORPUS:
            srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None
        srv._evidence_registry = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_evidence_import_json(self):
        c = self._client()
        r = c.post("/evidence/import/json", json={"records": [
            {"formula": "NaCl", "property_name": "band_gap", "observed_value": 8.5}
        ]})
        assert r.status_code == 200
        assert r.json()["added"] == 1

    def test_evidence_status(self):
        c = self._client()
        r = c.get("/evidence/status")
        assert r.status_code == 200
        assert "total" in r.json()

    def test_benchmark_presets(self):
        c = self._client()
        r = c.get("/benchmark/presets")
        assert r.status_code == 200
        assert "targets" in r.json()

    def test_benchmark_run(self):
        c = self._client()
        r = c.post("/benchmark/run", json={
            "target_property": "formation_energy", "sample_size": 5})
        assert r.status_code == 200
        assert "overall" in r.json()

    def test_benchmark_status(self):
        c = self._client()
        r = c.get("/benchmark/status")
        assert r.status_code == 200

    def test_calibration_status(self):
        c = self._client()
        r = c.get("/calibration/status")
        assert r.status_code == 200

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/materials?limit=1").status_code == 200
        assert c.get("/generation/presets").status_code == 200
        assert c.get("/validation/presets").status_code == 200
        assert c.get("/learning/status").status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert "3.2.0" in d["version"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
