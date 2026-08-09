"""Scorecard orchestrator + decomposition + classification.
Mocked connectors. Zero network."""
from __future__ import annotations

import unittest

from geaspirit.opportunity.contracts import (
    AOI, ConnectorResult, Evidence, SubScores, OPPORTUNITY_CLASSES,
)
from geaspirit.opportunity.orchestrator import score_opportunity


def _ev(tag, conf=0.8, data=None):
    return Evidence(tag=tag, source="mock",
                    fetched_at="2026-05-28T00:00:00Z",
                    confidence=conf, license="MOCK",
                    notes="", data=data or {})


# --- canned connector results ----------------------------------------

def _fake_osm_full(_aoi):
    return ConnectorResult(
        connector="osm_logistics", status="ok",
        evidence=(
            _ev("nearby_road_access", data={"distance_km": 2.5}),
            _ev("nearby_railway",     data={"distance_km": 9.0}),
            _ev("nearby_port",        data={"distance_km": 70.0}),
            _ev("nearby_airport",     data={"distance_km": 55.0}),
        ),
        fetched_at="2026-05-28T00:00:00Z",
    )


def _fake_env_clear(_aoi):
    return ConnectorResult(
        connector="env_constraints", status="ok",
        evidence=(_ev("environmental_clear"),),
        fetched_at="2026-05-28T00:00:00Z",
    )


def _fake_env_medium(_aoi):
    return ConnectorResult(
        connector="env_constraints", status="ok",
        evidence=(_ev("environmental_risk_medium"),),
        fetched_at="2026-05-28T00:00:00Z",
    )


def _fake_env_high(_aoi):
    return ConnectorResult(
        connector="env_constraints", status="ok",
        evidence=(_ev("environmental_risk_high"),),
        fetched_at="2026-05-28T00:00:00Z",
    )


def _fake_tailings_hit(_aoi):
    return ConnectorResult(
        connector="tailings_portal", status="ok",
        evidence=(_ev("nearby_tailings_facility",
                       data={"count": 3, "largest_volume_m3": 5_000_000}),),
        fetched_at="2026-05-28T00:00:00Z",
    )


def _fake_tailings_huge(_aoi):
    return ConnectorResult(
        connector="tailings_portal", status="ok",
        evidence=(_ev("nearby_tailings_facility",
                       data={"count": 8, "largest_volume_m3": 50_000_000}),),
        fetched_at="2026-05-28T00:00:00Z",
    )


def _fake_skipped(connector_name):
    def fn(_aoi):
        return ConnectorResult(connector=connector_name, status="skipped",
                               fetched_at="2026-05-28T00:00:00Z",
                               error_message="no data file")
    return fn


# --- MITECO legal evidence fakes (Sprint 2.1) ------------------------

def _fake_miteco(tag, dominant_status):
    def fn(_aoi):
        return ConnectorResult(
            connector="miteco_catastro", status="ok",
            evidence=(_ev(tag, conf=0.75,
                          data={"dominant_status": dominant_status,
                                "count": 1,
                                "import_mode": "operator_pasted_json"}),),
            fetched_at="2026-05-28T00:00:00Z",
        )
    return fn


_fake_miteco_expired      = _fake_miteco("title_expired", "expired")
_fake_miteco_cancelled    = _fake_miteco("title_cancelled", "cancelled")
_fake_miteco_third_party  = _fake_miteco("title_active_by_third_party",
                                          "active_third_party")
_fake_miteco_conflicting  = _fake_miteco("title_conflicting", "conflicting")
_fake_miteco_clear        = _fake_miteco("title_clear", "active_clear")


# --- tests -----------------------------------------------------------

