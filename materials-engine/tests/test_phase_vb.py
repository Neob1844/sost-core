#!/usr/bin/env python3
"""Phase V.B Tests — Direct GNN integration, scoring, and validation queue.

Tests:
  VB01: candidate → lift → CGCNN FE prediction
  VB02: candidate → lift → ALIGNN BG prediction
  VB03: graceful fallback if one model fails
  VB04: known materials get tagged as references
  VB05: new candidates with direct GNN score above proxy-only
  VB06: validation queue routes known materials to known_reference
  VB07: validation queue boosts direct_gnn_lifted candidates
  VB08: proxy_only capped at validation_candidate
  VB09: run_direct_gnn_inference returns combined result
  VB10: engine builds candidate_context correctly
  VB11: known_material_penalty applied in scorer
  VB12: direct_gnn_bonus applied in scorer
  VB13: no regressions in basic scoring
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest

from autonomous_discovery.scorer import score_candidate
from autonomous_discovery.validation_queue import route_candidate
from autonomous_discovery.structure_pipeline import (
    run_gnn_inference, run_direct_gnn_inference, get_parent_cif
)
from autonomous_discovery.chem_filters import parse_formula, normalize_formula
from autonomous_discovery.policy import get_profile


class TestDirectGNNIntegration(unittest.TestCase):
    """Test direct GNN inference integration."""

    def test_vb01_run_gnn_inference_formation_energy(self):
        """VB01: run_gnn_inference attempts CGCNN for new candidates."""
        # Get a known structure CIF
        parent = get_parent_cif("GaAs")
        if parent is None:
            self.skipTest("No GaAs structure in corpus")
        result = run_gnn_inference(parent["cif"], target="formation_energy")
        # GaAs should be corpus_exact_match
        self.assertIn(result["gnn_inference_status"],
                       ("corpus_exact_match", "direct_gnn_success"))
        self.assertIsNotNone(result["prediction"])

    def test_vb02_run_gnn_inference_band_gap(self):
        """VB02: run_gnn_inference attempts ALIGNN for band gap."""
        parent = get_parent_cif("GaAs")
        if parent is None:
            self.skipTest("No GaAs structure in corpus")
        result = run_gnn_inference(parent["cif"], target="band_gap")
        self.assertIn(result["gnn_inference_status"],
                       ("corpus_exact_match", "direct_gnn_success"))

    def test_vb03_graceful_fallback(self):
        """VB03: Invalid CIF fails gracefully."""
        result = run_gnn_inference("INVALID CIF DATA", target="formation_energy")
        self.assertIn(result["gnn_inference_status"],
                       ("invalid_structure", "error:"))
        self.assertIn(result["prediction_origin"],
                       ("unavailable", "proxy_only"))

    def test_vb04_known_material_detected(self):
        """VB04: Known materials are detected via corpus lookup."""
        known = get_parent_cif("GaAs")
        self.assertIsNotNone(known, "GaAs should be in corpus")

        unknown = get_parent_cif("Xa99Yb77Zc55")
        self.assertIsNone(unknown, "Nonsense formula should not be in corpus")

    def test_vb09_run_direct_gnn_inference(self):
        """VB09: Combined FE+BG inference returns complete dict."""
        parent = get_parent_cif("Si")
        if parent is None:
            self.skipTest("No Si structure in corpus")

        result = run_direct_gnn_inference(parent["cif"])
        self.assertIn("direct_fe_inference_attempted", result)
        self.assertIn("direct_bg_inference_attempted", result)
        self.assertIn("prediction_origin", result)
        self.assertIn("bg_prediction_origin", result)

    def test_vb09b_direct_gnn_none_input(self):
        """VB09b: None CIF input handled gracefully."""
        result = run_direct_gnn_inference(None)
        self.assertFalse(result["direct_fe_inference_success"])
        self.assertFalse(result["direct_bg_inference_success"])


class TestScorerPhaseVB(unittest.TestCase):
    """Test Phase V.B scoring adjustments."""

    def _base_profile(self):
        return get_profile("balanced")

    def test_vb05_direct_gnn_scores_above_proxy(self):
        """VB05: Direct GNN candidates score higher than proxy-only."""
        profile = self._base_profile()

        # Score with direct GNN context
        ctx_gnn = {
            "is_known_material": False,
            "has_direct_gnn_fe": True,
            "has_direct_gnn_bg": False,
            "has_structure_lift": True,
            "prediction_origin": "direct_gnn_lifted",
            "gnn_confidence": "medium",
        }
        scores_gnn = score_candidate("GaAlAs", ["Ga", "Al", "As"],
                                      "element_substitution", profile,
                                      candidate_context=ctx_gnn)

        # Score with proxy-only context
        ctx_proxy = {
            "is_known_material": False,
            "has_direct_gnn_fe": False,
            "has_direct_gnn_bg": False,
            "has_structure_lift": False,
            "prediction_origin": "proxy_only",
            "gnn_confidence": "none",
        }
        scores_proxy = score_candidate("GaAlAs", ["Ga", "Al", "As"],
                                        "element_substitution", profile,
                                        candidate_context=ctx_proxy)

        self.assertGreater(scores_gnn["composite_score"],
                            scores_proxy["composite_score"],
                            "Direct GNN should score higher than proxy-only")

    def test_vb11_known_material_penalty(self):
        """VB11: Known materials get penalized in autonomous mode."""
        profile = self._base_profile()

        ctx_known = {
            "is_known_material": True,
            "has_direct_gnn_fe": True,
            "has_direct_gnn_bg": True,
            "has_structure_lift": True,
            "prediction_origin": "known_exact",
            "gnn_confidence": "high",
        }
        scores = score_candidate("GaAs", ["Ga", "As"],
                                  "element_substitution", profile,
                                  candidate_context=ctx_known)
        self.assertGreater(scores["known_material_penalty"], 0,
                            "Known material should have penalty")

    def test_vb12_direct_gnn_bonus(self):
        """VB12: Direct GNN candidates get bonus."""
        profile = self._base_profile()

        ctx = {
            "is_known_material": False,
            "has_direct_gnn_fe": True,
            "has_direct_gnn_bg": False,
            "has_structure_lift": True,
            "prediction_origin": "direct_gnn_lifted",
            "gnn_confidence": "medium",
        }
        scores = score_candidate("GaAlAs", ["Ga", "Al", "As"],
                                  "element_substitution", profile,
                                  candidate_context=ctx)
        self.assertGreater(scores["direct_gnn_bonus"], 0,
                            "Direct GNN should get bonus")

    def test_vb13_no_regression_basic_scoring(self):
        """VB13: Basic scoring without context still works."""
        profile = self._base_profile()
        scores = score_candidate("GaAs", ["Ga", "As"],
                                  "element_substitution", profile)
        self.assertIn("composite_score", scores)
        self.assertIn("plausibility", scores)
        self.assertGreater(scores["composite_score"], 0)


class TestValidationQueuePhaseVB(unittest.TestCase):
    """Test Phase V.B validation queue routing."""

    def test_vb06_known_material_routes_to_reference(self):
        """VB06: Known materials route to known_reference."""
        scores = {
            "composite_score": 0.70,
            "plausibility": 0.80,
            "decision": "accepted",
        }
        ctx = {"is_known_material": True, "prediction_origin": "known_exact"}
        result = route_candidate(scores, candidate_context=ctx)
        self.assertEqual(result["validation_decision"], "known_reference")

    def test_vb07_direct_gnn_boosted(self):
        """VB07: Direct GNN candidates with good scores get boosted."""
        scores = {
            "composite_score": 0.53,
            "plausibility": 0.65,
            "decision": "accepted",
        }
        ml_eval = {"ml_confidence": "medium", "ml_inference_status": "direct_gnn_success"}
        ctx = {
            "is_known_material": False,
            "prediction_origin": "direct_gnn_lifted",
            "has_structure_lift": True,
        }
        result = route_candidate(scores, ml_eval, candidate_context=ctx)
        self.assertIn(result["validation_decision"],
                       ("priority_validation", "validation_candidate"))

    def test_vb08_proxy_only_capped(self):
        """VB08: Proxy-only candidates cannot reach priority_validation."""
        scores = {
            "composite_score": 0.60,
            "plausibility": 0.70,
            "decision": "accepted",
        }
        ml_eval = {"ml_confidence": "medium", "ml_inference_status": "proxy_from_neighbor"}
        ctx = {
            "is_known_material": False,
            "prediction_origin": "proxy_only",
        }
        result = route_candidate(scores, ml_eval, candidate_context=ctx)
        self.assertNotEqual(result["validation_decision"], "priority_validation",
                             "Proxy-only should not reach priority_validation")


if __name__ == "__main__":
    unittest.main(verbosity=2)
