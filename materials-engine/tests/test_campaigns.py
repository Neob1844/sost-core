"""Tests for campaigns, fingerprint store, retrieval index, and API.

Phase III.C: Comprehensive tests for corpus scale, fast retrieval, and campaigns.
"""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np

from src.schema import Material
from src.storage.db import MaterialsDB
from src.features.fingerprint_store import FingerprintStore, FINGERPRINT_VERSION, VECTOR_DIM
from src.retrieval.index import RetrievalIndex
from src.campaigns.spec import (
    CampaignSpec, CampaignValidationError, ALL_PRESETS,
    exotic_materials_default, low_formation_energy_default,
    band_gap_window_default, tp_sensitive_candidates_default,
    high_novelty_watchlist_default, CAMPAIGN_TYPES,
)
from src.campaigns.engine import CampaignEngine


# ================================================================
# Helpers
# ================================================================

def _make_material(formula, elements, spacegroup=None, band_gap=None,
                   formation_energy=None, has_valid_structure=True,
                   source="test", source_id=None):
    m = Material(
        formula=formula, elements=sorted(elements), n_elements=len(elements),
        spacegroup=spacegroup, band_gap=band_gap,
        formation_energy=formation_energy,
        has_valid_structure=has_valid_structure,
        source=source, source_id=source_id or formula,
        confidence=0.8,
    )
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5),
    _make_material("TiO2", ["O", "Ti"], 136, 3.2, -3.4),
    _make_material("NaCl", ["Cl", "Na"], 225, 8.5, -4.2),
    _make_material("Si", ["Si"], 227, 1.1, 0.0),
    _make_material("GaAs", ["As", "Ga"], 216, 1.4, -0.7),
    _make_material("ZnO", ["O", "Zn"], 186, 3.3, -3.5),
    _make_material("CuO", ["Cu", "O"], 15, 1.2, -1.6),
    _make_material("Al2O3", ["Al", "O"], 167, 8.8, -3.7, source_id="Al2O3_2"),
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
# FingerprintStore tests
# ================================================================

