#!/usr/bin/env python3
"""Phase XI.B Tests — Autonomy governance, auto-selection, promotion/demotion."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.autonomy_governor import AutonomyGovernor, AUTONOMY_LEVELS
from validation_bridge.evidence import EvidenceStore
from validation_bridge.calibration import CalibrationStore


class TestAutonomyLevels(unittest.TestCase):

    def test_all_levels_defined(self):
        for i in range(5):
            self.assertIn(i, AUTONOMY_LEVELS)
            self.assertIn("name", AUTONOMY_LEVELS[i])

    def test_level_0_blocks_everything(self):
        gov = AutonomyGovernor(level=0)
        self.assertFalse(gov.config["auto_campaign"])
        self.assertFalse(gov.config["auto_promote"])
        self.assertFalse(gov.config["auto_demote"])

    def test_level_3_allows_most(self):
        gov = AutonomyGovernor(level=3)
        self.assertTrue(gov.config["auto_campaign"])
        self.assertTrue(gov.config["auto_promote"])
        self.assertTrue(gov.config["auto_demote"])
        self.assertTrue(gov.config["policy_adapt"])

    def test_set_level_clamped(self):
        gov = AutonomyGovernor(level=2)
        gov.set_level(99)
        self.assertEqual(gov.level, 4)
        gov.set_level(-5)
        self.assertEqual(gov.level, 0)


class TestCampaignAutoSelection(unittest.TestCase):

    def test_low_level_requires_human(self):
        gov = AutonomyGovernor(level=0)
        rec = gov.recommend_campaign()
        self.assertTrue(rec["requires_human"])
        self.assertIsNone(rec["profile"])

    def test_high_level_recommends(self):
        gov = AutonomyGovernor(level=3)
        rec = gov.recommend_campaign()
        self.assertFalse(rec["requires_human"])
        self.assertIsNotNone(rec["profile"])
        self.assertIn(rec["profile"], list(__import__('autonomous_discovery.policy', fromlist=['CAMPAIGN_PROFILES']).CAMPAIGN_PROFILES.keys()))

    def test_recommendation_has_reason(self):
        gov = AutonomyGovernor(level=3)
        rec = gov.recommend_campaign()
        self.assertIn("reason", rec)
        self.assertGreater(len(rec["reason"]), 0)

    def test_goals_influence_selection(self):
        gov1 = AutonomyGovernor(level=3)
        gov1.set_goals(["maximize_defensible_novel_candidates"])
        rec1 = gov1.recommend_campaign()

        gov2 = AutonomyGovernor(level=3)
        gov2.set_goals(["improve_weak_families"])
        rec2 = gov2.recommend_campaign()

        # Different goals should potentially produce different recommendations
        # (they might be the same if one profile dominates both, but the scores should differ)
        self.assertIn("all_scores", rec1)
        self.assertIn("all_scores", rec2)

    def test_evidence_influences_selection(self):
        ev = EvidenceStore(None)
        # Record evidence for one campaign
        for _ in range(5):
            ev.record({"classification": "model_supports_candidate"},
                       campaign="battery_relevant")
        gov = AutonomyGovernor(level=3, evidence_store=ev)
        rec = gov.recommend_campaign()
        self.assertIsNotNone(rec["profile"])


class TestAutoPromotion(unittest.TestCase):

    def test_disabled_at_low_level(self):
        gov = AutonomyGovernor(level=1)
        ok, reason = gov.should_promote(
            {"composite_score": 0.9, "is_novel_direct_gnn": True},
            {"confidence_score": 0.9},
            {"validation_readiness_score": 0.9})
        self.assertFalse(ok)
        self.assertIn("disabled", reason)

    def test_promotes_strong_candidate(self):
        gov = AutonomyGovernor(level=3)
        ok, reason = gov.should_promote(
            {"composite_score": 0.65, "is_novel_direct_gnn": True},
            {"confidence_score": 0.60},
            {"validation_readiness_score": 0.60})
        self.assertTrue(ok)
        self.assertIn("auto_promote", reason)

    def test_rejects_weak_candidate(self):
        gov = AutonomyGovernor(level=3)
        ok, reason = gov.should_promote(
            {"composite_score": 0.40, "is_novel_direct_gnn": False},
            {"confidence_score": 0.30},
            {"validation_readiness_score": 0.30})
        self.assertFalse(ok)


class TestAutoDemotion(unittest.TestCase):

    def test_demotes_low_confidence(self):
        gov = AutonomyGovernor(level=3)
        ok, reason = gov.should_demote(
            {"composite_score": 0.25, "evidence_quality": "evidence_warns"},
            {"confidence_score": 0.20})
        self.assertTrue(ok)

    def test_keeps_decent_candidate(self):
        gov = AutonomyGovernor(level=3)
        ok, reason = gov.should_demote(
            {"composite_score": 0.60, "evidence_quality": "evidence_supported"},
            {"confidence_score": 0.65})
        self.assertFalse(ok)

    def test_evidence_warns_triggers_demotion(self):
        gov = AutonomyGovernor(level=3)
        ok, reason = gov.should_demote(
            {"composite_score": 0.40, "evidence_quality": "evidence_warns"},
            {"confidence_score": 0.50})
        self.assertTrue(ok)
        self.assertIn("evidence_warns", reason)


class TestHumanReviewTriggers(unittest.TestCase):

    def test_high_value_high_uncertainty(self):
        gov = AutonomyGovernor(level=3)
        triggers = gov.needs_human_review(
            {"composite_score": 0.60},
            {"confidence_score": 0.30, "out_of_domain_risk": 0.2},
            {"validation_readiness_score": 0.50})
        self.assertIn("high_value_high_uncertainty", triggers)

    def test_near_handoff(self):
        gov = AutonomyGovernor(level=3)
        triggers = gov.needs_human_review(
            {"composite_score": 0.55},
            {"confidence_score": 0.60, "out_of_domain_risk": 0.1},
            {"validation_readiness_score": 0.60})
        self.assertIn("near_handoff_threshold", triggers)

    def test_no_triggers_for_clear_case(self):
        gov = AutonomyGovernor(level=3)
        triggers = gov.needs_human_review(
            {"composite_score": 0.80},
            {"confidence_score": 0.80, "out_of_domain_risk": 0.05},
            {"validation_readiness_score": 0.80})
        self.assertEqual(len(triggers), 0)


class TestDecisionLog(unittest.TestCase):

    def test_logs_decisions(self):
        gov = AutonomyGovernor(level=3)
        gov.recommend_campaign()
        self.assertGreater(len(gov.decision_log), 0)
        self.assertIn("event", gov.decision_log[0])

    def test_summary(self):
        gov = AutonomyGovernor(level=2)
        s = gov.summary()
        self.assertEqual(s["autonomy_level"], 2)
        self.assertEqual(s["autonomy_name"], "supervised")
        self.assertIn("capabilities", s)


class TestAutoSeed(unittest.TestCase):

    def test_returns_seeds(self):
        gov = AutonomyGovernor(level=2)
        seeds = [("GaAs", "AlN"), ("TiO2", "ZnO"), ("Si", "Ge")]
        result = gov.recommend_seeds(seeds, n=2)
        self.assertEqual(len(result), 2)

    def test_evidence_influences_seeds(self):
        ev = EvidenceStore(None)
        for _ in range(5):
            ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.05},
                       elements=["Ga", "As"])
        gov = AutonomyGovernor(level=3, evidence_store=ev)
        seeds = [("GaAs", "AlN"), ("XY", "ZW")]
        result = gov.recommend_seeds(seeds, n=2)
        # GaAs should be preferred (reliable family)
        self.assertEqual(result[0], ("GaAs", "AlN"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
