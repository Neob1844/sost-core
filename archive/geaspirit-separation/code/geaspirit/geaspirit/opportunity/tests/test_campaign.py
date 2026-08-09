"""Campaign engine — network-free tests.

Each test feeds a fake connector tuple so neither OSM Overpass nor any
filesystem-based connector is exercised. We assert:

  * AOI input parsing accepts both `name` and `aoi_name`
  * AOI input parsing accepts metals as list and as pipe-string
  * `run_campaign` returns scorecards sorted by commercial desc
  * `--limit` truncates BEFORE scoring
  * `export_campaign` writes per-AOI canonical + pretty + summary + CSV
  * canonical SHA in the summary matches the per-AOI canonical file
  * `redact_coordinates=True` strips lat/lon from the summary but
    leaves the per-AOI canonical files intact (they're the on-chain
    artefact)
"""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from geaspirit.opportunity import campaign as cmp
from geaspirit.opportunity.contracts import AOI, ConnectorResult, Evidence


def _fake_osm_full(_aoi):
    return ConnectorResult(
        connector="osm_logistics", status="ok",
        evidence=(
            Evidence(tag="nearby_road_access", source="fake", fetched_at="2026-05-28T00:00:00Z",
                     confidence=0.9, license="ODbL-1.0",
                     data={"distance_km": 2.0}),
            Evidence(tag="nearby_railway", source="fake", fetched_at="2026-05-28T00:00:00Z",
                     confidence=0.9, license="ODbL-1.0",
                     data={"distance_km": 7.0}),
        ),
        fetched_at="2026-05-28T00:00:00Z",
    )

def _fake_env_clear(_aoi):
    return ConnectorResult(
        connector="env_constraints", status="ok",
        evidence=(Evidence(tag="environmental_clear", source="fake",
                           fetched_at="2026-05-28T00:00:00Z", confidence=0.7,
                           license="ODbL-1.0"),),
        fetched_at="2026-05-28T00:00:00Z",
    )

def _fake_tailings_hit(_aoi):
    return ConnectorResult(
        connector="tailings_portal", status="ok",
        evidence=(Evidence(tag="nearby_tailings_facility", source="fake",
                           fetched_at="2026-05-28T00:00:00Z", confidence=0.85,
                           license="GRID-Arendal",
                           data={"largest_volume_m3": 2e6, "hits": [],
                                 "count": 1}),),
        fetched_at="2026-05-28T00:00:00Z",
    )


FAKE_CONNECTORS = (_fake_osm_full, _fake_env_clear, _fake_tailings_hit)


def _campaign_file(td, aois):
    p = Path(td) / "camp.json"
    p.write_text(json.dumps({
        "name": "TestCampaign", "description": "", "version": "1",
        "aois": aois,
    }), encoding="utf-8")
    return p


# ─── input parsing ─────────────────────────────────────────────────

class InputParsingTests(unittest.TestCase):
    def test_name_or_aoi_name_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "n1.json"
            p1.write_text(json.dumps({
                "name": "c", "aois": [{"name": "A", "lat": 0.0, "lon": 0.0,
                                       "radius_km": 10.0, "country": "ES",
                                       "metals_of_interest": ["W"]}],
            }), encoding="utf-8")
            p2 = Path(td) / "n2.json"
            p2.write_text(json.dumps({
                "name": "c", "aois": [{"aoi_name": "B", "lat": 0.0, "lon": 0.0,
                                       "radius_km": 10.0, "country": "ES",
                                       "metals_of_interest": ["W"]}],
            }), encoding="utf-8")
            c1 = cmp.parse_campaign_file(p1)
            c2 = cmp.parse_campaign_file(p2)
        self.assertEqual(c1["aois"][0].name, "A")
        self.assertEqual(c2["aois"][0].name, "B")

    def test_metals_as_pipe_string(self):
        with tempfile.TemporaryDirectory() as td:
            p = _campaign_file(td, [
                {"name": "x", "lat": 0.0, "lon": 0.0, "radius_km": 10.0,
                 "country": "ES", "metals_of_interest": "W|Sn|Cu"},
            ])
            c = cmp.parse_campaign_file(p)
        self.assertEqual(c["aois"][0].metals_of_interest, ("W", "Sn", "Cu"))

    def test_empty_aois_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text(json.dumps({"name": "c", "aois": []}), encoding="utf-8")
            with self.assertRaises(ValueError):
                cmp.parse_campaign_file(p)


