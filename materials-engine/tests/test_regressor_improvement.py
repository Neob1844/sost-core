"""Tests for Phase IV.P: Non-Metal Regressor Improvement."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.hierarchical_bandgap.regressor_tuning import CHALLENGERS
from src.hierarchical_bandgap.nonmetal_comparison import (
    compute_pipeline_mae, build_comparison, make_promotion_decision,
    save_all_artifacts, PRODUCTION, REGRESSOR_V1, GATE, PROD_BUCKETS,
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


# ===== SPEC =====

class TestSpec:
    def test_challengers_defined(self):
        assert "nonmetal_longer_train" in CHALLENGERS
        assert "nonmetal_lower_lr" in CHALLENGERS
        assert "nonmetal_longer_lower_lr" in CHALLENGERS

    def test_challengers_have_config(self):
        for name, cfg in CHALLENGERS.items():
            assert "arch" in cfg
            assert "epochs" in cfg
            assert "lr" in cfg
            assert cfg["epochs"] > 0
            assert cfg["lr"] > 0

    def test_references(self):
        assert PRODUCTION["test_mae"] == 0.3422
        assert REGRESSOR_V1["test_mae"] == 0.7609
        assert GATE["accuracy"] == 0.908


# ===== PIPELINE COMPUTATION =====

class TestPipeline:
    def test_compute_pipeline_mae(self):
        result = compute_pipeline_mae(0.5, {"0.05-1.0": 0.35, "1.0-3.0": 0.55})
        assert result["pipeline_mae"] > 0
        assert "bucket_mae" in result
        assert "0.0-0.05" in result["bucket_mae"]

    def test_lower_regressor_lower_pipeline(self):
        r1 = compute_pipeline_mae(0.76, {})
        r2 = compute_pipeline_mae(0.50, {})
        assert r2["pipeline_mae"] < r1["pipeline_mae"]

    def test_pipeline_serializable(self):
        result = compute_pipeline_mae(0.5, {})
        json.dumps(result)


# ===== COMPARISON =====

class TestComparison:
    def _challengers(self):
        return [
            {"name": "c1", "test_mae": 0.60, "test_rmse": 0.85, "test_r2": 0.72,
             "epochs": 25, "lr": 0.005, "bucket_mae": {"0.05-1.0": 0.40}, "training_time_sec": 2000},
            {"name": "c2", "test_mae": 0.50, "test_rmse": 0.75, "test_r2": 0.80,
             "epochs": 30, "lr": 0.002, "bucket_mae": {"0.05-1.0": 0.35, "1.0-3.0": 0.55}, "training_time_sec": 3000},
        ]

    def test_build_comparison(self):
        comp = build_comparison(self._challengers())
        assert len(comp["entries"]) == 4  # production + v1 + 2 challengers

    def test_production_first(self):
        comp = build_comparison(self._challengers())
        assert comp["entries"][0]["role"] == "production"

    def test_promotion_improve(self):
        challengers = [
            {"name": "good", "test_mae": 0.40, "test_rmse": 0.60, "test_r2": 0.85,
             "epochs": 30, "lr": 0.002,
             "bucket_mae": {"0.05-1.0": 0.30, "1.0-3.0": 0.45, "3.0-6.0": 0.50},
             "training_time_sec": 3000},
        ]
        comp = build_comparison(challengers)
        dec = make_promotion_decision(challengers, comp)
        # With regressor MAE=0.40 and bucket MAE 0.30 for narrow-gap,
        # pipeline should be well below production
        assert dec["decision"] in ("promote", "watchlist")
        assert dec["mae_improvement"] > 0

    def test_promotion_hold_when_worse(self):
        challengers = [
            {"name": "bad", "test_mae": 0.90, "test_rmse": 1.2, "test_r2": 0.40,
             "epochs": 10, "lr": 0.01, "bucket_mae": {}, "training_time_sec": 500},
        ]
        comp = build_comparison(challengers)
        dec = make_promotion_decision(challengers, comp)
        assert dec["decision"] in ("hold", "watchlist")  # worse regressor still has gate benefit

    def test_decision_serializable(self):
        comp = build_comparison(self._challengers())
        dec = make_promotion_decision(self._challengers(), comp)
        json.dumps(dec)


# ===== ARTIFACTS =====

class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        challengers = [
            {"name": "c1", "test_mae": 0.55, "test_rmse": 0.80, "test_r2": 0.75,
             "epochs": 25, "lr": 0.005, "bucket_mae": {"0.05-1.0": 0.40},
             "training_time_sec": 2000},
        ]
        comp = build_comparison(challengers)
        dec = make_promotion_decision(challengers, comp)
        save_all_artifacts(challengers, comp, dec, output_dir=td)
        for f in ("nonmetal_comparison.json", "nonmetal_comparison.md",
                  "pipeline_comparison.json", "pipeline_comparison.md",
                  "bucket_comparison.json", "bucket_comparison.md",
                  "promotion_decision.json", "promotion_decision.md"):
            assert os.path.exists(os.path.join(td, f)), f"Missing: {f}"


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
        r = self._client().get("/hierarchical-band-gap-regressor/status")
        assert r.status_code == 200
        assert r.json()["phase"] == "IV.P"

    def test_challengers(self):
        assert self._client().get("/hierarchical-band-gap-regressor/challengers").status_code == 200

    def test_comparison(self):
        assert self._client().get("/hierarchical-band-gap-regressor/comparison").status_code == 200

    def test_decision(self):
        assert self._client().get("/hierarchical-band-gap-regressor/decision").status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/hierarchical-band-gap-calibration/status").status_code == 200
        assert c.get("/hierarchical-band-gap/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "3.0.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
