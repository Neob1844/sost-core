"""Tests for the Material Intelligence Layer."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.features.fingerprint_store import FingerprintStore
from src.intelligence.evidence import (
    KNOWN, PREDICTED, PROXY, UNAVAILABLE,
    EXACT_KNOWN_MATCH, NEAR_KNOWN_MATCH, NOT_FOUND_IN_CORPUS,
    EXISTENCE_DISCLAIMER, property_entry, evidence_summary,
)
from src.intelligence.applications import classify_applications
from src.intelligence.comparison import build_comparison_table
from src.intelligence.report import generate_report


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
                   bulk_modulus=None, total_magnetization=None,
                   source="test", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 band_gap=band_gap, formation_energy=formation_energy,
                 structure_data=structure_data, bulk_modulus=bulk_modulus,
                 total_magnetization=total_magnetization,
                 has_valid_structure=structure_data is not None,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("NaCl", ["Cl", "Na"], 225, 8.5, -4.2, structure_data=NACL_CIF),
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5, total_magnetization=3.5),
    _make_material("Si", ["Si"], 227, 1.1, 0.0, bulk_modulus=97.0),
    _make_material("GaAs", ["As", "Ga"], 216, 1.4, -0.7),
    _make_material("TiO2", ["O", "Ti"], 136, 3.2, -3.4),
    _make_material("ZnO", ["O", "Zn"], 186, 3.3, -3.5),
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


# ================================================================
# Evidence tests
# ================================================================

class TestEvidence:
    def test_property_entry(self):
        e = property_entry(2.1, KNOWN, "eV")
        assert e["value"] == 2.1
        assert e["evidence"] == KNOWN

    def test_evidence_summary(self):
        s = evidence_summary(["bg", "fe"], ["bg2"], ["density"], ["phonon"])
        assert s["known_count"] == 2
        assert s["predicted_count"] == 1
        assert s["unavailable_count"] == 1


# ================================================================
# Application tests
# ================================================================

class TestApplications:
    def test_semiconductor(self):
        apps = classify_applications(band_gap=1.5, band_gap_evidence=KNOWN)
        labels = [a["label"] for a in apps]
        assert "semiconductor" in labels

    def test_photovoltaic(self):
        apps = classify_applications(band_gap=1.3, band_gap_evidence=KNOWN)
        labels = [a["label"] for a in apps]
        assert "photovoltaic_candidate" in labels

    def test_wide_gap_insulator(self):
        apps = classify_applications(band_gap=8.5, band_gap_evidence=KNOWN)
        labels = [a["label"] for a in apps]
        assert "wide_gap_insulator" in labels

    def test_magnetic(self):
        apps = classify_applications(total_magnetization=5.0)
        labels = [a["label"] for a in apps]
        assert "magnetic_candidate" in labels

    def test_catalytic(self):
        apps = classify_applications(elements=["Pt", "O"])
        labels = [a["label"] for a in apps]
        assert "catalytic_candidate" in labels

    def test_structural(self):
        apps = classify_applications(bulk_modulus=200.0)
        labels = [a["label"] for a in apps]
        assert "structural_candidate" in labels

    def test_unknown_no_data(self):
        apps = classify_applications()
        assert apps[0]["label"] == "unknown_application"

    def test_evidence_level_propagated(self):
        apps = classify_applications(band_gap=1.5, band_gap_evidence=PREDICTED)
        sc = [a for a in apps if a["label"] == "semiconductor"][0]
        assert sc["evidence_level"] == PREDICTED

    def test_predicted_lower_score(self):
        known = classify_applications(band_gap=1.5, band_gap_evidence=KNOWN)
        pred = classify_applications(band_gap=1.5, band_gap_evidence=PREDICTED)
        k_score = [a for a in known if a["label"] == "semiconductor"][0]["score"]
        p_score = [a for a in pred if a["label"] == "semiconductor"][0]["score"]
        assert k_score > p_score


# ================================================================
# Comparison tests
# ================================================================

class TestComparison:
    def test_comparison_table(self, test_db, fp_store):
        table = build_comparison_table(
            None, "NaCl", ["Cl", "Na"], 225, test_db, fp_store, top_k=3)
        assert len(table) > 0
        row = table[0]
        assert "formula" in row
        assert "similarity" in row
        assert "band_gap" in row
        assert row["band_gap"]["evidence"] in (KNOWN, UNAVAILABLE)

    def test_comparison_without_store(self, test_db):
        table = build_comparison_table(
            None, "NaCl", ["Cl", "Na"], 225, test_db, None, top_k=3)
        assert len(table) > 0


# ================================================================
# Report tests
# ================================================================

class TestReport:
    def test_exact_match(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], spacegroup=225, db=test_db, store=fp_store)
        assert report["existence_status"] == EXACT_KNOWN_MATCH
        assert len(report["exact_matches"]) >= 1
        assert "band_gap" in report["known_properties"]
        assert report["known_properties"]["band_gap"]["evidence"] == KNOWN

    def test_near_known_match(self, test_db, fp_store):
        # KCl not in corpus but similar to NaCl
        report = generate_report(
            "KCl", ["Cl", "K"], spacegroup=225, db=test_db, store=fp_store)
        assert report["existence_status"] in (NEAR_KNOWN_MATCH, NOT_FOUND_IN_CORPUS)

    def test_not_found(self, test_db, fp_store):
        report = generate_report(
            "UPu3", ["Pu", "U"], spacegroup=12, db=test_db, store=fp_store)
        assert report["existence_status"] == NOT_FOUND_IN_CORPUS

    def test_material_id_lookup(self, test_db, fp_store):
        cid = CORPUS[0].canonical_id
        report = generate_report(
            "", [], material_id=cid, db=test_db, store=fp_store)
        assert report["existence_status"] == EXACT_KNOWN_MATCH
        assert report["query_formula"] == "NaCl"

    def test_evidence_summary_present(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], spacegroup=225, db=test_db, store=fp_store)
        es = report["evidence_summary"]
        assert es["known_count"] > 0
        assert "unavailable_fields" in es

    def test_applications_present(self, test_db, fp_store):
        report = generate_report(
            "GaAs", ["As", "Ga"], spacegroup=216, db=test_db, store=fp_store)
        assert len(report["likely_applications"]) > 0
        assert "label" in report["likely_applications"][0]

    def test_comparison_table_present(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], spacegroup=225, db=test_db, store=fp_store)
        assert len(report["comparison_table"]) > 0

    def test_unavailable_properties(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        assert "density" in report["unavailable_properties"]
        assert report["unavailable_properties"]["density"]["evidence"] == UNAVAILABLE

    def test_method_notes(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        assert len(report["method_notes"]) > 0
        assert any("corpus" in n.lower() for n in report["method_notes"])

    def test_confidence_note(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        assert report["confidence_note"]
        assert "confidence" in report["confidence_note"].lower()

    def test_tp_context(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], db=test_db, store=fp_store,
            temperature_K=1000.0, pressure_GPa=5.0)
        assert report["thermo_pressure_context"] is not None
        assert report["thermo_pressure_context"]["temperature_K"] == 1000.0

    def test_no_structure_reduces_confidence(self, test_db, fp_store):
        # Si has no structure_data
        report = generate_report(
            "Si", ["Si"], spacegroup=227, db=test_db, store=fp_store)
        assert "not possible" in report["confidence_note"].lower() or \
               "not available" in report["confidence_note"].lower()

    def test_json_serializable(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        json.dumps(report)

    def test_novelty_score(self, test_db, fp_store):
        report = generate_report(
            "NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        assert isinstance(report["novelty_score"], float)


# ================================================================
# API tests
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

    def test_get_intelligence(self):
        c = self._client()
        r = c.get("/materials?limit=1")
        cid = r.json()["data"][0]["canonical_id"]
        r2 = c.get(f"/intelligence/material/{cid}")
        assert r2.status_code == 200
        d = r2.json()
        assert "existence_status" in d
        assert "likely_applications" in d
        assert "evidence_summary" in d

    def test_get_intelligence_not_found(self):
        c = self._client()
        r = c.get("/intelligence/nonexistent")
        assert r.status_code == 404

    def test_post_report(self):
        c = self._client()
        r = c.post("/intelligence/report", json={
            "formula": "NaCl", "elements": ["Cl", "Na"], "spacegroup": 225})
        assert r.status_code == 200
        d = r.json()
        assert d["existence_status"] == EXACT_KNOWN_MATCH

    def test_post_report_unknown(self):
        c = self._client()
        r = c.post("/intelligence/report", json={
            "formula": "UPu3", "elements": ["Pu", "U"]})
        assert r.status_code == 200
        assert r.json()["existence_status"] == NOT_FOUND_IN_CORPUS

    def test_post_compare(self):
        c = self._client()
        r = c.post("/intelligence/compare", json={
            "formula": "NaCl", "elements": ["Cl", "Na"], "top_k": 3})
        assert r.status_code == 200
        assert "comparison_table" in r.json()

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/materials?limit=1").status_code == 200
        assert c.get("/generation/presets").status_code == 200
        assert c.get("/campaigns/presets").status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "2.2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