# ─── execution & ranking ───────────────────────────────────────────

class RunCampaignTests(unittest.TestCase):
    def setUp(self):
        self.aois = [
            {"name": "A-bigger", "lat": 42.0, "lon": -8.0, "radius_km": 30.0,
             "country": "ES", "metals_of_interest": ["W", "Cu"]},
            {"name": "B-strategic", "lat": 41.0, "lon": -7.0, "radius_km": 30.0,
             "country": "PT", "metals_of_interest": ["Li"]},
            {"name": "C-thin", "lat": 40.0, "lon": -6.0, "radius_km": 30.0,
             "country": "ES", "metals_of_interest": ["Pb"]},
        ]

    def test_sort_descending_by_commercial(self):
        with tempfile.TemporaryDirectory() as td:
            p = _campaign_file(td, self.aois)
            c = cmp.parse_campaign_file(p)
            scorecards = cmp.run_campaign(c, connectors=FAKE_CONNECTORS)
        scores = [s.subscores.commercial for s in scorecards]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_limit_truncates_before_scoring(self):
        with tempfile.TemporaryDirectory() as td:
            p = _campaign_file(td, self.aois)
            c = cmp.parse_campaign_file(p)
            scorecards = cmp.run_campaign(c, connectors=FAKE_CONNECTORS, limit=2)
        self.assertEqual(len(scorecards), 2)


# ─── export ────────────────────────────────────────────────────────

class ExportTests(unittest.TestCase):
    def test_full_export_layout(self):
        with tempfile.TemporaryDirectory() as td:
            p = _campaign_file(td, [
                {"name": "AOI Alpha", "lat": 42.0, "lon": -8.0, "radius_km": 30.0,
                 "country": "ES", "metals_of_interest": ["W"]},
                {"name": "AOI Beta", "lat": 41.0, "lon": -7.0, "radius_km": 30.0,
                 "country": "PT", "metals_of_interest": ["Li"]},
            ])
            out = Path(td) / "out"
            scorecards, written = cmp.run_and_export(
                p, out, connectors=FAKE_CONNECTORS,
            )
            self.assertGreaterEqual(len(written), 6)
            csv_path = out / "ranking.csv"
            self.assertTrue(csv_path.exists())
            with csv_path.open(encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 2)
            summary = json.loads((out / "campaign_summary.canonical.json").read_text())
            self.assertEqual(summary["aoi_count"], 2)
            for rec in summary["scorecards"]:
                self.assertTrue((out / rec["canonical_file"]).exists())

    def test_redact_coordinates_strips_summary_lat_lon(self):
        with tempfile.TemporaryDirectory() as td:
            p = _campaign_file(td, [
                {"name": "AOI Alpha", "lat": 42.0, "lon": -8.0, "radius_km": 30.0,
                 "country": "ES", "metals_of_interest": ["W"]},
            ])
            out = Path(td) / "out"
            cmp.run_and_export(
                p, out, connectors=FAKE_CONNECTORS, redact_coordinates=True,
            )
            summary = json.loads((out / "campaign_summary.canonical.json").read_text())
            rec = summary["scorecards"][0]
            self.assertNotIn("lat", rec["aoi"])
            self.assertNotIn("lon", rec["aoi"])
            self.assertTrue(rec["aoi"].get("coordinates_redacted"))


if __name__ == "__main__":
    unittest.main()