class StructureTests(unittest.TestCase):
    def setUp(self):
        self.aoi = AOI(name="Test W-Sn", lat=42.6, lon=-8.3,
                       radius_km=30, country="ES",
                       metals_of_interest=("W", "Sn"))

    def test_scorecard_has_subscores(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit))
        self.assertIsInstance(sc.subscores, SubScores)
        for f in ("geological","logistics","environmental","legal","commercial"):
            v = getattr(sc.subscores, f)
            self.assertGreaterEqual(v, 0); self.assertLessEqual(v, 100)

    def test_score_mirrors_commercial(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit))
        self.assertEqual(sc.score, sc.subscores.commercial)

    def test_opportunity_class_in_enum(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit))
        self.assertIn(sc.opportunity_class, OPPORTUNITY_CLASSES)

    def test_schema_v1(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit))
        self.assertEqual(sc.schema_version, "opportunity_scorecard.v1")


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.aoi = AOI(name="Test W-Sn", lat=42.6, lon=-8.3,
                       radius_km=30, country="ES",
                       metals_of_interest=("W", "Sn"))

    def test_clean_env_yields_extraction_led(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit))
        self.assertEqual(sc.opportunity_class, "extraction_led")
        self.assertEqual(sc.subscores.environmental, 100)

    def test_env_high_with_tailings_is_remediation_led(self):
        """User's key correction: env_high + legacy mineralization
        must reclassify to remediation_led, NOT bonus the score."""
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_high, _fake_tailings_huge))
        self.assertEqual(sc.opportunity_class, "remediation_led")
        # Env subscore must reflect the constraint, not be ignored.
        self.assertLessEqual(sc.subscores.environmental, 30)
        # And commercial must be hard-penalised relative to clear-env case.
        sc_clear = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_huge))
        self.assertLess(sc.subscores.commercial, sc_clear.subscores.commercial)

    def test_env_high_without_geology_is_blocked(self):
        """No metals declared + env high → blocked."""
        bare_aoi = AOI(name="Wilderness probe", lat=42.6, lon=-8.3,
                       radius_km=30, country="ES",
                       metals_of_interest=())
        sc = score_opportunity(bare_aoi,
            connectors=(_fake_osm_full, _fake_env_high,
                        _fake_skipped("tailings_portal")))
        self.assertEqual(sc.opportunity_class, "blocked")
        self.assertIn("not recommended", sc.thesis.lower())

    def test_env_medium_with_geology_is_mixed_or_extraction(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_medium, _fake_tailings_hit))
        # 60 falls in (30, 65] band → mixed
        self.assertEqual(sc.opportunity_class, "mixed")

    def test_no_env_data_does_not_bonus(self):
        """Env connector skipped → unknown ≠ good. Subscore must be
        50 (neutral), never 100."""
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_skipped("env_constraints"),
                        _fake_tailings_hit))
        self.assertEqual(sc.subscores.environmental, 50)


class LegalSubscoreTests(unittest.TestCase):
    """Sprint 2.1: legal subscore must map title status → band, never
    optimistically. Missing MITECO data → 50 (neutral), not 100."""

    def setUp(self):
        self.aoi = AOI(name="Test W-Sn", lat=42.6, lon=-8.3,
                       radius_km=30, country="ES",
                       metals_of_interest=("W", "Sn"))

    def test_no_miteco_data_yields_neutral_legal(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit))
        self.assertEqual(sc.subscores.legal, 50)

    def test_title_clear_raises_legal(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_clear))
        self.assertEqual(sc.subscores.legal, 80)

    def test_title_expired_band(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_expired))
        self.assertEqual(sc.subscores.legal, 72)

    def test_title_cancelled_band(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_cancelled))
        self.assertEqual(sc.subscores.legal, 75)

    def test_title_active_third_party_lowers_legal(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_third_party))
        self.assertEqual(sc.subscores.legal, 55)

    def test_title_conflicting_drops_legal_below_penalty_threshold(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_conflicting))
        # legal 30 ≤ 35 → commercial -10 hard penalty applied
        self.assertEqual(sc.subscores.legal, 30)


