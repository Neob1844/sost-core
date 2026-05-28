"""Contracts: validation + language guardrail."""
from __future__ import annotations

import unittest

from geaspirit.opportunity.contracts import (
    AOI, Evidence, ConnectorResult, OpportunityScorecard, SubScores,
    FORBIDDEN_PHRASES,
)


def _ok_subscores(commercial=70):
    """Helper: minimal valid SubScores instance for tests where the
    numbers don't matter, only the language guardrail does."""
    return SubScores(geological=70, logistics=70, environmental=70,
                     legal=50, commercial=commercial)


class AOITests(unittest.TestCase):
    def test_valid_aoi(self):
        aoi = AOI(name="Galicia W-Sn", lat=42.64, lon=-8.35,
                  radius_km=30, country="ES",
                  metals_of_interest=("W", "Sn"),
                  notes="historical pegmatite district")
        self.assertEqual(aoi.name, "Galicia W-Sn")

    def test_reject_bad_lat(self):
        with self.assertRaises(ValueError):
            AOI(name="x", lat=99, lon=0, radius_km=1)

    def test_reject_bad_radius(self):
        with self.assertRaises(ValueError):
            AOI(name="x", lat=0, lon=0, radius_km=0)


class EvidenceTests(unittest.TestCase):
    def test_valid_evidence(self):
        e = Evidence(tag="nearby_road_access",
                     source="OpenStreetMap",
                     fetched_at="2026-05-28T00:00:00Z",
                     confidence=0.85, license="ODbL-1.0")
        self.assertEqual(e.tag, "nearby_road_access")

    def test_reject_bad_confidence(self):
        with self.assertRaises(ValueError):
            Evidence(tag="x", source="x", fetched_at="x",
                     confidence=1.5, license="x")


class LanguageGuardrailTests(unittest.TestCase):
    """Forbidden phrases on user-facing strings must raise ValueError."""

    def test_thesis_blocks_confirmed_resource(self):
        aoi = AOI(name="x", lat=0, lon=0, radius_km=1)
        with self.assertRaises(ValueError) as cm:
            OpportunityScorecard(
                aoi=aoi, score=70, class_grade="B+",
                opportunity_class="mixed", subscores=_ok_subscores(70),
                thesis="This area has confirmed resource of 100Mt Cu.",
                next_step="contact owner",
            )
        self.assertIn("confirmed resource", str(cm.exception).lower())

    def test_next_step_blocks_guaranteed_return(self):
        aoi = AOI(name="x", lat=0, lon=0, radius_km=1)
        with self.assertRaises(ValueError):
            OpportunityScorecard(
                aoi=aoi, score=70, class_grade="B+",
                opportunity_class="mixed", subscores=_ok_subscores(70),
                thesis="candidate",
                next_step="acquire option and earn a guaranteed return",
            )

    def test_aoi_notes_blocks_jorc(self):
        with self.assertRaises(ValueError):
            AOI(name="x", lat=0, lon=0, radius_km=1,
                notes="this AOI is JORC-compliant")

    def test_clean_strings_pass(self):
        aoi = AOI(name="x", lat=0, lon=0, radius_km=1)
        sc = OpportunityScorecard(
            aoi=aoi, score=70, class_grade="B+",
            opportunity_class="mixed", subscores=_ok_subscores(70),
            thesis="Historical occurrence merits due diligence.",
            next_step="Identify titular and request sampling quote.",
        )
        self.assertEqual(sc.score, 70)

    def test_score_must_mirror_commercial_subscore(self):
        """Anti-confusion: score and subscores.commercial MUST match."""
        aoi = AOI(name="x", lat=0, lon=0, radius_km=1)
        with self.assertRaises(ValueError):
            OpportunityScorecard(
                aoi=aoi, score=80,          # 80 vs 70 in subscores
                class_grade="A",
                opportunity_class="mixed", subscores=_ok_subscores(70),
                thesis="candidate", next_step="next step",
            )

    def test_opportunity_class_must_be_valid(self):
        aoi = AOI(name="x", lat=0, lon=0, radius_km=1)
        with self.assertRaises(ValueError):
            OpportunityScorecard(
                aoi=aoi, score=70, class_grade="B+",
                opportunity_class="bogus", subscores=_ok_subscores(70),
                thesis="candidate", next_step="next step",
            )

    def test_forbidden_phrases_lowercase(self):
        for p in FORBIDDEN_PHRASES:
            self.assertEqual(p, p.lower(),
                             f"FORBIDDEN_PHRASES entry not lowercase: {p}")


if __name__ == "__main__":
    unittest.main()
