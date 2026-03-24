#!/usr/bin/env python3
"""Phase XI Tests — Calibration intelligence, evidence-driven scoring, noise suppression."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from validation_bridge.calibration_intelligence import (
    compute_family_trust, compute_strategy_trust, compute_scoring_adjustments
)
from validation_bridge.evidence import EvidenceStore
from validation_bridge.calibration import CalibrationStore
from autonomous_discovery.scorer import score_candidate
from autonomous_discovery.policy import get_profile


class TestFamilyTrust(unittest.TestCase):

    def test_no_evidence_unknown(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        ft = compute_family_trust(["Ga", "As"], ev, cal)
        self.assertEqual(ft["family_reliability"], "unknown")
        self.assertEqual(ft["family_trust_score"], 0.0)
        self.assertEqual(ft["family_evidence_count"], 0)

    def test_good_evidence_strong(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        for _ in range(5):
            ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.08},
                       elements=["Ga", "As"])
        ft = compute_family_trust(["Ga", "As"], ev, cal)
        self.assertGreater(ft["family_trust_score"], 0.2)
        self.assertEqual(ft["family_reliability"], "strong")

    def test_poor_evidence_weak(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        for _ in range(5):
            ev.record({"classification": "model_overconfident", "fe_abs_error": 0.8},
                       elements=["X", "Y"])
        ft = compute_family_trust(["X", "Y"], ev, cal)
        self.assertLess(ft["family_trust_score"], 0.0)
        self.assertEqual(ft["family_reliability"], "weak")

    def test_calibration_adjustment_applied(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.10},
                   elements=["Ti", "O"])
        # Manually set calibration
        cal.family_trust["O-Ti"] = 0.2
        ft = compute_family_trust(["Ti", "O"], ev, cal)
        self.assertGreater(ft["family_trust_score"], 0.3)


class TestStrategyTrust(unittest.TestCase):

    def test_no_evidence(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        st = compute_strategy_trust("element_substitution", ev, cal)
        self.assertEqual(st["strategy_reliability"], "unknown")

    def test_good_yield(self):
        ev = EvidenceStore(None)
        cal = CalibrationStore(None)
        for _ in range(4):
            ev.record({"classification": "model_supports_candidate"}, method="element_substitution")
        ev.record({"classification": "model_overconfident"}, method="element_substitution")
        st = compute_strategy_trust("element_substitution", ev, cal)
        self.assertGreater(st["strategy_trust_score"], 0.0)
        self.assertAlmostEqual(st["strategy_validation_yield"], 0.8, places=1)


class TestScoringAdjustments(unittest.TestCase):

    def test_strong_family_and_strategy(self):
        ft = {"family_trust_score": 0.4}
        st = {"strategy_trust_score": 0.3}
        adj = compute_scoring_adjustments(ft, st)
        self.assertGreater(adj["family_trust_bonus"], 0)
        self.assertGreater(adj["strategy_trust_bonus"], 0)
        self.assertEqual(adj["noise_suppression_penalty"], 0.0)
        self.assertEqual(adj["evidence_quality_label"], "evidence_supported")

    def test_weak_family_and_strategy(self):
        ft = {"family_trust_score": -0.4}
        st = {"strategy_trust_score": -0.2}
        adj = compute_scoring_adjustments(ft, st)
        self.assertLess(adj["family_trust_bonus"], 0)
        self.assertLess(adj["strategy_trust_bonus"], 0)
        self.assertGreater(adj["noise_suppression_penalty"], 0.10)
        self.assertEqual(adj["evidence_quality_label"], "evidence_warns")

    def test_neutral(self):
        ft = {"family_trust_score": 0.0}
        st = {"strategy_trust_score": 0.0}
        adj = compute_scoring_adjustments(ft, st)
        self.assertEqual(adj["family_trust_bonus"], 0.0)
        self.assertEqual(adj["strategy_trust_bonus"], 0.0)
        self.assertEqual(adj["evidence_quality_label"], "evidence_neutral")


class TestScorerWithEvidence(unittest.TestCase):

    def test_evidence_bonus_applied(self):
        profile = get_profile("balanced")
        adj = {"family_trust_bonus": 0.08, "strategy_trust_bonus": 0.05,
               "noise_suppression_penalty": 0.0, "evidence_quality_label": "evidence_supported"}
        s1 = score_candidate("GaAlAs", ["Ga", "Al", "As"], "element_substitution", profile)
        s2 = score_candidate("GaAlAs", ["Ga", "Al", "As"], "element_substitution", profile,
                              evidence_adjustments=adj)
        self.assertGreater(s2["composite_score"], s1["composite_score"])
        self.assertEqual(s2["evidence_quality"], "evidence_supported")

    def test_evidence_penalty_applied(self):
        profile = get_profile("balanced")
        adj = {"family_trust_bonus": -0.10, "strategy_trust_bonus": -0.06,
               "noise_suppression_penalty": 0.15, "evidence_quality_label": "evidence_warns"}
        s1 = score_candidate("GaAlAs", ["Ga", "Al", "As"], "element_substitution", profile)
        s2 = score_candidate("GaAlAs", ["Ga", "Al", "As"], "element_substitution", profile,
                              evidence_adjustments=adj)
        self.assertLess(s2["composite_score"], s1["composite_score"])
        self.assertEqual(s2["evidence_quality"], "evidence_warns")

    def test_no_evidence_no_change(self):
        profile = get_profile("balanced")
        s1 = score_candidate("GaAs", ["Ga", "As"], "element_substitution", profile)
        s2 = score_candidate("GaAs", ["Ga", "As"], "element_substitution", profile,
                              evidence_adjustments=None)
        self.assertEqual(s1["composite_score"], s2["composite_score"])
        self.assertEqual(s2["evidence_quality"], "no_evidence")

    def test_evidence_fields_in_output(self):
        profile = get_profile("balanced")
        adj = {"family_trust_bonus": 0.05, "strategy_trust_bonus": 0.02,
               "noise_suppression_penalty": 0.0, "evidence_quality_label": "evidence_supported"}
        s = score_candidate("GaAs", ["Ga", "As"], "element_substitution", profile,
                             evidence_adjustments=adj)
        self.assertIn("family_trust_bonus", s)
        self.assertIn("strategy_trust_bonus", s)
        self.assertIn("noise_suppression", s)
        self.assertIn("evidence_quality", s)


class TestEvidenceGuidedProfile(unittest.TestCase):

    def test_profile_exists(self):
        p = get_profile("evidence_guided_discovery")
        self.assertIn("weights", p)
        self.assertTrue(p.get("use_evidence_calibration", False))

    def test_profile_distinct(self):
        p1 = get_profile("evidence_guided_discovery")
        p2 = get_profile("valuable_unknowns")
        self.assertNotEqual(p1["weights"], p2["weights"])


class TestNoiseSuppression(unittest.TestCase):

    def test_both_weak_triggers_suppression(self):
        ft = {"family_trust_score": -0.3}
        st = {"strategy_trust_score": -0.2}
        adj = compute_scoring_adjustments(ft, st)
        self.assertGreaterEqual(adj["noise_suppression_penalty"], 0.15)

    def test_one_weak_mild_suppression(self):
        ft = {"family_trust_score": -0.15}
        st = {"strategy_trust_score": 0.1}
        adj = compute_scoring_adjustments(ft, st)
        self.assertGreater(adj["noise_suppression_penalty"], 0)
        self.assertLess(adj["noise_suppression_penalty"], 0.15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