class OpportunityClassTests(unittest.TestCase):
    """Sprint 2.1: legal-driven classes."""

    def setUp(self):
        self.aoi = AOI(name="Test W-Sn", lat=42.6, lon=-8.3,
                       radius_km=30, country="ES",
                       metals_of_interest=("W", "Sn"))

    def test_active_third_party_yields_partnership_led(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_third_party))
        self.assertEqual(sc.opportunity_class, "partnership_led")
        self.assertIn("third-party", sc.thesis)

    def test_expired_yields_reactivation_led(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_expired))
        self.assertEqual(sc.opportunity_class, "reactivation_led")
        self.assertIn("re-permit", sc.thesis)

    def test_cancelled_also_yields_reactivation_led(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_cancelled))
        self.assertEqual(sc.opportunity_class, "reactivation_led")

    def test_conflicting_yields_blocked(self):
        """Legal dispute alone parks the AOI commercially."""
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_conflicting))
        self.assertEqual(sc.opportunity_class, "blocked")

    def test_env_block_dominates_over_legal(self):
        """env <= 30 + legacy → remediation_led, even if legal would
        otherwise pick reactivation_led."""
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_high, _fake_tailings_hit,
                        _fake_miteco_expired))
        self.assertEqual(sc.opportunity_class, "remediation_led")

    def test_clear_title_keeps_extraction_led(self):
        sc = score_opportunity(self.aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_hit,
                        _fake_miteco_clear))
        self.assertEqual(sc.opportunity_class, "extraction_led")


class ScoringTests(unittest.TestCase):
    """Anti-regression: numeric formula stays stable."""

    def test_full_strong_case_score(self):
        aoi = AOI(name="x", lat=42.6, lon=-8.3, radius_km=30,
                  country="ES", metals_of_interest=("W", "Sn"))
        sc = score_opportunity(aoi,
            connectors=(_fake_osm_full, _fake_env_clear, _fake_tailings_huge))
        # geo: 30 (metals) +15 (strategic) +25 (tailings hit) +20 (>10M m³) = 90
        # log: 50 base + road<5 +20 + rail<10 +15 + port 70km<80 +6 + airport 55km>30 +0 = 91
        # env: 100 (clear) · leg: 50 (sprint 1.1 neutral)
        # raw = 0.40*90 + 0.25*91 + 0.25*100 + 0.10*50
        #     = 36 + 22.75 + 25 + 5 = 88.75 → 89
        # no env penalty, all 3 connectors ok → no data penalty → 89
        self.assertEqual(sc.subscores.geological, 90)
        self.assertEqual(sc.subscores.logistics, 91)
        self.assertEqual(sc.subscores.environmental, 100)
        self.assertEqual(sc.subscores.legal, 50)
        self.assertEqual(sc.subscores.commercial, 89)
        self.assertEqual(sc.class_grade, "A")

    def test_env_high_applies_hard_penalty(self):
        aoi = AOI(name="x", lat=42.6, lon=-8.3, radius_km=30,
                  country="ES", metals_of_interest=("W", "Sn"))
        sc = score_opportunity(aoi,
            connectors=(_fake_osm_full, _fake_env_high, _fake_tailings_huge))
        # geo:90 log:91 env:25 leg:50
        # raw = 0.40*90 + 0.25*91 + 0.25*25 + 0.10*50 = 36+22.75+6.25+5 = 70
        # env<=30 → hard -25 → 45. Final commercial = 45.
        self.assertEqual(sc.subscores.commercial, 45)


class LanguageGuardrailIntegration(unittest.TestCase):
    def test_generated_thesis_never_claims_resource(self):
        aoi = AOI(name="x", lat=42.6, lon=-8.3, radius_km=30,
                  country="ES", metals_of_interest=("W", "Sn"))
        for conns in (
            (_fake_osm_full, _fake_env_clear,  _fake_tailings_huge),
            (_fake_osm_full, _fake_env_high,   _fake_tailings_huge),
            (_fake_osm_full, _fake_env_medium, _fake_tailings_hit),
            (_fake_osm_full, _fake_skipped("env_constraints"),
             _fake_skipped("tailings_portal")),
        ):
            sc = score_opportunity(aoi, connectors=conns)
            for forbidden in ("confirmed resource", "guaranteed", "proven reserves"):
                self.assertNotIn(forbidden, sc.thesis.lower())
                self.assertNotIn(forbidden, sc.next_step.lower())


if __name__ == "__main__":
    unittest.main()
