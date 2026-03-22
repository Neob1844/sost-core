"""Tests for Phase IV.L: Selective Band Gap Retraining + Promotion Decision."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.selective_retraining.spec import (
    ChallengerResult, ComparisonEntry, BucketComparison, PromotionDecision,
    DECISION_PROMOTE, DECISION_HOLD, DECISION_WATCHLIST,
)
from src.selective_retraining.comparison import (
    build_comparison_table, build_bucket_comparison,
    make_promotion_decision, save_all_artifacts,
    PRODUCTION_BG, PRODUCTION_BUCKETS,
)
from src.selective_retraining.trainer import CHALLENGER_DATASETS


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   band_gap=None, source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, band_gap=band_gap,
                 has_valid_structure=True,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


# ===== SPEC =====

class TestSpec:
    def test_challenger_result(self):
        c = ChallengerResult(name="test", test_mae=0.3, test_r2=0.8)
        d = c.to_dict()
        assert d["name"] == "test"
        json.dumps(d)

    def test_comparison_entry(self):
        e = ComparisonEntry(name="prod", role="production", test_mae=0.34)
        json.dumps(e.to_dict())

    def test_bucket_comparison(self):
        b = BucketComparison(bucket_label="1.0-3.0", production_mae=0.87)
        json.dumps(b.to_dict())

    def test_promotion_decision(self):
        d = PromotionDecision(decision=DECISION_HOLD, rationale="test")
        json.dumps(d.to_dict())

    def test_decision_constants(self):
        assert DECISION_PROMOTE == "promote"
        assert DECISION_HOLD == "hold"
        assert DECISION_WATCHLIST == "watchlist"


# ===== COMPARISON =====

class TestComparison:
    def _challengers(self):
        return [
            ChallengerResult(name="c1", test_mae=0.33, test_rmse=0.70, test_r2=0.72,
                             dataset_name="ds1", dataset_size=10000, training_time_sec=100),
            ChallengerResult(name="c2", test_mae=0.35, test_rmse=0.75, test_r2=0.68,
                             dataset_name="ds2", dataset_size=5000, training_time_sec=50),
            ChallengerResult(name="c3", test_mae=0.30, test_rmse=0.65, test_r2=0.75,
                             dataset_name="ds3", dataset_size=20000, training_time_sec=200),
        ]

    def test_comparison_table(self):
        table = build_comparison_table(self._challengers())
        assert len(table) == 4  # 1 production + 3 challengers
        assert table[0].role == "production"
        assert table[0].test_mae == PRODUCTION_BG["test_mae"]

    def test_comparison_deltas(self):
        table = build_comparison_table(self._challengers())
        for entry in table:
            if entry.role == "challenger":
                expected_delta = entry.test_mae - PRODUCTION_BG["test_mae"]
                assert abs(entry.mae_delta - expected_delta) < 0.001

    def test_bucket_comparison(self):
        buckets = build_bucket_comparison(self._challengers())
        assert len(buckets) == len(PRODUCTION_BUCKETS)
        for b in buckets:
            assert b.bucket_type == "value_range"
            assert b.production_mae > 0

    def test_promotion_hold_when_worse(self):
        """If all challengers are worse, decision should be HOLD."""
        challengers = [
            ChallengerResult(name="bad", test_mae=0.5, test_rmse=0.9, test_r2=0.5,
                             dataset_name="ds", dataset_size=1000, training_time_sec=10),
        ]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        decision = make_promotion_decision(challengers, comp, buckets)
        assert decision.decision == DECISION_HOLD
        assert decision.promoted_model is None

    def test_promotion_promote_when_better(self):
        """If a challenger clearly improves, promote."""
        challengers = [
            ChallengerResult(name="good", test_mae=0.30, test_rmse=0.65, test_r2=0.75,
                             dataset_name="ds", dataset_size=20000, training_time_sec=200),
        ]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        decision = make_promotion_decision(challengers, comp, buckets)
        assert decision.decision == DECISION_PROMOTE
        assert decision.promoted_model == "good"
        assert decision.mae_improvement > 0

    def test_promotion_watchlist(self):
        """Marginal improvement → watchlist."""
        challengers = [
            ChallengerResult(name="marginal", test_mae=0.3400, test_rmse=0.73, test_r2=0.70,
                             dataset_name="ds", dataset_size=10000, training_time_sec=100),
        ]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        decision = make_promotion_decision(challengers, comp, buckets)
        # 0.3422 - 0.3400 = 0.0022 < MIN_MAE_IMPROVEMENT (0.01)
        assert decision.decision in (DECISION_HOLD, DECISION_WATCHLIST)

    def test_no_valid_challengers(self):
        """No valid challengers → HOLD."""
        challengers = [
            ChallengerResult(name="failed", test_mae=0.0),
        ]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        decision = make_promotion_decision(challengers, comp, buckets)
        assert decision.decision == DECISION_HOLD


# ===== ARTIFACTS =====

class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        challengers = [
            ChallengerResult(name="c1", test_mae=0.33, test_rmse=0.70, test_r2=0.72,
                             dataset_name="ds1", dataset_size=10000, training_time_sec=100,
                             architecture="alignn_lite"),
        ]
        comp = build_comparison_table(challengers)
        buckets = build_bucket_comparison(challengers)
        decision = make_promotion_decision(challengers, comp, buckets)
        save_all_artifacts(challengers, comp, buckets, decision, output_dir=td)

        assert os.path.exists(os.path.join(td, "comparison_table.json"))
        assert os.path.exists(os.path.join(td, "comparison_table.md"))
        assert os.path.exists(os.path.join(td, "bucket_comparison.json"))
        assert os.path.exists(os.path.join(td, "bucket_comparison.md"))
        assert os.path.exists(os.path.join(td, "promotion_decision.json"))
        assert os.path.exists(os.path.join(td, "promotion_decision.md"))
        assert os.path.exists(os.path.join(td, "challenger_c1", "result.json"))
        assert os.path.exists(os.path.join(td, "challenger_c1", "result.md"))


# ===== TRAINER DEFS =====

class TestTrainerDefs:
    def test_challenger_datasets_defined(self):
        assert "bg_hotspots_10k" in CHALLENGER_DATASETS
        assert "bg_sparse_exotic_10k" in CHALLENGER_DATASETS
        assert "bg_balanced_hardmix_20k" in CHALLENGER_DATASETS

    def test_datasets_have_sql(self):
        for name, ds in CHALLENGER_DATASETS.items():
            assert "sql" in ds
            assert "band_gap" in ds["sql"]
            assert ds["limit"] > 0


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
        r = self._client().get("/selective-retraining/band-gap/status")
        assert r.status_code == 200
        assert r.json()["target"] == "band_gap"

    def test_challengers(self):
        r = self._client().get("/selective-retraining/band-gap/challengers")
        assert r.status_code == 200
        assert "challengers" in r.json()

    def test_comparison(self):
        r = self._client().get("/selective-retraining/band-gap/comparison")
        assert r.status_code == 200

    def test_decision(self):
        r = self._client().get("/selective-retraining/band-gap/decision")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200
        assert c.get("/retraining-prep/status").status_code == 200
        assert c.get("/orchestrator/status").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "3.2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