class TestFingerprintStore:
    def test_build(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        manifest = store.build(test_db)
        assert manifest["indexed"] == 8
        assert manifest["vector_dim"] == VECTOR_DIM
        assert manifest["fingerprint_version"] == FINGERPRINT_VERSION
        assert store.is_loaded

    def test_load(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)

        store2 = FingerprintStore(store_dir=temp_dir)
        assert store2.load()
        assert store2.size == 8

    def test_load_nonexistent(self, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        assert not store.load()

    def test_ensure_loaded_builds(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        assert store.ensure_loaded(db=test_db)
        assert store.size == 8

    def test_ensure_loaded_from_disk(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        store2 = FingerprintStore(store_dir=temp_dir)
        assert store2.ensure_loaded()
        assert store2.size == 8

    def test_vectors_shape(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        vecs = store.get_vectors()
        assert vecs.shape == (8, VECTOR_DIM)

    def test_ids_match(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        assert len(store.get_ids()) == 8
        assert len(store.get_formulas()) == 8

    def test_empty_corpus(self, temp_dir):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        store = FingerprintStore(store_dir=temp_dir)
        manifest = store.build(db)
        assert manifest["indexed"] == 0
        os.unlink(f.name)


# ================================================================
# RetrievalIndex tests
# ================================================================

class TestRetrievalIndex:
    def test_build_and_search(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        idx = RetrievalIndex(store)
        idx.build()
        assert idx.is_ready
        assert idx.size == 8

    def test_search_returns_results(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        idx = RetrievalIndex(store)
        idx.build()

        # Query with Fe2O3-like fingerprint
        from src.novelty.fingerprint import combined_fingerprint
        fp = combined_fingerprint(["Fe", "O"], spacegroup=167, band_gap=2.1)
        results = idx.search(fp, top_k=3)
        assert len(results) == 3
        assert results[0][2] > 0.5  # should have decent similarity

    def test_search_exclude_id(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        idx = RetrievalIndex(store)
        idx.build()

        from src.novelty.fingerprint import combined_fingerprint
        fp = combined_fingerprint(["Fe", "O"], spacegroup=167)
        results_all = idx.search(fp, top_k=8)
        first_id = results_all[0][0]
        results_excl = idx.search(fp, top_k=8, exclude_id=first_id)
        excluded_ids = [r[0] for r in results_excl]
        assert first_id not in excluded_ids

    def test_search_empty_query(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        idx = RetrievalIndex(store)
        idx.build()
        results = idx.search(np.zeros(VECTOR_DIM), top_k=5)
        assert results == []

    def test_status(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        idx = RetrievalIndex(store)
        idx.build()
        s = idx.status()
        assert s["ready"]
        assert s["indexed"] == 8
        assert s["method"] == "cosine_dot_product"

    def test_not_ready_before_build(self, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        idx = RetrievalIndex(store)
        assert not idx.is_ready
        assert idx.size == 0


# ================================================================
# Campaign spec tests
# ================================================================

class TestCampaignSpec:
    def test_valid_spec(self):
        spec = CampaignSpec(name="Test", campaign_type="custom")
        spec.validate()

    def test_empty_name_rejected(self):
        spec = CampaignSpec(name="", campaign_type="custom")
        with pytest.raises(CampaignValidationError, match="name"):
            spec.validate()

    def test_unknown_type_rejected(self):
        spec = CampaignSpec(name="Test", campaign_type="magic")
        with pytest.raises(CampaignValidationError, match="Unknown type"):
            spec.validate()

    def test_all_types_valid(self):
        for t in CAMPAIGN_TYPES:
            spec = CampaignSpec(name=f"Test {t}", campaign_type=t)
            spec.validate()

    def test_campaign_id_deterministic(self):
        spec = CampaignSpec(name="Test", campaign_type="custom")
        id1 = spec.campaign_id()
        id2 = spec.campaign_id()
        assert id1 == id2

    def test_to_dict_roundtrip(self):
        spec = exotic_materials_default()
        d = spec.to_dict()
        spec2 = CampaignSpec.from_dict(d)
        assert spec2.name == spec.name
        assert spec2.campaign_type == spec.campaign_type

    def test_all_presets_valid(self):
        for name, fn in ALL_PRESETS.items():
            spec = fn()
            spec.validate()

    def test_preset_exotic(self):
        s = exotic_materials_default()
        assert s.campaign_type == "exotic_hunt"

    def test_preset_stability(self):
        s = low_formation_energy_default()
        assert s.criteria["max_formation_energy"] == 0.0

    def test_preset_band_gap(self):
        s = band_gap_window_default(target=2.0, tolerance=1.0)
        assert s.criteria["band_gap_target"] == 2.0

    def test_preset_tp(self):
        s = tp_sensitive_candidates_default()
        assert s.temperature_K == 1200.0
        assert s.pressure_GPa == 10.0

    def test_preset_novelty(self):
        s = high_novelty_watchlist_default()
        assert s.campaign_type == "novelty_hunt"


# ================================================================
# Campaign engine tests
# ================================================================

class TestCampaignEngine:
    def test_run_campaign(self, test_db):
        engine = CampaignEngine(test_db, output_dir=tempfile.mkdtemp())
        spec = CampaignSpec(name="Test Run", campaign_type="custom",
                            objective="Testing", top_k=3)
        result = engine.run(spec)
        assert result["status"] == "completed"
        assert "shortlist" in result
        assert result["result_summary"]["pool_size"] == 8

    def test_run_and_save(self, test_db):
        out_dir = tempfile.mkdtemp()
        engine = CampaignEngine(test_db, output_dir=out_dir)
        spec = CampaignSpec(name="Save Test", campaign_type="custom")
        result, path = engine.run_and_save(spec)
        assert os.path.exists(path)
        shutil.rmtree(out_dir)

    def test_get_run(self, test_db):
        out_dir = tempfile.mkdtemp()
        engine = CampaignEngine(test_db, output_dir=out_dir)
        spec = CampaignSpec(name="Get Test", campaign_type="custom")
        result, _ = engine.run_and_save(spec)
        cid = result["campaign_id"]
        loaded = engine.get_run(cid)
        assert loaded is not None
        assert loaded["campaign_id"] == cid
        shutil.rmtree(out_dir)

    def test_get_run_not_found(self, test_db):
        engine = CampaignEngine(test_db, output_dir=tempfile.mkdtemp())
        assert engine.get_run("nonexistent") is None

    def test_list_runs(self, test_db):
        out_dir = tempfile.mkdtemp()
        engine = CampaignEngine(test_db, output_dir=out_dir)
        for i in range(3):
            spec = CampaignSpec(name=f"List Test {i}", campaign_type="custom")
            engine.run_and_save(spec)
        runs = engine.list_runs()
        assert len(runs) == 3
        shutil.rmtree(out_dir)

    def test_campaign_with_tp(self, test_db):
        engine = CampaignEngine(test_db, output_dir=tempfile.mkdtemp())
        spec = tp_sensitive_candidates_default()
        result = engine.run(spec)
        assert result["conditions_used"] is not None

    def test_campaign_with_preset(self, test_db):
        engine = CampaignEngine(test_db, output_dir=tempfile.mkdtemp())
        spec = low_formation_energy_default()
        result = engine.run(spec)
        assert result["status"] == "completed"

    def test_empty_corpus_campaign(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        engine = CampaignEngine(db, output_dir=tempfile.mkdtemp())
        spec = CampaignSpec(name="Empty", campaign_type="custom")
        result = engine.run(spec)
        assert result["result_summary"]["pool_size"] == 0
        os.unlink(f.name)

    def test_campaign_reproducible(self, test_db):
        out1 = tempfile.mkdtemp()
        out2 = tempfile.mkdtemp()
        e1 = CampaignEngine(test_db, output_dir=out1)
        e2 = CampaignEngine(test_db, output_dir=out2)
        spec = exotic_materials_default()
        r1 = e1.run(spec)
        r2 = e2.run(spec)
        scores1 = [c["scores"]["shortlist"] for c in r1["shortlist"]]
        scores2 = [c["scores"]["shortlist"] for c in r2["shortlist"]]
        assert scores1 == scores2
        shutil.rmtree(out1)
        shutil.rmtree(out2)


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

    def test_get_presets(self):
        c = self._client()
        r = c.get("/campaigns/presets")
        assert r.status_code == 200
        d = r.json()
        assert "presets" in d
        assert "exotic_materials_default" in d["presets"]

    def test_run_campaign(self):
        c = self._client()
        r = c.post("/campaigns/run", json={
            "name": "API Test", "campaign_type": "custom", "top_k": 3})
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "completed"
        assert "shortlist" in d

    def test_run_campaign_invalid(self):
        c = self._client()
        r = c.post("/campaigns/run", json={"name": "", "campaign_type": "custom"})
        assert r.status_code == 400

    def test_get_campaign_not_found(self):
        c = self._client()
        r = c.get("/campaigns/nonexistent")
        assert r.status_code == 404

    def test_retrieval_status(self):
        c = self._client()
        r = c.get("/retrieval/status")
        assert r.status_code == 200
        # May or may not be ready depending on whether store was built

    def test_similar_search_no_index(self):
        c = self._client()
        r = c.post("/similar/search", json={
            "formula": "Fe2O3", "elements": ["Fe", "O"], "top_k": 3})
        # 503 if no fingerprint store built
        assert r.status_code in (200, 503)

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/stats").status_code == 200
        assert c.get("/materials?limit=2").status_code == 200
        assert c.get("/candidates/exotic?top_k=2").status_code == 200
        assert c.get("/shortlist/default-criteria").status_code == 200
        assert c.post("/shortlist/build", json={}).status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "3.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
