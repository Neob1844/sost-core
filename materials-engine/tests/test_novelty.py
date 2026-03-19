"""Tests for novelty filter, exotic scoring, and related API endpoints.

Phase III.A: Comprehensive tests covering fingerprints, scoring, filtering,
serialization, API propagation, edge cases, and reproducibility.
"""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import numpy as np

from src.schema import Material
from src.storage.db import MaterialsDB
from src.novelty.fingerprint import (
    compositional_fingerprint, structural_fingerprint, combined_fingerprint,
    material_fingerprint, cosine_similarity, element_rarity_score,
    spacegroup_rarity_score, COMP_DIM, STRUCT_DIM, COMBINED_DIM,
)
from src.novelty.scoring import (
    compute_novelty, compute_exotic, NoveltyResult, ExoticResult,
    EXACT_MATCH_THRESHOLD, NEAR_KNOWN_THRESHOLD,
    W_NOVELTY, W_ELEMENT_RARITY, W_STRUCTURE_RARITY, W_NEIGHBOR_SPARSITY,
)
from src.novelty.filter import NoveltyFilter


# ================================================================
# Helpers
# ================================================================

def _make_material(formula, elements, spacegroup=None, band_gap=None,
                   formation_energy=None, source="test", source_id=None):
    m = Material(
        formula=formula, elements=sorted(elements), n_elements=len(elements),
        spacegroup=spacegroup, band_gap=band_gap,
        formation_energy=formation_energy,
        source=source, source_id=source_id or formula,
        confidence=0.8,
    )
    m.compute_canonical_id()
    return m


def _make_db_with_materials(materials):
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = MaterialsDB(f.name)
    for m in materials:
        db.insert_material(m)
    return db, f.name


CORPUS = [
    _make_material("Fe2O3", ["Fe", "O"], spacegroup=167, band_gap=2.1, formation_energy=-1.5),
    _make_material("TiO2", ["O", "Ti"], spacegroup=136, band_gap=3.2, formation_energy=-3.4),
    _make_material("NaCl", ["Cl", "Na"], spacegroup=225, band_gap=8.5, formation_energy=-4.2),
    _make_material("Si", ["Si"], spacegroup=227, band_gap=1.1, formation_energy=0.0),
    _make_material("GaAs", ["As", "Ga"], spacegroup=216, band_gap=1.4, formation_energy=-0.7),
]


@pytest.fixture
def test_db():
    db, path = _make_db_with_materials(CORPUS)
    yield db
    os.unlink(path)


# ================================================================
# Fingerprint tests
# ================================================================

