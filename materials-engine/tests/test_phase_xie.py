#!/usr/bin/env python3
"""Phase XI.E Tests — Validation economics, evidence gain, redundancy."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.validation_economics import compute_validation_value, select_validation_batch
from autonomous_discovery.policy import get_profile


class TestEvidenceGain(unittest.TestCase):

    def test_novel_gnn_high_gain(self):
        scores = {"composite_score": 0.7}
        unc = {"confidence_score": 0.6, "out_of_domain_risk": 0.2}
        ready = {"validation_readiness_score": 0.6}
        ctx = {"prediction_origin": "direct_gnn_lifted", "is_known_material": False,
               "risk_level": "plausible", "formula": "AlGaAs"}
        v = compute_validation_value(scores, unc, ready, ctx)
        self.assertGreater(v["evidence_gain"], 0.40)

    def test_known_material_low_gain(self):
        scores = {"composite_score": 0.8}
        unc = {"confidence_score": 0.9, "out_of_domain_risk": 0.05}
        ready = {"validation_readiness_score": 0.9}
        ctx = {"is_known_material": True, "prediction_origin": "known_exact", "formula": "GaAs"}
        v = compute_validation_value(scores, unc, ready, ctx)
        self.assertLess(v["evidence_gain"], 0.20)


class TestRedundancy(unittest.TestCase):

    def test_duplicate_full_penalty(self):
        ctx = {"formula": "GaAs"}
        v = compute_validation_value({}, {}, {}, ctx, queued_formulas={"GaAs"})
        self.assertEqual(v["redundancy_penalty"], 1.0)

    def test_similar_partial_penalty(self):
        ctx = {"formula": "GaAlAs"}
        v = compute_validation_value({}, {}, {}, ctx, queued_formulas={"GaAs"})
        self.assertGreater(v["redundancy_penalty"], 0)

    def test_unrelated_no_penalty(self):
        ctx = {"formula": "TiO2"}
        v = compute_validation_value({}, {}, {}, ctx, queued_formulas={"LiCoO2"})
        self.assertEqual(v["redundancy_penalty"], 0.0)


class TestCostProxy(unittest.TestCase):

    def test_simple_lower_cost(self):
        ctx = {"formula": "ZnO", "has_structure_lift": True, "risk_level": "familiar"}
        v = compute_validation_value({}, {}, {}, ctx)
        cost_simple = v["validation_cost_proxy"]

        ctx2 = {"formula": "BaCdTiZnO4", "has_structure_lift": False, "risk_level": "risky"}
        v2 = compute_validation_value({}, {}, {}, ctx2)
        self.assertLess(cost_simple, v2["validation_cost_proxy"])


class TestROI(unittest.TestCase):

    def test_high_gain_low_cost_high_roi(self):
        scores = {"composite_score": 0.7}
        unc = {"confidence_score": 0.6, "out_of_domain_risk": 0.3}
        ready = {"validation_readiness_score": 0.7}
        ctx = {"formula": "CdInTe", "prediction_origin": "direct_gnn_lifted",
               "is_known_material": False, "has_structure_lift": True, "risk_level": "familiar"}
        v = compute_validation_value(scores, unc, ready, ctx)
        self.assertGreater(v["validation_roi"], 0.3)

    def test_redundant_low_roi(self):
        scores = {"composite_score": 0.7}
        unc = {"confidence_score": 0.6, "out_of_domain_risk": 0.2}
        ready = {"validation_readiness_score": 0.6}
        ctx = {"formula": "GaAs", "prediction_origin": "direct_gnn_lifted",
               "is_known_material": False, "has_structure_lift": True}
        v = compute_validation_value(scores, unc, ready, ctx, queued_formulas={"GaAs"})
        # ROI should be lower than without redundancy, but exact value depends on formula
        v_no_dup = compute_validation_value(scores, unc, ready, ctx, queued_formulas=set())
        self.assertLess(v["validation_roi"], v_no_dup["validation_roi"])


class TestBatchSelection(unittest.TestCase):

    def test_dedup_in_batch(self):
        candidates = [
            {"formula": "A", "validation_value": {"validation_roi": 0.9}, "chemistry": {"family": "F1"}},
            {"formula": "A", "validation_value": {"validation_roi": 0.8}, "chemistry": {"family": "F1"}},
            {"formula": "B", "validation_value": {"validation_roi": 0.7}, "chemistry": {"family": "F2"}},
        ]
        batch = select_validation_batch(candidates, max_batch=5)
        formulas = [c["formula"] for c in batch]
        self.assertEqual(formulas.count("A"), 1)

    def test_family_quota(self):
        candidates = [
            {"formula": f"X{i}", "validation_value": {"validation_roi": 0.9 - i*0.01},
             "chemistry": {"family": "same_family"}, "candidate_context": {"family": "same_family"}}
            for i in range(6)
        ]
        batch = select_validation_batch(candidates, max_batch=10)
        self.assertLessEqual(len(batch), 3)

    def test_respects_max_batch(self):
        candidates = [{"formula": f"M{i}", "validation_value": {"validation_roi": 0.5},
                        "chemistry": {"family": f"F{i}"}} for i in range(20)]
        batch = select_validation_batch(candidates, max_batch=5)
        self.assertEqual(len(batch), 5)


class TestProfile(unittest.TestCase):

    def test_validation_economics_exists(self):
        p = get_profile("validation_economics")
        self.assertTrue(p.get("optimize_validation_roi", False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
