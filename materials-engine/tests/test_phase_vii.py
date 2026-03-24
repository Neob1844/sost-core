#!/usr/bin/env python3
"""Phase VII Tests — Uncertainty, validation readiness, DFT handoff, diversity."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.uncertainty import (
    compute_uncertainty, compute_validation_readiness,
    generate_handoff_pack, apply_diversity_constraint
)
from autonomous_discovery.policy import get_profile


class TestUncertaintyScoring(unittest.TestCase):

    def test_known_material_low_uncertainty(self):
        ctx = {"is_known_material": True, "prediction_origin": "known_exact",
               "has_structure_lift": True, "has_direct_gnn_fe": True, "gnn_confidence": "high"}
        scores = {"plausibility": 0.8, "family_bonus": 0.15}
        r = compute_uncertainty(ctx, scores, "element_substitution", 2, [{"formula": "GaAs"}])
        self.assertLess(r["uncertainty_score"], 0.15)
        self.assertEqual(r["support_strength"], "strong")

    def test_proxy_only_high_uncertainty(self):
        ctx = {"is_known_material": False, "prediction_origin": "proxy_only",
               "has_structure_lift": False, "has_direct_gnn_fe": False, "gnn_confidence": "none"}
        scores = {"plausibility": 0.5, "family_bonus": 0}
        r = compute_uncertainty(ctx, scores, "mixed_parent", 4, [])
        self.assertGreater(r["uncertainty_score"], 0.60)
        self.assertIn(r["support_strength"], ("weak", "none"))

    def test_direct_gnn_moderate_uncertainty(self):
        ctx = {"is_known_material": False, "prediction_origin": "direct_gnn_lifted",
               "has_structure_lift": True, "has_direct_gnn_fe": True, "gnn_confidence": "medium"}
        scores = {"plausibility": 0.7, "family_bonus": 0.1}
        r = compute_uncertainty(ctx, scores, "element_substitution", 2, [{"formula": "InP"}])
        self.assertGreater(r["uncertainty_score"], 0.10)
        self.assertLess(r["uncertainty_score"], 0.50)
        self.assertIn(r["support_strength"], ("moderate", "strong"))

    def test_out_of_domain_risk_increases_with_complexity(self):
        ctx = {"is_known_material": False, "prediction_origin": "proxy_only",
               "has_structure_lift": False}
        scores = {"plausibility": 0.5}
        r2 = compute_uncertainty(ctx, scores, "element_substitution", 2)
        r5 = compute_uncertainty(ctx, scores, "mixed_parent", 5)
        self.assertGreater(r5["out_of_domain_risk"], r2["out_of_domain_risk"])

    def test_structure_reliability_hierarchy(self):
        base = {"is_known_material": False, "prediction_origin": "proxy_only",
                "has_direct_gnn_fe": False, "gnn_confidence": "none"}
        s = {"plausibility": 0.5}

        # No lift
        ctx1 = {**base, "has_structure_lift": False}
        r1 = compute_uncertainty(ctx1, s, "mixed_parent", 2)

        # With lift
        ctx2 = {**base, "has_structure_lift": True}
        r2 = compute_uncertainty(ctx2, s, "element_substitution", 2)

        # With lift + GNN
        ctx3 = {**base, "has_structure_lift": True, "has_direct_gnn_fe": True,
                "prediction_origin": "direct_gnn_lifted", "gnn_confidence": "medium"}
        r3 = compute_uncertainty(ctx3, s, "element_substitution", 2)

        self.assertLess(r1["structure_reliability"], r2["structure_reliability"])
        self.assertLess(r2["structure_reliability"], r3["structure_reliability"])

    def test_prediction_support_summary_readable(self):
        ctx = {"is_known_material": False, "prediction_origin": "direct_gnn_lifted",
               "has_structure_lift": True, "has_direct_gnn_fe": True, "gnn_confidence": "medium"}
        scores = {"plausibility": 0.7, "family_bonus": 0.15}
        r = compute_uncertainty(ctx, scores, "element_substitution", 2, [{"formula": "GaP"}])
        self.assertIn("direct GNN", r["prediction_support_summary"])
        self.assertIn("1 corpus neighbor", r["prediction_support_summary"])


class TestValidationReadiness(unittest.TestCase):

    def test_known_material_reference_only(self):
        unc = {"confidence_score": 0.95, "out_of_domain_risk": 0.0,
               "structure_reliability": 1.0, "support_strength": "strong"}
        scores = {"composite_score": 0.8, "plausibility": 0.9, "is_novel_direct_gnn": False}
        ctx = {"is_known_material": True}
        r = compute_validation_readiness(unc, scores, ctx)
        self.assertEqual(r["next_action"], "reference_only")
        self.assertFalse(r["dft_handoff_ready"])

    def test_dft_handoff_for_good_novel_candidate(self):
        unc = {"confidence_score": 0.65, "out_of_domain_risk": 0.15,
               "structure_reliability": 0.65, "support_strength": "moderate"}
        scores = {"composite_score": 0.7, "plausibility": 0.75, "is_novel_direct_gnn": True}
        ctx = {"is_known_material": False}
        r = compute_validation_readiness(unc, scores, ctx)
        self.assertTrue(r["dft_handoff_ready"])
        self.assertEqual(r["next_action"], "DFT_handoff_candidate")

    def test_low_confidence_not_handoff_ready(self):
        unc = {"confidence_score": 0.20, "out_of_domain_risk": 0.7,
               "structure_reliability": 0.10, "support_strength": "none"}
        scores = {"composite_score": 0.3, "plausibility": 0.3, "is_novel_direct_gnn": False}
        ctx = {"is_known_material": False}
        r = compute_validation_readiness(unc, scores, ctx)
        self.assertFalse(r["dft_handoff_ready"])
        self.assertIn(r["next_action"], ("deprioritize", "keep_watchlist"))

    def test_readiness_score_range(self):
        unc = {"confidence_score": 0.5, "out_of_domain_risk": 0.3,
               "structure_reliability": 0.5, "support_strength": "moderate"}
        scores = {"composite_score": 0.5, "plausibility": 0.6, "is_novel_direct_gnn": False}
        r = compute_validation_readiness(unc, scores)
        self.assertGreaterEqual(r["validation_readiness_score"], 0.0)
        self.assertLessEqual(r["validation_readiness_score"], 1.0)

    def test_handoff_value_higher_for_novel(self):
        unc = {"confidence_score": 0.6, "out_of_domain_risk": 0.2,
               "structure_reliability": 0.6, "support_strength": "moderate"}
        s1 = {"composite_score": 0.6, "plausibility": 0.7, "is_novel_direct_gnn": True}
        s2 = {"composite_score": 0.6, "plausibility": 0.7, "is_novel_direct_gnn": False}
        r1 = compute_validation_readiness(unc, s1, {"is_known_material": False})
        r2 = compute_validation_readiness(unc, s2, {"is_known_material": False})
        self.assertGreater(r1["handoff_value_score"], r2["handoff_value_score"])


class TestHandoffPack(unittest.TestCase):

    def test_handoff_pack_has_all_fields(self):
        candidate = {"formula": "AlGa", "method": "element_substitution",
                     "parent_a": "GaAs", "parent_b": "AlN",
                     "scores": {"composite_score": 0.7, "plausibility": 0.8, "prediction_origin": "direct_gnn_lifted"},
                     "ml_evaluation": {"nearest_neighbors": [{"formula": "GaAs", "formation_energy": -0.3}]},
                     "structure_lift": {"structure_lift_status": "lifted_ok"},
                     "gnn_combined": {"direct_fe_value": -0.379}}
        unc = {"uncertainty_score": 0.25, "confidence_score": 0.75,
               "out_of_domain_risk": 0.1, "support_strength": "moderate",
               "structure_reliability": 0.65, "prediction_support_summary": "test"}
        readiness = {"validation_readiness_score": 0.65, "dft_handoff_ready": True,
                     "next_action": "DFT_handoff_candidate", "handoff_value_score": 0.7}

        pack = generate_handoff_pack(candidate, unc, readiness)
        self.assertEqual(pack["candidate_formula"], "AlGa")
        self.assertEqual(pack["formation_energy_predicted"], -0.379)
        self.assertTrue(pack["dft_handoff_ready"])
        self.assertIn("disclaimer", pack)
        self.assertIn("THEORETICAL", pack["disclaimer"])
        self.assertIsInstance(pack["risk_flags"], list)

    def test_handoff_pack_risk_flags(self):
        candidate = {"formula": "X", "scores": {"plausibility": 0.2, "proxy_only_penalty": 0.1}}
        unc = {"uncertainty_score": 0.8, "out_of_domain_risk": 0.7,
               "structure_reliability": 0.1, "family_support_confidence": 0.1,
               "confidence_score": 0.2, "support_strength": "none",
               "prediction_support_summary": ""}
        readiness = {"validation_readiness_score": 0.1, "dft_handoff_ready": False,
                     "next_action": "deprioritize", "handoff_value_score": 0.05}
        pack = generate_handoff_pack(candidate, unc, readiness)
        self.assertIn("HIGH_OOD_RISK", pack["risk_flags"])
        self.assertIn("HIGH_UNCERTAINTY", pack["risk_flags"])
        self.assertIn("LOW_PLAUSIBILITY", pack["risk_flags"])


class TestDiversityConstraint(unittest.TestCase):

    def test_limits_same_family(self):
        candidates = [
            {"elements": ["Ga", "As"], "composite_score": 0.9},
            {"elements": ["Ga", "As"], "composite_score": 0.8},
            {"elements": ["Ga", "As"], "composite_score": 0.7},
            {"elements": ["Ga", "As"], "composite_score": 0.6},  # should be dropped
            {"elements": ["Ti", "O"], "composite_score": 0.5},
        ]
        selected = apply_diversity_constraint(candidates, max_per_family=3, top_k=10)
        ga_as = sum(1 for c in selected if sorted(c["elements"]) == ["As", "Ga"])
        self.assertEqual(ga_as, 3)
        self.assertEqual(len(selected), 4)  # 3 GaAs + 1 TiO

    def test_top_k_limit(self):
        candidates = [{"elements": [f"E{i}"], "composite_score": 1.0 - i*0.1} for i in range(20)]
        selected = apply_diversity_constraint(candidates, top_k=5)
        self.assertEqual(len(selected), 5)


class TestHighUncertaintyProbe(unittest.TestCase):

    def test_profile_exists(self):
        p = get_profile("high_uncertainty_probe")
        self.assertIn("weights", p)
        self.assertTrue(p.get("prefer_uncertain", False))
        self.assertGreater(p["explore_ratio"], 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
