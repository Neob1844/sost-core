#!/usr/bin/env python3
"""Phase XI.C Tests — Chemistry-aware scoring and prioritization."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.scorer import score_candidate
from autonomous_discovery.policy import get_profile


class TestChemistryAwareScoring(unittest.TestCase):

    def _profile(self):
        return get_profile("balanced")

    def test_familiar_gets_boost(self):
        ctx_familiar = {
            "is_known_material": False, "has_direct_gnn_fe": True,
            "has_structure_lift": True, "prediction_origin": "direct_gnn_lifted",
            "gnn_confidence": "medium",
            "risk_level": "familiar", "family": "III-V semiconductor",
            "caution_labels": ["FAMILY SUPPORTED", "III-V FAMILY"],
        }
        ctx_unknown = {
            "is_known_material": False, "has_direct_gnn_fe": True,
            "has_structure_lift": True, "prediction_origin": "direct_gnn_lifted",
            "gnn_confidence": "medium",
            "risk_level": "unknown", "family": None, "caution_labels": [],
        }
        s1 = score_candidate("GaAlAs", ["Ga", "Al", "As"], "element_substitution",
                              self._profile(), candidate_context=ctx_familiar)
        s2 = score_candidate("GaAlAs", ["Ga", "Al", "As"], "element_substitution",
                              self._profile(), candidate_context=ctx_unknown)
        self.assertGreater(s1["composite_score"], s2["composite_score"])
        self.assertGreater(s1["chemistry_family_adj"], 0)

    def test_risky_gets_penalty(self):
        ctx_risky = {
            "is_known_material": False, "has_direct_gnn_fe": False,
            "has_structure_lift": False, "prediction_origin": "proxy_only",
            "gnn_confidence": "none",
            "risk_level": "risky", "family": None,
            "caution_labels": ["UNUSUAL STOICHIOMETRY", "NO FAMILY MATCH"],
        }
        ctx_plausible = {
            "is_known_material": False, "has_direct_gnn_fe": False,
            "has_structure_lift": False, "prediction_origin": "proxy_only",
            "gnn_confidence": "none",
            "risk_level": "plausible", "family": "Mixed oxide",
            "caution_labels": ["MIXED OXIDE"],
        }
        s1 = score_candidate("Zr5B", ["Zr", "B"], "mixed_parent",
                              self._profile(), candidate_context=ctx_risky)
        s2 = score_candidate("Zr5B", ["Zr", "B"], "mixed_parent",
                              self._profile(), candidate_context=ctx_plausible)
        self.assertLess(s1["composite_score"], s2["composite_score"])
        self.assertLess(s1["chemistry_risk_adj"], 0)

    def test_unusual_reduced_with_gnn(self):
        ctx_unusual_no_gnn = {
            "is_known_material": False, "has_direct_gnn_fe": False,
            "has_structure_lift": False, "prediction_origin": "proxy_only",
            "risk_level": "unusual", "caution_labels": [],
        }
        ctx_unusual_with_gnn = {
            "is_known_material": False, "has_direct_gnn_fe": True,
            "has_structure_lift": True, "prediction_origin": "direct_gnn_lifted",
            "gnn_confidence": "medium",
            "risk_level": "unusual", "caution_labels": [],
        }
        s1 = score_candidate("XY", ["X", "Y"], "element_substitution",
                              self._profile(), candidate_context=ctx_unusual_no_gnn)
        s2 = score_candidate("XY", ["X", "Y"], "element_substitution",
                              self._profile(), candidate_context=ctx_unusual_with_gnn)
        # With GNN evidence, penalty should be reduced
        self.assertGreater(s2["chemistry_risk_adj"], s1["chemistry_risk_adj"])

    def test_suboxide_extra_penalty(self):
        ctx = {
            "is_known_material": False, "has_direct_gnn_fe": False,
            "has_structure_lift": False, "prediction_origin": "proxy_only",
            "risk_level": "unusual",
            "caution_labels": ["SUBOXIDE-LIKE"],
        }
        s = score_candidate("Zn3O", ["Zn", "O"], "element_substitution",
                             self._profile(), candidate_context=ctx)
        self.assertLess(s["chemistry_risk_adj"], -0.06)  # unusual + suboxide

    def test_battery_relevant_boost(self):
        ctx = {
            "is_known_material": False, "has_direct_gnn_fe": True,
            "has_structure_lift": True, "prediction_origin": "direct_gnn_lifted",
            "gnn_confidence": "medium",
            "risk_level": "familiar",
            "caution_labels": ["FAMILY SUPPORTED", "BATTERY-RELEVANT"],
        }
        s = score_candidate("CoLiO2", ["Co", "Li", "O"], "element_substitution",
                             self._profile(), candidate_context=ctx)
        self.assertGreater(s["chemistry_family_adj"], 0.04)  # familiar + battery bonus

    def test_no_chemistry_context_no_adjustment(self):
        s = score_candidate("GaAs", ["Ga", "As"], "element_substitution",
                             self._profile())
        self.assertEqual(s["chemistry_risk_adj"], 0.0)
        self.assertEqual(s["chemistry_family_adj"], 0.0)
        self.assertEqual(s["chemistry_risk_level"], "unknown")

    def test_output_has_chemistry_fields(self):
        ctx = {"risk_level": "plausible", "caution_labels": []}
        s = score_candidate("GaAs", ["Ga", "As"], "element_substitution",
                             self._profile(), candidate_context=ctx)
        self.assertIn("chemistry_risk_adj", s)
        self.assertIn("chemistry_family_adj", s)
        self.assertIn("chemistry_risk_level", s)


class TestChemistryAwareProfile(unittest.TestCase):

    def test_profile_exists(self):
        p = get_profile("chemistry_aware_discovery")
        self.assertIn("weights", p)
        self.assertTrue(p.get("prefer_familiar_chemistry", False))

    def test_profile_distinct(self):
        p1 = get_profile("chemistry_aware_discovery")
        p2 = get_profile("exotic_hunt")
        self.assertNotEqual(p1["weights"]["stability"], p2["weights"]["stability"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
