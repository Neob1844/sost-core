"""Tests for Phase IV.O: Gate Calibration + Borderline Routing."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.hierarchical_bandgap.calibration import (
    GateThresholdResult, RoutingPolicyResult, CalibratedPipelineResult,
    PromotionDecision, sweep_thresholds, evaluate_routing_policy,
    save_all_artifacts, POLICY_ORIGINAL, POLICY_CONSERVATIVE,
    POLICY_BORDERLINE_TO_REG, POLICY_THREE_ZONE,
    PRODUCTION_BG, PROD_BUCKETS,
)


def _make_test_set():
    """Create a synthetic test set for calibration tests."""
    samples = []
    # 70 metals (BG < 0.05, sigmoid should be low)
    for i in range(70):
        samples.append({"formula": f"Metal{i}", "band_gap": 0.001 * i,
                         "is_metal": True, "sigmoid": 0.1 + 0.003 * i})
    # 10 narrow-gap nonmetals (BG 0.05-1.0, sigmoid borderline)
    for i in range(10):
        samples.append({"formula": f"NarrowGap{i}", "band_gap": 0.1 + 0.08 * i,
                         "is_metal": False, "sigmoid": 0.35 + 0.03 * i})
    # 15 medium-gap (BG 1-3, sigmoid high)
    for i in range(15):
        samples.append({"formula": f"MedGap{i}", "band_gap": 1.0 + 0.13 * i,
                         "is_metal": False, "sigmoid": 0.7 + 0.01 * i})
    # 5 wide-gap (BG 3-6, sigmoid very high)
    for i in range(5):
        samples.append({"formula": f"WideGap{i}", "band_gap": 3.0 + 0.5 * i,
                         "is_metal": False, "sigmoid": 0.85 + 0.02 * i})
    return samples


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
    def test_threshold_result(self):
        r = GateThresholdResult(sigmoid_threshold=0.4, accuracy=0.92)
        json.dumps(r.to_dict())

    def test_routing_result(self):
        r = RoutingPolicyResult(policy="test", pipeline_mae=0.25)
        json.dumps(r.to_dict())

    def test_calibrated_result(self):
        r = CalibratedPipelineResult()
        json.dumps(r.to_dict())

    def test_promotion_decision(self):
        d = PromotionDecision(decision="hold")
        json.dumps(d.to_dict())


# ===== THRESHOLD SWEEP =====

class TestThresholdSweep:
    def test_sweep(self):
        test_set = _make_test_set()
        results = sweep_thresholds(test_set, [0.3, 0.5, 0.7])
        assert len(results) == 3
        for r in results:
            assert 0 <= r.accuracy <= 1
            assert r.tp + r.tn + r.fp + r.fn == len(test_set)

    def test_lower_threshold_more_fn(self):
        """Higher threshold → more materials classified as metal → more FN."""
        test_set = _make_test_set()
        results = sweep_thresholds(test_set, [0.3, 0.7])
        # At threshold 0.7, more nonmetals will be misclassified as metal
        assert results[1].fn >= results[0].fn

    def test_sweep_serializable(self):
        results = sweep_thresholds(_make_test_set(), [0.5])
        json.dumps([r.to_dict() for r in results])

    def test_fn_narrow_tracked(self):
        test_set = _make_test_set()
        results = sweep_thresholds(test_set, [0.7])  # high threshold catches narrow-gap as metal
        assert results[0].fn_narrow_gap >= 0


# ===== ROUTING POLICIES =====

class TestRoutingPolicies:
    def test_original(self):
        test_set = _make_test_set()
        r = evaluate_routing_policy(test_set, POLICY_ORIGINAL, regressor_mae=0.5)
        assert r.pipeline_mae > 0
        assert r.total_samples == len(test_set)

    def test_conservative(self):
        test_set = _make_test_set()
        r = evaluate_routing_policy(test_set, POLICY_CONSERVATIVE, regressor_mae=0.5,
                                     borderline_low=0.3)
        assert r.pipeline_mae > 0

    def test_borderline_to_regressor(self):
        test_set = _make_test_set()
        r = evaluate_routing_policy(test_set, POLICY_BORDERLINE_TO_REG, regressor_mae=0.5,
                                     borderline_low=0.25)
        assert r.fn_count == 0 or r.fn_count < 30  # should reduce FN

    def test_three_zone(self):
        test_set = _make_test_set()
        r = evaluate_routing_policy(test_set, POLICY_THREE_ZONE, regressor_mae=0.5,
                                     borderline_low=0.3, borderline_high=0.7)
        assert r.pipeline_mae > 0
        assert len(r.bucket_mae) > 0

    def test_lower_borderline_fewer_fn(self):
        """Lower borderline_low → more sent to regressor → fewer FN."""
        test_set = _make_test_set()
        r_high = evaluate_routing_policy(test_set, POLICY_BORDERLINE_TO_REG,
                                          regressor_mae=0.5, borderline_low=0.5)
        r_low = evaluate_routing_policy(test_set, POLICY_BORDERLINE_TO_REG,
                                         regressor_mae=0.5, borderline_low=0.2)
        assert r_low.fn_count <= r_high.fn_count

    def test_policy_serializable(self):
        r = evaluate_routing_policy(_make_test_set(), POLICY_ORIGINAL, 0.5)
        json.dumps(r.to_dict())


# ===== ARTIFACTS =====

class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        test_set = _make_test_set()
        sweep = sweep_thresholds(test_set, [0.3, 0.5])
        policies = [
            evaluate_routing_policy(test_set, POLICY_ORIGINAL, 0.5),
            evaluate_routing_policy(test_set, POLICY_BORDERLINE_TO_REG, 0.5, borderline_low=0.3),
        ]
        best = min(policies, key=lambda p: p.pipeline_mae)
        comparison = CalibratedPipelineResult(
            production=PRODUCTION_BG,
            best_calibrated=best.to_dict(),
            all_policies=[p.to_dict() for p in policies],
            threshold_sweep=[s.to_dict() for s in sweep])
        decision = PromotionDecision(decision="hold", rationale="test",
                                      best_calibrated_mae=best.pipeline_mae)
        save_all_artifacts(sweep, policies, comparison, decision, output_dir=td)
        for f in ("threshold_sweep.json", "threshold_sweep.md",
                  "routing_comparison.json", "routing_comparison.md",
                  "pipeline_comparison.json", "pipeline_comparison.md",
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
        r = self._client().get("/hierarchical-band-gap-calibration/status")
        assert r.status_code == 200
        assert r.json()["phase"] == "IV.O"

    def test_thresholds(self):
        assert self._client().get("/hierarchical-band-gap-calibration/thresholds").status_code == 200

    def test_routing(self):
        assert self._client().get("/hierarchical-band-gap-calibration/routing").status_code == 200

    def test_comparison(self):
        assert self._client().get("/hierarchical-band-gap-calibration/comparison").status_code == 200

    def test_decision(self):
        assert self._client().get("/hierarchical-band-gap-calibration/decision").status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/hierarchical-band-gap/status").status_code == 200
        assert c.get("/stratified-retraining/band-gap/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.8.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
