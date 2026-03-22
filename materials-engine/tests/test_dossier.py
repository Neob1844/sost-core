"""Tests for the Material Validation Dossier layer (Phase III.F)."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.features.fingerprint_store import FingerprintStore
from src.intelligence.evidence import (
    KNOWN, PREDICTED, PROXY, UNAVAILABLE,
    EXACT_KNOWN_MATCH, NEAR_KNOWN_MATCH, NOT_FOUND_IN_CORPUS,
    GENERATED_HYPOTHESIS, EXISTENCE_DISCLAIMER,
)
from src.intelligence.dossier import (
    build_dossier, build_dossier_from_evaluation,
    save_dossier, load_dossier, list_dossiers,
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


# ================================================================
# Dossier build tests
# ================================================================

class TestDossierBuild:
    def test_exact_match(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], spacegroup=225,
                          query_type="corpus_material",
                          db=test_db, store=fp_store)
        assert d["existence_status"] == EXACT_KNOWN_MATCH
        assert d["dossier_id"]
        assert "band_gap" in d["known_properties"]
        assert d["validation_priority"] == "low"  # known material

    def test_near_known(self, test_db, fp_store):
        d = build_dossier("KCl", ["Cl", "K"], spacegroup=225,
                          db=test_db, store=fp_store)
        assert d["existence_status"] in (NEAR_KNOWN_MATCH, NOT_FOUND_IN_CORPUS)

    def test_not_found(self, test_db, fp_store):
        d = build_dossier("UPu3", ["Pu", "U"], spacegroup=12,
                          db=test_db, store=fp_store)
        assert d["existence_status"] == NOT_FOUND_IN_CORPUS

    def test_generated_hypothesis(self, test_db, fp_store):
        d = build_dossier("UPu3", ["Pu", "U"], spacegroup=12,
                          query_type="generated_candidate",
                          candidate_id="test_cand_123",
                          db=test_db, store=fp_store)
        assert d["existence_status"] == GENERATED_HYPOTHESIS
        assert d["query_candidate_id"] == "test_cand_123"
        assert d["query_type"] == "generated_candidate"

    def test_insufficient_structure(self, test_db, fp_store):
        # Si has no structure_data
        d = build_dossier("Si", ["Si"], spacegroup=227,
                          material_id=CORPUS[2].canonical_id,
                          query_type="corpus_material",
                          db=test_db, store=fp_store)
        # Structure is not available for Si in our test corpus
        assert not d["query_has_structure"]
        # Limitations should mention structure
        assert any("structure" in lim.lower() for lim in d["limitations"])

    def test_with_evaluation_data(self, test_db, fp_store):
        eval_data = {
            "candidate_id": "eval_test",
            "formula": "KBr",
            "elements": ["Br", "K"],
            "spacegroup": 225,
            "scores": {"evaluation": 0.65},
            "lift": {"confidence": 0.7},
            "predictions": {
                "formation_energy": -3.2,
                "band_gap": 6.5,
            },
        }
        d = build_dossier("KBr", ["Br", "K"], spacegroup=225,
                          query_type="generated_candidate",
                          candidate_id="eval_test",
                          db=test_db, store=fp_store,
                          evaluation_data=eval_data)
        assert d["evaluation_score"] == 0.65
        assert "formation_energy" in d["predicted_properties"]
        assert d["predicted_properties"]["formation_energy"]["evidence"] == PREDICTED

    def test_with_tp_context(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store,
                          temperature_K=1500.0, pressure_GPa=20.0)
        assert d["thermo_pressure_context"] is not None
        assert "thermal_risk_proxy" in d["proxy_properties"]
        assert "pressure_sensitivity_proxy" in d["proxy_properties"]


# ================================================================
# Evidence classification tests
# ================================================================

class TestEvidenceInDossier:
    def test_known_properties_tagged(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], spacegroup=225,
                          db=test_db, store=fp_store)
        for k, v in d["known_properties"].items():
            assert v["evidence"] == KNOWN

    def test_unavailable_properties_tagged(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        for k, v in d["unavailable_properties"].items():
            assert v["evidence"] == UNAVAILABLE

    def test_proxy_properties_tagged(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store,
                          temperature_K=1500.0)
        for k, v in d["proxy_properties"].items():
            assert v["evidence"] == PROXY

    def test_evidence_summary(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        es = d["evidence_summary"]
        assert es["known_count"] >= 1
        assert es["unavailable_count"] >= 1
        total = (es["known_count"] + es["predicted_count"]
                 + es["proxy_count"] + es["unavailable_count"])
        assert total > 0


# ================================================================
# Validation priority tests
# ================================================================

class TestValidationPriority:
    def test_known_material_low_priority(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], spacegroup=225,
                          db=test_db, store=fp_store)
        assert d["validation_priority"] == "low"
        assert "already_known_in_corpus" in d["validation_rationale"]["reason_codes"]

    def test_generated_with_good_eval(self, test_db, fp_store):
        eval_data = {
            "scores": {"evaluation": 0.7},
            "lift": {"confidence": 0.7},
            "predictions": {"formation_energy": -2.0, "band_gap": 1.5},
        }
        d = build_dossier("XYZ", ["X"], spacegroup=12,
                          query_type="generated_candidate",
                          db=test_db, store=fp_store,
                          evaluation_data=eval_data)
        # With high eval score, should get at least medium
        assert d["validation_priority"] in ("high", "medium")

    def test_rationale_has_components(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        r = d["validation_rationale"]
        assert "priority_score" in r
        assert "components" in r
        assert "weights_used" in r


# ================================================================
# Application classification in dossier
# ================================================================

class TestApplicationsInDossier:
    def test_applications_present(self, test_db, fp_store):
        d = build_dossier("Fe2O3", ["Fe", "O"], spacegroup=167,
                          db=test_db, store=fp_store)
        assert len(d["likely_applications"]) > 0
        for app in d["likely_applications"]:
            assert "label" in app
            assert "score" in app
            assert "evidence_level" in app

    def test_high_pressure_candidate(self, test_db, fp_store):
        d = build_dossier("WC", ["C", "W"], db=test_db, store=fp_store)
        labels = [a["label"] for a in d["likely_applications"]]
        assert "high_pressure_candidate" in labels


# ================================================================
# Comparison table in dossier
# ================================================================

class TestComparisonInDossier:
    def test_comparison_table_present(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        assert len(d["comparison_table"]) > 0
        row = d["comparison_table"][0]
        assert "formula" in row
        assert "similarity" in row
        assert "band_gap" in row

    def test_comparison_evidence_tagged(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        for row in d["comparison_table"]:
            assert row["band_gap"]["evidence"] in (KNOWN, UNAVAILABLE)


# ================================================================
# Persistence tests
# ================================================================

class TestPersistence:
    def test_save_and_load(self, test_db, fp_store, temp_dir):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        path = save_dossier(d, output_dir=temp_dir)
        assert os.path.exists(path)
        loaded = load_dossier(d["dossier_id"], output_dir=temp_dir)
        assert loaded is not None
        assert loaded["dossier_id"] == d["dossier_id"]

    def test_list_dossiers(self, test_db, fp_store, temp_dir):
        d1 = build_dossier("NaCl", ["Cl", "Na"],
                           db=test_db, store=fp_store)
        d2 = build_dossier("Si", ["Si"],
                           db=test_db, store=fp_store)
        save_dossier(d1, output_dir=temp_dir)
        save_dossier(d2, output_dir=temp_dir)
        dossiers = list_dossiers(output_dir=temp_dir)
        assert len(dossiers) == 2

    def test_json_serializable(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        json.dumps(d)  # must not raise

    def test_limitations_present(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        assert len(d["limitations"]) > 0
        assert any("corpus" in lim.lower() for lim in d["limitations"])

    def test_method_notes_present(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"],
                          db=test_db, store=fp_store)
        assert len(d["method_notes"]) > 0


# ================================================================
# From evaluation tests
# ================================================================

class TestFromEvaluation:
    def test_build_from_eval(self, test_db, fp_store):
        eval_data = {
            "candidate_id": "eval_123",
            "formula": "KBr",
            "elements": ["Br", "K"],
            "spacegroup": 225,
            "scores": {"evaluation": 0.55},
            "lift": {"confidence": 0.7},
            "predictions": {"formation_energy": -3.0},
        }
        d = build_dossier_from_evaluation(eval_data, test_db, fp_store)
        assert d["query_type"] == "generated_candidate"
        assert d["query_candidate_id"] == "eval_123"


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

    def test_intelligence_status(self):
        c = self._client()
        r = c.get("/intelligence/status")
        assert r.status_code == 200
        assert "dossiers" in r.json()

    def test_get_material_intelligence(self):
        c = self._client()
        r = c.get("/materials?limit=1")
        cid = r.json()["data"][0]["canonical_id"]
        r2 = c.get(f"/intelligence/material/{cid}")
        assert r2.status_code == 200
        assert "existence_status" in r2.json()

    def test_post_report(self):
        c = self._client()
        r = c.post("/intelligence/report", json={
            "formula": "NaCl", "elements": ["Cl", "Na"]})
        assert r.status_code == 200

    def test_post_compare(self):
        c = self._client()
        r = c.post("/intelligence/compare", json={
            "formula": "NaCl", "elements": ["Cl", "Na"], "top_k": 3})
        assert r.status_code == 200

    def test_dossier_from_eval_not_found(self):
        c = self._client()
        r = c.post("/intelligence/dossier/from-evaluation",
                    json={"evaluation_id": "nonexistent"})
        assert r.status_code == 404

    def test_get_dossier_not_found(self):
        c = self._client()
        r = c.get("/intelligence/dossier/nonexistent")
        assert r.status_code == 404

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/materials?limit=1").status_code == 200
        assert c.get("/generation/presets").status_code == 200
        assert c.get("/campaigns/presets").status_code == 200
        assert c.get("/shortlist/default-criteria").status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "3.1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
