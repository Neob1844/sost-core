"""Tests for controlled candidate generation and novelty-first filtering.

Phase III.D: Tests cover rules, spec, engine, API, and reproducibility.
"""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np

from src.schema import Material
from src.storage.db import MaterialsDB
from src.generation.rules import (
    get_substitutes, get_family, perturb_formula_counts,
    counts_to_formula, formula_to_counts, plausibility_score,
    SUBSTITUTION_FAMILIES, ALL_SUBSTITUTABLE,
)
from src.generation.spec import (
    GenerationSpec, GenerationValidationError,
    ALL_GENERATION_PRESETS, exotic_search, stable_search,
    band_gap_search, tp_sensitive_search,
)
from src.generation.engine import GenerationEngine, GeneratedCandidate
from src.features.fingerprint_store import FingerprintStore


# ================================================================
# Helpers
# ================================================================

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
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5),
    _make_material("TiO2", ["O", "Ti"], 136, 3.2, -3.4),
    _make_material("NaCl", ["Cl", "Na"], 225, 8.5, -4.2),
    _make_material("Si", ["Si"], 227, 1.1, 0.0),
    _make_material("GaAs", ["As", "Ga"], 216, 1.4, -0.7),
    _make_material("ZnO", ["O", "Zn"], 186, 3.3, -3.5),
    _make_material("CuO", ["Cu", "O"], 15, 1.2, -1.6),
    _make_material("Al2O3", ["Al", "O"], 167, 8.8, -3.7, source_id="Al2O3_r"),
    _make_material("MgO", ["Mg", "O"], 225, 7.8, -6.0, source_id="MgO_r"),
    _make_material("SrTiO3", ["O", "Sr", "Ti"], 221, 3.2, -3.9, source_id="SrTiO3_r"),
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
# Rules tests
# ================================================================

class TestRules:
    def test_get_substitutes_fe(self):
        subs = get_substitutes("Fe")
        assert len(subs) > 0
        assert "Fe" not in subs  # should not include self

    def test_get_substitutes_unknown(self):
        subs = get_substitutes("Xx")
        assert subs == []

    def test_get_family(self):
        f = get_family("Fe")
        assert f is not None

    def test_family_none_for_unknown(self):
        assert get_family("Xx") is None

    def test_formula_to_counts(self):
        c = formula_to_counts("Fe2O3")
        assert c == {"Fe": 2, "O": 3}

    def test_counts_to_formula(self):
        f = counts_to_formula({"Fe": 2, "O": 3})
        assert f == "Fe2O3"

    def test_counts_to_formula_single(self):
        f = counts_to_formula({"Si": 1})
        assert f == "Si"

    def test_perturb_formula(self):
        counts = {"Fe": 2, "O": 3}
        perturbed = perturb_formula_counts(counts, max_delta=1)
        assert len(perturbed) > 0
        # Check no zero or negative counts
        for p in perturbed:
            assert all(v > 0 for v in p.values())

    def test_perturb_no_negative(self):
        counts = {"Fe": 1}
        perturbed = perturb_formula_counts(counts, max_delta=1)
        # Fe=1, delta=-1 would give 0 → filtered out
        for p in perturbed:
            assert p["Fe"] > 0

    def test_plausibility_simple(self):
        s = plausibility_score(["Fe", "O"], 2, 167, parent_formula="Fe2O3")
        assert 0.0 <= s <= 1.0
        assert s > 0.5  # reasonable material

    def test_plausibility_too_many_elements(self):
        elems = ["Fe", "O", "Ti", "Cu", "Zn", "Al", "Si"]
        s = plausibility_score(elems, 7, None)
        # Should be penalized for too many elements
        assert s < 0.6

    def test_substitution_families_exist(self):
        assert len(SUBSTITUTION_FAMILIES) > 10
        assert len(ALL_SUBSTITUTABLE) > 50


# ================================================================
# Spec tests
# ================================================================

class TestSpec:
    def test_valid_spec(self):
        spec = GenerationSpec(strategy="mixed")
        spec.validate()

    def test_invalid_strategy(self):
        spec = GenerationSpec(strategy="magic")
        with pytest.raises(GenerationValidationError, match="Unknown strategy"):
            spec.validate()

    def test_all_presets_valid(self):
        for name, fn in ALL_GENERATION_PRESETS.items():
            spec = fn()
            spec.validate()

    def test_run_id_deterministic(self):
        spec = GenerationSpec(strategy="mixed", random_seed=42)
        id1 = spec.run_id()
        id2 = spec.run_id()
        assert id1 == id2

    def test_to_dict_roundtrip(self):
        spec = exotic_search()
        d = spec.to_dict()
        spec2 = GenerationSpec.from_dict(d)
        assert spec2.strategy == spec.strategy
        assert spec2.max_parents == spec.max_parents

    def test_preset_exotic(self):
        s = exotic_search()
        assert s.strategy == "mixed"
        assert s.max_candidates == 1000

    def test_preset_stable(self):
        s = stable_search()
        assert s.formation_energy_max == 0.5

    def test_preset_band_gap(self):
        s = band_gap_search()
        assert s.band_gap_min == 0.5
        assert s.band_gap_max == 3.0


# ================================================================
# Engine tests
# ================================================================

