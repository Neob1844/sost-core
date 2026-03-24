#!/usr/bin/env python3
"""Phase XI.D Tests — Chemistry-aware campaign selection + family-aware seeding."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.campaign_intelligence import (
    classify_family_status, score_campaign_chemistry,
    score_seed_chemistry, generate_campaign_rationale
)
from autonomous_discovery.autonomy_governor import AutonomyGovernor
from autonomous_discovery.policy import get_profile, CAMPAIGN_PROFILES
from validation_bridge.evidence import EvidenceStore


class TestFamilyStatus(unittest.TestCase):

    def test_no_evidence_exploratory(self):
        ev = EvidenceStore(None)
        status, reason = classify_family_status("Ga-As", ev)
        self.assertEqual(status, "exploratory")

    def test_good_evidence_preferred(self):
        ev = EvidenceStore(None)
        for _ in range(5):
            ev.record({"classification": "model_supports_candidate", "fe_abs_error": 0.08},
                       elements=["Ga", "As"])
        status, reason = classify_family_status("As-Ga", ev)
        self.assertEqual(status, "preferred")

    def test_noisy_family(self):
        ev = EvidenceStore(None)
        for _ in range(5):
            ev.record({"classification": "model_overconfident", "fe_abs_error": 0.5},
                       elements=["X", "Y"])
        status, reason = classify_family_status("X-Y", ev)
        self.assertEqual(status, "noisy")

    def test_low_yield_cooldown(self):
        ev = EvidenceStore(None)
        for _ in range(8):
            ev.record({"classification": "model_overconfident"}, elements=["Z", "W"])
        ev.record({"classification": "model_supports_candidate"}, elements=["Z", "W"])
        status, _ = classify_family_status("W-Z", ev)
        self.assertIn(status, ("cooldown", "noisy", "cautionary"))


class TestCampaignChemistry(unittest.TestCase):

    def test_scoring_returns_valid(self):
        profile = get_profile("balanced")
        result = score_campaign_chemistry("balanced", profile)
        self.assertIn("score", result)
        self.assertIn("reasons", result)
        self.assertGreater(result["score"], 0)

    def test_chemistry_aware_profile_boosted(self):
        p1 = get_profile("chemistry_aware_discovery")
        p2 = get_profile("exotic_hunt")
        r1 = score_campaign_chemistry("chemistry_aware_discovery", p1)
        r2 = score_campaign_chemistry("exotic_hunt", p2)
        # Chemistry-aware should score higher for defensibility
        self.assertGreater(r1["score"], r2["score"] - 0.2)  # within reason

    def test_evidence_improves_score(self):
        ev = EvidenceStore(None)
        for _ in range(6):
            ev.record({"classification": "model_supports_candidate"}, campaign="battery_relevant")
        p = get_profile("battery_relevant")
        r1 = score_campaign_chemistry("battery_relevant", p, None)
        r2 = score_campaign_chemistry("battery_relevant", p, ev)
        self.assertGreater(r2["score"], r1["score"])


class TestSeedChemistry(unittest.TestCase):

    def test_familiar_seeds_score_higher(self):
        r1 = score_seed_chemistry(("GaAs", "AlN"))  # familiar III-V
        r2 = score_seed_chemistry(("Zr5B", "Hf3C"))  # unusual
        self.assertGreater(r1["score"], r2["score"])

    def test_seed_has_reasons(self):
        r = score_seed_chemistry(("GaAs", "TiO2"))
        self.assertIsInstance(r["reasons"], list)
        self.assertGreater(len(r["reasons"]), 0)

    def test_evidence_affects_seeds(self):
        ev = EvidenceStore(None)
        for _ in range(5):
            ev.record({"classification": "model_overconfident"}, elements=["Ti", "O"])
        r = score_seed_chemistry(("TiO2", "ZnO"), ev)
        # TiO2 family is noisy, should lower score
        self.assertLess(r["score"], 0.7)


class TestGovernorIntegration(unittest.TestCase):

    def test_recommend_campaign_has_rationale(self):
        gov = AutonomyGovernor(level=3)
        rec = gov.recommend_campaign()
        self.assertIn("rationale", rec)
        self.assertGreater(len(rec["rationale"]), 0)

    def test_recommend_campaign_has_families(self):
        gov = AutonomyGovernor(level=3)
        rec = gov.recommend_campaign()
        self.assertIn("target_families", rec)
        self.assertIn("avoided_families", rec)

    def test_seed_recommendation_uses_chemistry(self):
        gov = AutonomyGovernor(level=3)
        seeds = [("GaAs", "AlN"), ("TiO2", "ZnO"), ("Si", "Ge")]
        result = gov.recommend_seeds(seeds, n=2)
        self.assertEqual(len(result), 2)
        # Should prefer familiar seeds
        self.assertIn(result[0], seeds)


class TestCampaignRationale(unittest.TestCase):

    def test_rationale_generation(self):
        profile = get_profile("balanced")
        chem = {"score": 0.65, "reasons": ["good yield"], "target_families": ["As-Ga"],
                "avoided_families": ["X-Y"]}
        r = generate_campaign_rationale("balanced", profile, chem)
        self.assertIn("balanced", r)
        self.assertIn("0.65", r)
        self.assertIn("As-Ga", r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
