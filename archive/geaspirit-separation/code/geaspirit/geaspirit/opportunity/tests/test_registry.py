"""Protocol Registry capsule helper — network-free tests.

We synthesise tiny canonical-shape JSON files on disk, then assert
the registry helper:

  * detects scorecard vs campaign vs neither,
  * embeds the right SHA-256 (computed from the file's bytes),
  * keeps capsule strings single-line and tokenisable,
  * bracket-escapes AOI names with spaces or punctuation,
  * collapses to ``redacted`` when --redact is on,
  * suggests a sost-cli command but does NOT execute it,
  * raises a clear error on the wrong file kind.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from geaspirit.opportunity import registry


def _write_scorecard(td, name="sc.canonical.json", aoi_name="Galicia W-Sn"):
    payload = {
        "schema_version": "opportunity_scorecard.v1",
        "aoi": {"name": aoi_name, "lat": 42.6, "lon": -8.3,
                "radius_km": 30.0, "country": "ES",
                "metals_of_interest": ["W", "Sn"]},
        "opportunity_class": "extraction_led",
        "class_grade": "B+",
        "score": 71,
        "subscores": {"geological": 60, "logistics": 80, "environmental": 100,
                      "legal": 50, "commercial": 71},
        "thesis": "candidate",
        "next_step": "due diligence",
        "evidence_tags": [],
        "connector_results": [],
        "generated_at": "2026-05-28T00:00:00Z",
        "not_a_resource_estimate": True,
    }
    p = Path(td) / name
    p.write_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return p


def _write_campaign(td, name="camp.canonical.json", cname="Iberia"):
    payload = {
        "schema_version": "opportunity_campaign.v1",
        "campaign_name": cname,
        "campaign_description": "",
        "campaign_version": "1",
        "aoi_count": 2,
        "ranking": [],
        "scorecards": [],
        "not_a_resource_estimate": True,
    }
    p = Path(td) / name
    p.write_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return p


class ScorecardCapsuleTests(unittest.TestCase):
    def test_basic_capsule(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_scorecard(td)
            body, _ = registry.build_scorecard_capsule(p)
            expected_sha = hashlib.sha256(p.read_bytes()).hexdigest()
            self.assertIn(f"sha256={expected_sha}", body)
            self.assertTrue(body.startswith(registry.SCORECARD_CAPSULE_PREFIX))
            self.assertIn("not_resource_estimate=true", body)
            self.assertIn("commercial=71", body)
            self.assertIn("class=extraction_led", body)
            # No newlines in the capsule.
            self.assertNotIn("\n", body)

    def test_redact_strips_aoi_name(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_scorecard(td, aoi_name="Cartagena - La Unión")
            body, _ = registry.build_scorecard_capsule(p, redact_aoi=True)
            self.assertIn("aoi=redacted", body)
            self.assertNotIn("Cartagena", body)

    def test_spaces_in_aoi_are_bracketed(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_scorecard(td, aoi_name="Galicia W-Sn / Forcarei")
            body, _ = registry.build_scorecard_capsule(p)
            # The aoi token must remain single, even with spaces inside.
            self.assertIn("aoi=[Galicia W-Sn / Forcarei]", body)

    def test_rejects_non_scorecard(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nope.json"
            p.write_text(json.dumps({"schema_version": "something_else"}),
                         encoding="utf-8")
            with self.assertRaises(ValueError):
                registry.build_scorecard_capsule(p)


class CampaignCapsuleTests(unittest.TestCase):
    def test_basic_campaign_capsule(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_campaign(td)
            body, _ = registry.build_campaign_capsule(p)
            self.assertTrue(body.startswith(registry.CAMPAIGN_CAPSULE_PREFIX))
            self.assertIn("count=2", body)
            self.assertIn("name=Iberia", body)
            self.assertNotIn("\n", body)

    def test_campaign_redact(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_campaign(td, cname="Iberia Mine-Waste Alpha")
            body, _ = registry.build_campaign_capsule(p, redact_name=True)
            self.assertIn("name=redacted", body)
            self.assertNotIn("Iberia", body)


class AutoDetectTests(unittest.TestCase):
    def test_auto_scorecard(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_scorecard(td)
            kind, body, _ = registry.build_capsule(p)
            self.assertEqual(kind, "scorecard")
            self.assertIn("class=extraction_led", body)

    def test_auto_campaign(self):
        with tempfile.TemporaryDirectory() as td:
            p = _write_campaign(td)
            kind, body, _ = registry.build_capsule(p)
            self.assertEqual(kind, "campaign")
            self.assertIn("count=2", body)

    def test_auto_unknown_raises(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.json"
            p.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                registry.build_capsule(p)


class SuggestedCommandTests(unittest.TestCase):
    def test_command_quotes_body(self):
        cmd = registry.suggested_sost_cli_command("FOO sha256=abc count=1")
        self.assertTrue(cmd.startswith("sost-cli registry-note"))
        self.assertIn("'FOO sha256=abc count=1'", cmd)


if __name__ == "__main__":
    unittest.main()