class TestFingerprints:
    def test_compositional_dimensions(self):
        fp = compositional_fingerprint(["Fe", "O"])
        assert fp.shape == (COMP_DIM,)

    def test_compositional_normalized(self):
        fp = compositional_fingerprint(["Fe", "O", "O"])
        assert abs(fp.sum() - 1.0) < 1e-5

    def test_compositional_empty(self):
        fp = compositional_fingerprint([])
        assert fp.sum() == 0.0

    def test_compositional_unknown_element(self):
        fp = compositional_fingerprint(["Xx", "Fe"])
        # Unknown element ignored, only Fe counts
        assert fp.sum() > 0

    def test_structural_dimensions(self):
        fp = structural_fingerprint(spacegroup=225)
        assert fp.shape == (STRUCT_DIM,)

    def test_structural_spacegroup_normalized(self):
        fp = structural_fingerprint(spacegroup=230)
        assert abs(fp[0] - 1.0) < 1e-5

    def test_structural_all_none(self):
        fp = structural_fingerprint()
        assert fp.sum() == 0.0

    def test_combined_dimensions(self):
        fp = combined_fingerprint(["Fe", "O"], spacegroup=167)
        assert fp.shape == (COMBINED_DIM,)
        assert COMBINED_DIM == COMP_DIM + STRUCT_DIM

    def test_material_fingerprint(self):
        m = _make_material("Fe2O3", ["Fe", "O"], spacegroup=167, band_gap=2.1)
        fp = material_fingerprint(m)
        assert fp.shape == (COMBINED_DIM,)
        assert fp.sum() > 0

    def test_cosine_similarity_identical(self):
        a = np.array([1.0, 2.0, 3.0])
        assert abs(cosine_similarity(a, a) - 1.0) < 1e-5

    def test_cosine_similarity_orthogonal(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert abs(cosine_similarity(a, b)) < 1e-5

    def test_cosine_similarity_zero(self):
        a = np.zeros(5)
        b = np.ones(5)
        assert cosine_similarity(a, b) == 0.0

    def test_fingerprint_reproducible(self):
        m = _make_material("TiO2", ["O", "Ti"], spacegroup=136)
        fp1 = material_fingerprint(m)
        fp2 = material_fingerprint(m)
        assert np.array_equal(fp1, fp2)


# ================================================================
# Rarity score tests
# ================================================================

class TestRarity:
    def test_element_rarity_common(self):
        counts = {"Fe": 100, "O": 100}
        score = element_rarity_score(["Fe", "O"], counts, 100)
        assert 0.0 <= score <= 1.0
        # Very common elements should have low rarity
        assert score < 0.5

    def test_element_rarity_rare(self):
        counts = {"Fe": 100, "O": 100, "Pu": 1}
        score = element_rarity_score(["Pu"], counts, 100)
        assert score > 0.5

    def test_element_rarity_unseen(self):
        counts = {"Fe": 50}
        score = element_rarity_score(["Pu"], counts, 100)
        assert score > 0.8

    def test_element_rarity_empty(self):
        assert element_rarity_score([], {}, 0) == 0.0

    def test_spacegroup_rarity_common(self):
        counts = {225: 50, 167: 30}
        score = spacegroup_rarity_score(225, counts, 100)
        assert 0.0 <= score <= 1.0

    def test_spacegroup_rarity_unseen(self):
        counts = {225: 50}
        score = spacegroup_rarity_score(1, counts, 100)
        assert score == 1.0

    def test_spacegroup_rarity_none(self):
        score = spacegroup_rarity_score(None, {}, 100)
        assert score == 0.5  # unknown → moderate


# ================================================================
# Scoring tests
# ================================================================

class TestNoveltyScoring:
    def test_exact_match(self):
        result = compute_novelty(max_similarity=0.99, exact_formula_match=True,
                                 nearest_id="abc", nearest_formula="Fe2O3")
        assert result.exact_match is True
        assert result.novelty_band == "known"
        assert result.novelty_score == 0.0
        assert "exact_formula_and_structure_match" in result.reason_codes

    def test_near_duplicate(self):
        result = compute_novelty(max_similarity=0.99)
        assert result.novelty_band == "known"
        assert result.novelty_score < 0.1

    def test_near_known(self):
        result = compute_novelty(max_similarity=0.90)
        assert result.novelty_band == "near_known"
        assert 0.05 < result.novelty_score < 0.2

    def test_novel_candidate(self):
        result = compute_novelty(max_similarity=0.50)
        assert result.novelty_band == "novel_candidate"
        assert result.novelty_score >= 0.4

    def test_outlier(self):
        result = compute_novelty(max_similarity=0.1)
        assert result.novelty_band == "novel_candidate"
        assert "outlier_candidate" in result.reason_codes
        assert "low_neighbor_density" in result.reason_codes

    def test_no_neighbors(self):
        result = compute_novelty(max_similarity=0.0)
        assert result.novelty_score == 1.0
        assert result.novelty_band == "novel_candidate"

    def test_to_dict(self):
        result = compute_novelty(max_similarity=0.7, nearest_id="x", nearest_formula="Y")
        d = result.to_dict()
        assert "novelty_score" in d
        assert "novelty_band" in d
        assert "nearest_neighbor_id" in d
        assert "reason_codes" in d


class TestExoticScoring:
    def test_weights_sum_to_one(self):
        total = W_NOVELTY + W_ELEMENT_RARITY + W_STRUCTURE_RARITY + W_NEIGHBOR_SPARSITY
        assert abs(total - 1.0) < 1e-5

    def test_all_zero(self):
        result = compute_exotic(0.0, 0.0, 0.0, 0.0)
        assert result.exotic_score == 0.0

    def test_all_one(self):
        result = compute_exotic(1.0, 1.0, 1.0, 1.0)
        assert abs(result.exotic_score - 1.0) < 1e-5

    def test_weighted_correctly(self):
        result = compute_exotic(0.5, 0.5, 0.5, 0.5)
        assert abs(result.exotic_score - 0.5) < 1e-5

    def test_factors_populated(self):
        result = compute_exotic(0.8, 0.9, 0.1, 0.6)
        assert "rare_elements" in result.exotic_factors
        assert "novel_composition" in result.exotic_factors

    def test_top_reason(self):
        result = compute_exotic(0.2, 0.9, 0.1, 0.3)
        assert result.top_reason == "rare_elements"

    def test_to_dict(self):
        result = compute_exotic(0.5, 0.3, 0.2, 0.4)
        d = result.to_dict()
        assert "exotic_score" in d
        assert "components" in d
        assert "weights" in d
        assert "exotic_factors" in d

    def test_clamped(self):
        # Even if inputs are out of range, output should be [0,1]
        result = compute_exotic(1.5, 1.5, 1.5, 1.5)
        assert result.exotic_score <= 1.0


# ================================================================
# Filter integration tests
# ================================================================

class TestNoveltyFilter:
    def test_corpus_loaded(self, test_db):
        nf = NoveltyFilter(test_db)
        assert nf.corpus_size == 5

    def test_check_known_material(self, test_db):
        nf = NoveltyFilter(test_db)
        m = _make_material("Fe2O3", ["Fe", "O"], spacegroup=167, band_gap=2.1,
                           formation_energy=-1.5)
        result = nf.check_novelty(m)
        assert result.novelty_band == "known"
        assert result.exact_match is True

    def test_check_similar_material(self, test_db):
        nf = NoveltyFilter(test_db)
        # Fe3O4 — close to Fe2O3
        m = _make_material("Fe3O4", ["Fe", "O"], spacegroup=227, band_gap=0.1,
                           formation_energy=-1.1)
        result = nf.check_novelty(m)
        # Should be near_known or known due to Fe+O composition overlap
        assert result.novelty_band in ("known", "near_known")
        assert result.nearest_neighbor_similarity > 0.7

    def test_check_novel_material(self, test_db):
        nf = NoveltyFilter(test_db)
        # Something very different from corpus
        m = _make_material("UPu3", ["U", "Pu"], spacegroup=12, band_gap=0.0,
                           formation_energy=1.5)
        result = nf.check_novelty(m)
        assert result.novelty_band == "novel_candidate"
        assert result.novelty_score > 0.5

    def test_check_from_params(self, test_db):
        nf = NoveltyFilter(test_db)
        result = nf.check_novelty_from_params(
            formula="UPu3", elements=["U", "Pu"],
            spacegroup=12, band_gap=0.0, formation_energy=1.5)
        assert result.novelty_band == "novel_candidate"

    def test_exotic_assessment(self, test_db):
        nf = NoveltyFilter(test_db)
        m = _make_material("UPu3", ["U", "Pu"], spacegroup=12,
                           formation_energy=1.5)
        novelty, exotic = nf.check_exotic(m)
        assert exotic.exotic_score > 0.3
        assert novelty.novelty_band == "novel_candidate"

    def test_rank_exotic(self, test_db):
        nf = NoveltyFilter(test_db)
        ranked = nf.rank_exotic(top_k=3)
        assert len(ranked) <= 3
        assert len(ranked) > 0
        # Should be sorted descending by exotic_score
        scores = [r["exotic"]["exotic_score"] for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_rank_exotic_has_all_fields(self, test_db):
        nf = NoveltyFilter(test_db)
        ranked = nf.rank_exotic(top_k=1)
        r = ranked[0]
        assert "canonical_id" in r
        assert "formula" in r
        assert "novelty" in r
        assert "exotic" in r
        assert "novelty_score" in r["novelty"]
        assert "exotic_score" in r["exotic"]

    def test_corpus_summary(self, test_db):
        nf = NoveltyFilter(test_db)
        summary = nf.corpus_summary()
        assert summary["corpus_size"] == 5
        assert "novelty_bands" in summary
        assert "disclaimer" in summary

    def test_reproducible_scores(self, test_db):
        nf1 = NoveltyFilter(test_db)
        nf2 = NoveltyFilter(test_db)
        m = _make_material("GaAs", ["As", "Ga"], spacegroup=216)
        r1 = nf1.check_novelty(m)
        r2 = nf2.check_novelty(m)
        assert r1.novelty_score == r2.novelty_score
        assert r1.novelty_band == r2.novelty_band


# ================================================================
# Edge cases
# ================================================================

class TestEdgeCases:
    def test_empty_corpus(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        nf = NoveltyFilter(db)
        assert nf.corpus_size == 0

        m = _make_material("Fe2O3", ["Fe", "O"])
        result = nf.check_novelty(m)
        # No corpus → novel by default (no neighbors)
        assert result.novelty_score > 0.0

        ranked = nf.rank_exotic(top_k=5)
        assert ranked == []

        os.unlink(f.name)

    def test_single_material_corpus(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        m = _make_material("Fe2O3", ["Fe", "O"], spacegroup=167)
        db.insert_material(m)
        nf = NoveltyFilter(db)
        assert nf.corpus_size == 1

        # Check itself
        result = nf.check_novelty(m)
        assert result.exact_match is True

        os.unlink(f.name)

    def test_material_no_properties(self, test_db):
        nf = NoveltyFilter(test_db)
        m = _make_material("XYZ", ["Fe"], source_id="bare")
        result = nf.check_novelty(m)
        assert result.novelty_band in ("known", "near_known", "novel_candidate")

    def test_material_empty_elements(self, test_db):
        nf = NoveltyFilter(test_db)
        m = Material(formula="", elements=[], n_elements=0,
                     source="test", source_id="empty")
        m.compute_canonical_id()
        result = nf.check_novelty(m)
        assert "insufficient_data_for_fingerprint" in result.reason_codes


# ================================================================
# Serialization tests
# ================================================================

class TestSerialization:
    def test_novelty_result_to_dict(self):
        r = NoveltyResult(novelty_score=0.7, novelty_band="novel_candidate",
                          nearest_neighbor_id="abc", nearest_neighbor_formula="Fe2O3",
                          nearest_neighbor_similarity=0.3,
                          reason_codes=["low_neighbor_density"])
        d = r.to_dict()
        assert d["novelty_score"] == 0.7
        assert d["novelty_band"] == "novel_candidate"
        assert "low_neighbor_density" in d["reason_codes"]

    def test_exotic_result_to_dict(self):
        r = ExoticResult(exotic_score=0.65, novelty_score=0.7,
                         element_rarity=0.8, structure_rarity=0.5,
                         neighbor_sparsity=0.6,
                         exotic_factors=["rare_elements"],
                         top_reason="rare_elements")
        d = r.to_dict()
        assert d["exotic_score"] == 0.65
        assert "components" in d
        assert "weights" in d

    def test_json_serializable(self, test_db):
        nf = NoveltyFilter(test_db)
        m = _make_material("Fe2O3", ["Fe", "O"], spacegroup=167)
        novelty, exotic = nf.check_exotic(m)
        # Must be JSON-serializable
        json.dumps(novelty.to_dict())
        json.dumps(exotic.to_dict())


# ================================================================
# API endpoint tests
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

    def test_get_novelty(self):
        client = self._client()
        # Get a material's canonical_id
        r = client.get("/materials?limit=1")
        cid = r.json()["data"][0]["canonical_id"]
        r2 = client.get(f"/novelty/{cid}")
        assert r2.status_code == 200
        d = r2.json()
        assert "novelty" in d
        assert "exotic" in d
        assert "disclaimer" in d
        assert d["novelty"]["novelty_band"] in ("known", "near_known", "novel_candidate")

    def test_get_novelty_not_found(self):
        client = self._client()
        r = client.get("/novelty/nonexistent")
        assert r.status_code == 404

    def test_post_novelty_check(self):
        client = self._client()
        r = client.post("/novelty/check", json={
            "formula": "UPu3", "elements": ["U", "Pu"],
            "spacegroup": 12})
        assert r.status_code == 200
        d = r.json()
        assert d["novelty"]["novelty_band"] == "novel_candidate"
        assert "disclaimer" in d

    def test_post_novelty_check_known(self):
        client = self._client()
        r = client.post("/novelty/check", json={
            "formula": "Fe2O3", "elements": ["Fe", "O"],
            "spacegroup": 167, "band_gap": 2.1,
            "formation_energy": -1.5})
        assert r.status_code == 200
        assert r.json()["novelty"]["novelty_band"] == "known"

    def test_get_exotic_candidates(self):
        client = self._client()
        r = client.get("/candidates/exotic?top_k=3")
        assert r.status_code == 200
        d = r.json()
        assert "candidates" in d
        assert len(d["candidates"]) <= 3
        assert "disclaimer" in d
        assert "scoring" in d

    def test_post_exotic_rank(self):
        client = self._client()
        r = client.post("/candidates/exotic/rank", json={"top_k": 2})
        assert r.status_code == 200
        d = r.json()
        assert len(d["candidates"]) <= 2

    def test_existing_endpoints_not_broken(self):
        """Verify all pre-existing endpoints still work."""
        client = self._client()
        assert client.get("/status").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/stats").status_code == 200
        assert client.get("/materials?limit=2").status_code == 200
        assert client.get("/search?formula=Fe2O3").status_code == 200
        assert client.get("/audit/summary").status_code == 200

    def test_status_version(self):
        client = self._client()
        d = client.get("/status").json()
        assert d["version"] == "1.2.1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
