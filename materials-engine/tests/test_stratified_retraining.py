"""Tests for Phase IV.M: Stratified/Curriculum Band Gap Retraining."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.stratified_retraining.spec import (
    ChallengerResult, ComparisonEntry, BucketComparison, PromotionDecision,
    StratifiedSample, DECISION_PROMOTE, DECISION_HOLD, DECISION_WATCHLIST,
)
from src.stratified_retraining.sampler import (
    RECIPES, STRATA_SQL, build_stratified_db,
)
from src.stratified_retraining.comparison import (
    build_comparison_table, build_bucket_comparison,
    make_promotion_decision, save_all_artifacts,
    PRODUCTION_BG, PRODUCTION_BUCKETS,
)


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   band_gap=None, source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, band_gap=band_gap,
                 has_valid_structure=True,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("Si", ["Si"], 227, 0.0, 0.0),          # metal
    _make_material("GaAs", ["As", "Ga"], 216, -0.7, 1.4),  # medium gap
    _make_material("NaCl", ["Cl", "Na"], 225, -4.2, 5.0),  # wide gap
    _make_material("Fe2O3", ["Fe", "O"], 167, -1.5, 2.1),  # medium gap
    _make_material("TiO2", ["O", "Ti"], 136, -3.4, 3.0),   # wide gap
    _make_material("LiMgAlSi", ["Al", "Li", "Mg", "Si"], 62, -0.5, 0.3),  # exotic
    _make_material("YBa2Cu3O7", ["Ba", "Cu", "O", "Y"], 47, -2.0, 0.0),   # exotic metal
    _make_material("HfZrTiNiSn", ["Hf", "Ni", "Sn", "Ti", "Zr"], 216, -0.3, 0.5),  # 5-elem
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


# ===== SPEC =====

class TestSpec:
    def test_stratified_sample(self):
        s = StratifiedSample(name="test", total_size=100,
                             strata={"random": 60, "hard": 40})
        json.dumps(s.to_dict())

    def test_challenger_result(self):
        c = ChallengerResult(name="c1", strategy="stratified", test_mae=0.3)
        d = c.to_dict()
        assert d["strategy"] == "stratified"
        json.dumps(d)

    def test_promotion_decision(self):
        d = PromotionDecision(decision=DECISION_HOLD)
        json.dumps(d.to_dict())


# ===== SAMPLER =====

class TestSampler:
    def test_recipes_defined(self):
        assert "bg_stratified_20k" in RECIPES
        assert "bg_curriculum_20k" in RECIPES
        assert "bg_stratified_balanced_30k" in RECIPES

    def test_strata_sql_defined(self):
        for key in ("random_representative", "hard_wide_gap", "sparse_exotic"):
            assert key in STRATA_SQL

    def test_stratified_20k_composition(self):
        r = RECIPES["bg_stratified_20k"]
        assert r["total"] == 20000
        assert r["strata"]["random_representative"] == 10000
        assert r["strata"]["hard_wide_gap"] == 6000
        assert r["strata"]["sparse_exotic"] == 4000

    def test_curriculum_has_finetune(self):
        r = RECIPES["bg_curriculum_20k"]
        assert "curriculum_finetune" in r
        assert "hard_wide_gap" in r["curriculum_finetune"]

    def test_build_stratified_db(self, test_db):
        """Build stratified DB from small test corpus."""
        path, sample = build_stratified_db(test_db, "bg_stratified_20k", seed=42)
        try:
            assert os.path.exists(path)
            assert sample.total_size > 0
            assert sample.name == "bg_stratified_20k"
            db2 = MaterialsDB(path)
            assert db2.count() == sample.total_size
        finally:
            os.unlink(path)


# ===== COMPARISON =====

class TestComparison:
    def _challengers(self):
        return [
            ChallengerResult(name="strat", strategy="stratified",
                             test_mae=0.33, test_rmse=0.70, test_r2=0.72,
                             dataset_size=20000, training_time_sec=2000),
            ChallengerResult(name="curr", strategy="curriculum",
                             test_mae=0.35, test_rmse=0.73, test_r2=0.70,
                             dataset_size=20000, training_time_sec=1500),
        ]

    def test_comparison_table(self):
        table = build_comparison_table(self._challengers())
        assert len(table) == 3
        assert table[0].role == "production"

    def test_comparison_deltas(self):
        table = build_comparison_table(self._challengers())
        for e in table:
            if e.role == "challenger":
                assert abs(e.mae_delta - (e.test_mae - PRODUCTION_BG["test_mae"])) < 0.001

    def test_bucket_comparison(self):
        buckets = build_bucket_comparison(self._challengers())
        assert len(buckets) == len(PRODUCTION_BUCKETS)

    def test_promote_when_better(self):
        challengers = [ChallengerResult(name="good", strategy="stratified",
                                        test_mae=0.30, test_rmse=0.65, test_r2=0.75,
                                        dataset_size=20000, training_time_sec=2000)]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        dec = make_promotion_decision(challengers, comp, buckets)
        assert dec.decision == DECISION_PROMOTE
        assert dec.promoted_model == "good"

    def test_hold_when_worse(self):
        challengers = [ChallengerResult(name="bad", strategy="stratified",
                                        test_mae=0.50, test_rmse=0.90, test_r2=0.50,
                                        dataset_size=20000, training_time_sec=2000)]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        dec = make_promotion_decision(challengers, comp, buckets)
        assert dec.decision == DECISION_HOLD

    def test_watchlist_marginal(self):
        challengers = [ChallengerResult(name="meh", strategy="stratified",
                                        test_mae=0.340, test_rmse=0.73, test_r2=0.71,
                                        dataset_size=20000, training_time_sec=2000)]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        dec = make_promotion_decision(challengers, comp, buckets)
        assert dec.decision in (DECISION_HOLD, DECISION_WATCHLIST)

    def test_decision_has_lessons(self):
        challengers = [ChallengerResult(name="test", strategy="stratified",
                                        test_mae=0.35, test_rmse=0.73, test_r2=0.70,
                                        dataset_size=20000, training_time_sec=2000)]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        dec = make_promotion_decision(challengers, comp, buckets)
        assert len(dec.lessons) > 0


# ===== ARTIFACTS =====

class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        challengers = [ChallengerResult(name="c1", strategy="stratified",
                                        test_mae=0.33, test_rmse=0.70, test_r2=0.72,
                                        dataset_size=20000, architecture="alignn_lite",
                                        training_time_sec=2000)]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        dec = make_promotion_decision(challengers, comp, buckets)
        save_all_artifacts(challengers, comp, buckets, dec, output_dir=td)
        for f in ("comparison_table.json", "comparison_table.md",
                  "bucket_comparison.json", "bucket_comparison.md",
                  "promotion_decision.json", "promotion_decision.md"):
            assert os.path.exists(os.path.join(td, f))
        assert os.path.exists(os.path.join(td, "challenger_c1", "result.json"))


# ===== API =====

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        m = _make_material("Si", ["Si"], 227, 0.0, 1.1)
        srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_status(self):
        r = self._client().get("/stratified-retraining/band-gap/status")
        assert r.status_code == 200
        assert r.json()["phase"] == "IV.M"

    def test_challengers(self):
        r = self._client().get("/stratified-retraining/band-gap/challengers")
        assert r.status_code == 200

    def test_comparison(self):
        r = self._client().get("/stratified-retraining/band-gap/comparison")
        assert r.status_code == 200

    def test_decision(self):
        r = self._client().get("/stratified-retraining/band-gap/decision")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/selective-retraining/band-gap/status").status_code == 200
        assert c.get("/retraining-prep/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.8.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
