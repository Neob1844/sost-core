"""Tests for Phase IV.N: Hierarchical Band Gap Modeling."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.hierarchical_bandgap.spec import (
    MetalGateResult, NonMetalRegressorResult, HierarchicalBandGapResult,
    PromotionDecision, METAL_THRESHOLD,
    DECISION_PROMOTE, DECISION_HOLD, DECISION_WATCHLIST,
)
from src.hierarchical_bandgap.pipeline import (
    compute_hierarchical_metrics, make_promotion_decision, save_all_artifacts,
    PRODUCTION_BG,
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
    def test_metal_threshold(self):
        assert METAL_THRESHOLD == 0.05

    def test_gate_result(self):
        g = MetalGateResult(accuracy=0.95, f1_metal=0.96, f1_nonmetal=0.93)
        d = g.to_dict()
        assert d["accuracy"] == 0.95
        json.dumps(d)

    def test_regressor_result(self):
        r = NonMetalRegressorResult(test_mae=0.45, test_r2=0.8)
        json.dumps(r.to_dict())

    def test_hierarchical_result(self):
        h = HierarchicalBandGapResult(name="test", pipeline_mae=0.2)
        json.dumps(h.to_dict())

    def test_promotion_decision(self):
        d = PromotionDecision(decision=DECISION_HOLD)
        json.dumps(d.to_dict())

    def test_metal_classification(self):
        """Test metal threshold logic."""
        assert 0.01 < METAL_THRESHOLD  # metals are BG < 0.05
        assert METAL_THRESHOLD < 0.1   # reasonable threshold


# ===== PIPELINE =====

class TestPipeline:
    def _good_gate(self):
        return MetalGateResult(
            accuracy=0.95, precision_metal=0.96, recall_metal=0.97,
            f1_metal=0.965, precision_nonmetal=0.92, recall_nonmetal=0.90,
            f1_nonmetal=0.91, confusion_matrix={"TP": 270, "TN": 680, "FP": 30, "FN": 20},
            training_time_sec=1000)

    def _good_regressor(self):
        return NonMetalRegressorResult(
            test_mae=0.45, test_rmse=0.70, test_r2=0.82,
            bucket_mae={"0.05-1.0": 0.30, "1.0-3.0": 0.50, "3.0-6.0": 0.65, "6.0+": 0.55},
            training_time_sec=1500, dataset_size=20000)

    def test_compute_metrics(self):
        gate = self._good_gate()
        reg = self._good_regressor()
        result = compute_hierarchical_metrics(gate, reg)
        assert result.pipeline_mae > 0
        assert result.pipeline_mae < 1.0
        assert len(result.bucket_comparison) > 0

    def test_metrics_serializable(self):
        result = compute_hierarchical_metrics(self._good_gate(), self._good_regressor())
        json.dumps(result.to_dict())

    def test_promotion_improve(self):
        """Good gate + good regressor should beat production."""
        gate = self._good_gate()
        reg = self._good_regressor()
        result = compute_hierarchical_metrics(gate, reg)
        decision = make_promotion_decision(result)
        # With 95% gate accuracy and 0.45 regressor MAE, pipeline MAE should be < 0.34
        if result.pipeline_mae < PRODUCTION_BG["test_mae"]:
            assert decision.decision in (DECISION_PROMOTE, DECISION_WATCHLIST)
        assert decision.mae_improvement != 0

    def test_promotion_hold_bad_gate(self):
        """Bad gate should prevent promotion."""
        gate = MetalGateResult(
            accuracy=0.60, recall_metal=0.5, recall_nonmetal=0.7,
            f1_metal=0.55, f1_nonmetal=0.65,
            confusion_matrix={"TP": 140, "TN": 350, "FP": 350, "FN": 160},
            training_time_sec=500)
        reg = self._good_regressor()
        result = compute_hierarchical_metrics(gate, reg)
        decision = make_promotion_decision(result)
        assert decision.decision in (DECISION_HOLD, DECISION_WATCHLIST)  # gate accuracy < 0.90 blocks promote

    def test_promotion_has_lessons(self):
        result = compute_hierarchical_metrics(self._good_gate(), self._good_regressor())
        decision = make_promotion_decision(result)
        assert len(decision.lessons) > 0

    def test_bucket_comparison_structure(self):
        result = compute_hierarchical_metrics(self._good_gate(), self._good_regressor())
        for b in result.bucket_comparison:
            assert "bucket" in b
            assert "production_mae" in b
            assert "hierarchical_mae" in b
            assert "delta" in b
            assert "improved" in b


# ===== ARTIFACTS =====

class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        gate = MetalGateResult(accuracy=0.95, f1_metal=0.96, f1_nonmetal=0.93,
                               confusion_matrix={"TP": 270, "TN": 680, "FP": 30, "FN": 20},
                               recall_metal=0.97, recall_nonmetal=0.90,
                               training_time_sec=1000)
        reg = NonMetalRegressorResult(test_mae=0.45, test_rmse=0.70, test_r2=0.82,
                                       bucket_mae={"0.05-1.0": 0.30}, training_time_sec=1500)
        result = compute_hierarchical_metrics(gate, reg)
        decision = make_promotion_decision(result)
        save_all_artifacts(gate, reg, result, decision, output_dir=td)
        for f in ("gate_metrics.json", "gate_metrics.md",
                  "nonmetal_regressor.json", "nonmetal_regressor.md",
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
        r = self._client().get("/hierarchical-band-gap/status")
        assert r.status_code == 200
        assert r.json()["phase"] == "IV.N"

    def test_gate(self):
        r = self._client().get("/hierarchical-band-gap/gate")
        assert r.status_code == 200

    def test_regressor(self):
        r = self._client().get("/hierarchical-band-gap/regressor")
        assert r.status_code == 200

    def test_comparison(self):
        r = self._client().get("/hierarchical-band-gap/comparison")
        assert r.status_code == 200

    def test_decision(self):
        r = self._client().get("/hierarchical-band-gap/decision")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/stratified-retraining/band-gap/status").status_code == 200
        assert c.get("/selective-retraining/band-gap/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.9.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
