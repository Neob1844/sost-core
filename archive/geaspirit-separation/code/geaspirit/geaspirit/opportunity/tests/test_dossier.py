"""HTML dossier renderer — network-free tests.

We synthesise a minimal campaign summary dict on disk and assert the
rendered HTML:

  * is single-file and self-contained (no script src=, no link href=
    to external resources),
  * contains the campaign name, AOI ranking entries, capsule note,
    short canonical SHA-256 fragments and the editorial disclaimer,
  * surfaces the opportunity_class labels we expect to ship,
  * refuses to publish a summary that smuggles forbidden promotional
    language into a thesis or next_step field,
  * honours --redact-coordinates by removing per-AOI lat/lon and
    swapping the campaign capsule name to ``redacted``,
  * raises a clear ValueError when handed a per-AOI scorecard JSON
    instead of a campaign summary.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from geaspirit.opportunity import dossier
from geaspirit.opportunity.contracts import FORBIDDEN_PHRASES


def _minimal_summary():
    return {
        "schema_version": "opportunity_campaign.v1",
        "campaign_name": "Iberia Mine-Waste Alpha (test)",
        "campaign_description": "test fixture, candidate desk validation only",
        "campaign_version": "1",
        "generated_at": "2026-05-28T00:00:00Z",
        "aoi_count": 2,
        "redact_coordinates": False,
        "ranking": [
            {"rank": 1, "aoi_name": "Galicia W-Sn / Forcarei", "country": "ES",
             "metals": "W|Sn", "opportunity_class": "extraction_led",
             "class_grade": "B+", "score": 76, "geological": 66,
             "logistics": 79, "environmental": 100, "legal": 50,
             "commercial": 76, "canonical_sha256": "abc123def456" * 5 + "feed"},
            {"rank": 2, "aoi_name": "Cartagena-La Unión", "country": "ES",
             "metals": "Pb|Zn|Ag", "opportunity_class": "remediation_led",
             "class_grade": "B", "score": 58, "geological": 45,
             "logistics": 95, "environmental": 25, "legal": 50,
             "commercial": 58, "canonical_sha256": "0e2f6dd2ba5e7b0c" * 4},
        ],
        "scorecards": [
            {"rank": 1, "aoi": {"name": "Galicia W-Sn / Forcarei", "lat": 42.6,
                                "lon": -8.3, "radius_km": 30.0, "country": "ES",
                                "metals_of_interest": ["W", "Sn"]},
             "opportunity_class": "extraction_led", "class_grade": "B+",
             "score": 76, "subscores": {"geological": 66, "logistics": 79,
                                          "environmental": 100, "legal": 50,
                                          "commercial": 76},
             "thesis": "Candidate desk target with prospectivity bridge.",
             "next_step": "Desk validation; legal title check; sampling.",
             "evidence_tags": ["nearby_road_access", "geaspirit_signal_spectral"],
             "canonical_sha256": "deadbeef" * 8},
            {"rank": 2, "aoi": {"name": "Cartagena-La Unión", "lat": 37.6,
                                "lon": -0.8, "radius_km": 25.0, "country": "ES",
                                "metals_of_interest": ["Pb", "Zn", "Ag"]},
             "opportunity_class": "remediation_led", "class_grade": "B",
             "score": 58, "subscores": {"geological": 45, "logistics": 95,
                                          "environmental": 25, "legal": 50,
                                          "commercial": 58},
             "thesis": "Exhausted district; secondary-recovery candidate.",
             "next_step": "Drop GRID-Arendal CSV; rerun for tailings tag.",
             "evidence_tags": ["nearby_port", "environmental_risk_high"],
             "canonical_sha256": "cafef00d" * 8},
        ],
        "not_a_resource_estimate": True,
    }


# ─── core render checks ────────────────────────────────────────────

class RenderShapeTests(unittest.TestCase):
    def test_self_contained(self):
        html = dossier.render_dossier(_minimal_summary())
        self.assertIn("<style>", html)
        # No remote dependencies.
        self.assertNotIn("<script src=", html)
        self.assertNotIn("<link href=", html)
        self.assertNotIn("https://fonts.", html)

    def test_contains_campaign_name(self):
        html = dossier.render_dossier(_minimal_summary())
        self.assertIn("Iberia Mine-Waste Alpha (test)", html)

    def test_contains_ranking_entries(self):
        html = dossier.render_dossier(_minimal_summary())
        self.assertIn("Galicia W-Sn / Forcarei", html)
        self.assertIn("Cartagena-La Uni", html)  # accent-tolerant

    def test_opportunity_class_labels(self):
        html = dossier.render_dossier(_minimal_summary())
        self.assertIn("extraction_led", html)
        self.assertIn("remediation_led", html)

    def test_disclaimer_present(self):
        html = dossier.render_dossier(_minimal_summary())
        self.assertIn("NOT a resource estimate", html)
        self.assertIn("NOT a financial promise", html)
        self.assertIn("legal title check", html.lower())


# ─── capsule note ───────────────────────────────────────────────────

class CapsuleTests(unittest.TestCase):
    def test_per_aoi_capsule_present(self):
        html = dossier.render_dossier(_minimal_summary())
        self.assertIn("GEASPIRIT_OPPORTUNITY_SCORECARD_V1", html)
        self.assertIn("sha256=deadbeef", html)
        self.assertIn("commercial=76", html)

    def test_campaign_capsule_from_path(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "campaign_summary.canonical.json"
            p.write_bytes(json.dumps(
                _minimal_summary(), sort_keys=True, separators=(",", ":"),
            ).encode("utf-8"))
            html = dossier.render_from_path(p)
        self.assertIn("GEASPIRIT_OPPORTUNITY_CAMPAIGN_V1", html)
        self.assertIn("count=2", html)
        # Source filename surfaced.
        self.assertIn("campaign_summary.canonical.json", html)


# ─── redaction ─────────────────────────────────────────────────────

class RedactionTests(unittest.TestCase):
    def test_redact_strips_per_aoi_coords(self):
        html = dossier.render_dossier(_minimal_summary(), redact_coordinates=True)
        self.assertNotIn("42.6000°N", html)
        self.assertNotIn("-8.3000°E", html)
        self.assertIn("coordinates redacted", html.lower())

    def test_redact_swaps_campaign_capsule_name(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.canonical.json"
            p.write_bytes(json.dumps(_minimal_summary(),
                                      sort_keys=True,
                                      separators=(",", ":")).encode("utf-8"))
            html = dossier.render_from_path(p, redact_coordinates=True)
        # Campaign capsule must say "name=redacted" instead of bracketed name.
        idx = html.find("GEASPIRIT_OPPORTUNITY_CAMPAIGN_V1")
        self.assertGreater(idx, -1)
        capsule_window = html[idx: idx + 400]
        self.assertIn("name=redacted", capsule_window)


# ─── editorial guardrail ───────────────────────────────────────────

class ForbiddenLanguageTests(unittest.TestCase):
    def test_thesis_with_forbidden_phrase_aborts(self):
        s = _minimal_summary()
        s["scorecards"][0]["thesis"] = "Galicia confirmed reserves of W-Sn."
        with self.assertRaises(ValueError):
            dossier.render_dossier(s)

    def test_next_step_with_forbidden_phrase_aborts(self):
        s = _minimal_summary()
        s["scorecards"][1]["next_step"] = "Expect guaranteed return on capex."
        with self.assertRaises(ValueError):
            dossier.render_dossier(s)

    def test_clean_summary_passes(self):
        # A scorecard whose operator-supplied fields are clean must
        # render without raising. We deliberately do NOT substring-
        # scan the rendered HTML for forbidden phrases: the disclaimer
        # itself contains the negated form "NOT a resource estimate"
        # by design.
        html = dossier.render_dossier(_minimal_summary())
        self.assertIn("NOT a resource estimate", html)
        self.assertIn("NOT a financial promise", html)


# ─── input validation ─────────────────────────────────────────────

class InputKindTests(unittest.TestCase):
    def test_per_aoi_scorecard_input_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "single.canonical.json"
            p.write_bytes(json.dumps({
                "schema_version": "opportunity_scorecard.v1",
                "aoi": {"name": "X", "lat": 0, "lon": 0,
                        "radius_km": 10, "country": "ES",
                        "metals_of_interest": ["W"]},
                "opportunity_class": "extraction_led",
                "class_grade": "B+", "score": 70,
                "subscores": {"geological": 60, "logistics": 80,
                              "environmental": 100, "legal": 50,
                              "commercial": 70},
                "thesis": "x", "next_step": "y",
                "evidence_tags": [], "connector_results": [],
                "generated_at": "2026-05-28T00:00:00Z",
                "not_a_resource_estimate": True,
            }, sort_keys=True, separators=(",", ":")).encode("utf-8"))
            with self.assertRaises(ValueError):
                dossier.render_from_path(p)


if __name__ == "__main__":
    unittest.main()