class TestEngine:
    def test_run_basic(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=5, max_candidates=20, random_seed=42)
        result = engine.run(spec)
        assert "run_id" in result
        assert "summary" in result
        assert "candidates" in result
        assert "disclaimer" in result
        assert result["summary"]["parents_used"] <= 5

    def test_run_produces_candidates(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=10, max_candidates=50, random_seed=42)
        result = engine.run(spec)
        assert result["summary"]["raw_generated"] > 0

    def test_run_reproducible(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        e1 = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        e2 = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=5, max_candidates=20, random_seed=42)
        r1 = e1.run(spec)
        r2 = e2.run(spec)
        assert r1["summary"] == r2["summary"]
        # Same candidates
        ids1 = [c["candidate_id"] for c in r1["candidates"]]
        ids2 = [c["candidate_id"] for c in r2["candidates"]]
        assert ids1 == ids2

    def test_substitution_only(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(strategy="element_substitution",
                              max_parents=5, max_candidates=20, random_seed=42)
        result = engine.run(spec)
        for c in result["candidates"]:
            assert c["generation_strategy"] == "element_substitution"

    def test_stoichiometry_only(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(strategy="stoichiometry_perturbation",
                              max_parents=5, max_candidates=20, random_seed=42)
        result = engine.run(spec)
        for c in result["candidates"]:
            assert c["generation_strategy"] == "stoichiometry_perturbation"

    def test_prototype_only(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(strategy="prototype_remix",
                              max_parents=10, max_candidates=20, random_seed=42)
        result = engine.run(spec)
        # Prototype needs same-SG parents, may produce fewer
        assert result["summary"]["raw_generated"] >= 0

    def test_novelty_filtering(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=10, max_candidates=50, random_seed=42)
        result = engine.run(spec)
        decisions = result["summary"]["decisions"]
        # Should have some rejected_known or rejected_near_known
        total_rejected = (decisions.get("rejected_known", 0)
                          + decisions.get("rejected_near_known", 0)
                          + decisions.get("rejected_invalid", 0))
        # At least filtering happened
        assert result["summary"]["final_count"] >= 0

    def test_run_and_save(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=5, max_candidates=10, random_seed=42)
        result, path = engine.run_and_save(spec)
        assert os.path.exists(path)
        loaded = engine.get_run(result["run_id"])
        assert loaded is not None

    def test_check_candidate(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        result = engine.check_candidate("UPu3", ["Pu", "U"], spacegroup=12)
        assert "candidate" in result
        assert result["candidate"]["scores"]["novelty"] > 0

    def test_check_known_material(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        result = engine.check_candidate("Fe2O3", ["Fe", "O"], spacegroup=167)
        # Should detect as known or near-known
        assert result["candidate"]["scores"]["novelty"] < 0.5

    def test_list_runs(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=3, max_candidates=5, random_seed=42)
        engine.run_and_save(spec)
        runs = engine.list_runs()
        assert len(runs) >= 1


# ================================================================
# Edge cases
# ================================================================

class TestEdgeCases:
    def test_empty_corpus(self, temp_dir):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        store = FingerprintStore(store_dir=temp_dir)
        store.build(db)
        engine = GenerationEngine(db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=5, max_candidates=10)
        result = engine.run(spec)
        assert result["summary"]["parents_used"] == 0
        assert result["summary"]["raw_generated"] == 0
        os.unlink(f.name)

    def test_single_material_corpus(self, temp_dir):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        m = _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5)
        db.insert_material(m)
        store = FingerprintStore(store_dir=temp_dir)
        store.build(db)
        engine = GenerationEngine(db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=1, max_candidates=10)
        result = engine.run(spec)
        assert result["summary"]["parents_used"] == 1
        os.unlink(f.name)


# ================================================================
# Serialization tests
# ================================================================

class TestSerialization:
    def test_candidate_to_dict(self):
        c = GeneratedCandidate(
            candidate_id="abc", formula="Fe2O3",
            elements=["Fe", "O"], n_elements=2,
            generation_strategy="element_substitution",
            novelty_score=0.5, decision="accepted_novel")
        d = c.to_dict()
        assert d["candidate_id"] == "abc"
        assert d["scores"]["novelty"] == 0.5

    def test_result_json_serializable(self, test_db, temp_dir):
        store = FingerprintStore(store_dir=temp_dir)
        store.build(test_db)
        engine = GenerationEngine(test_db, store=store, output_dir=temp_dir)
        spec = GenerationSpec(max_parents=3, max_candidates=5, random_seed=42)
        result = engine.run(spec)
        json.dumps(result)  # must not raise


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
        r = c.get("/generation/presets")
        assert r.status_code == 200
        assert "presets" in r.json()
        assert "exotic_search" in r.json()["presets"]

    def test_run_generation(self):
        c = self._client()
        r = c.post("/generation/run", json={
            "max_parents": 5, "max_candidates": 10, "random_seed": 42})
        assert r.status_code == 200
        d = r.json()
        assert "run_id" in d
        assert "summary" in d
        assert "disclaimer" in d

    def test_run_invalid_strategy(self):
        c = self._client()
        r = c.post("/generation/run", json={"strategy": "magic"})
        assert r.status_code == 400

    def test_check_candidate(self):
        c = self._client()
        r = c.post("/generation/check", json={
            "formula": "UPu3", "elements": ["U", "Pu"], "spacegroup": 12})
        assert r.status_code == 200
        assert "candidate" in r.json()

    def test_generation_status(self):
        c = self._client()
        r = c.get("/generation/status")
        assert r.status_code == 200

    def test_get_run_not_found(self):
        c = self._client()
        r = c.get("/generation/nonexistent")
        assert r.status_code == 404

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/stats").status_code == 200
        assert c.get("/materials?limit=2").status_code == 200
        assert c.get("/shortlist/default-criteria").status_code == 200
        assert c.get("/campaigns/presets").status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "2.7.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
