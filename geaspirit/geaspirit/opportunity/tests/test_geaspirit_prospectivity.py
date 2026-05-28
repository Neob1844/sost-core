"""GeaSpirit prospectivity bridge connector — disk-only tests.

Each test redirects the connector's _DATA_ROOT to a fresh tmp dir so
we never read the real operator dropbox. We assert:

  * graceful "skipped" when no dropbox exists
  * graceful "skipped" when dropbox is empty
  * JSON parse: envelope form (records[] under "records")
  * JSON parse: bare list-of-records form
  * CSV parse with pipe-separated signals
  * radius filter drops far-away records
  * score band thresholds (high / medium / low)
  * unknown signal families do not emit signal tags
  * union of signal families across records
  * score auto-normalisation (0..1 vs 0..100)
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geaspirit.opportunity.contracts import AOI
from geaspirit.opportunity.connectors import geaspirit_prospectivity


def _aoi(lat=42.6364, lon=-8.3486, radius=30.0):
    return AOI(
        name="Test AOI", lat=lat, lon=lon, radius_km=radius,
        country="ES", metals_of_interest=("W", "Sn"),
    )


class SkippedWhenEmptyTests(unittest.TestCase):
    def test_missing_dir_yields_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            missing = Path(td) / "does_not_exist"
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", missing):
                r = geaspirit_prospectivity.query(_aoi())
        self.assertEqual(r.status, "skipped")
        self.assertEqual(r.evidence, ())

    def test_empty_dir_yields_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        self.assertEqual(r.status, "skipped")


class JsonEnvelopeTests(unittest.TestCase):
    def _write(self, td, name, payload):
        p = Path(td) / name
        p.write_text(json.dumps(payload), encoding="utf-8")
        return p

    def test_envelope_form(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, "demo.json", {
                "version": "geaspirit_prospectivity.v1",
                "default_confidence": 0.6,
                "license_notes": "demo",
                "records": [
                    {"aoi_name": "near", "lat": 42.6, "lon": -8.35,
                     "score": 0.85, "signals": ["spectral", "geophysics"]},
                ],
            })
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        self.assertEqual(r.status, "ok")
        tags = sorted(e.tag for e in r.evidence)
        self.assertIn("geaspirit_prospectivity_high", tags)
        self.assertIn("geaspirit_signal_spectral", tags)
        self.assertIn("geaspirit_signal_geophysics", tags)

    def test_bare_list_form(self):
        with tempfile.TemporaryDirectory() as td:
            self._write(td, "bare.json", [
                {"aoi_name": "near", "lat": 42.65, "lon": -8.30,
                 "score": 55, "signals": ["thermal"]},
            ])
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        tags = sorted(e.tag for e in r.evidence)
        self.assertIn("geaspirit_prospectivity_medium", tags)
        self.assertIn("geaspirit_signal_thermal", tags)


class CsvTests(unittest.TestCase):
    def _write_csv(self, td, name, body):
        p = Path(td) / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_csv_pipe_separated_signals(self):
        body = (
            "aoi_name,lat,lon,radius_km,score,score_type,confidence,model,source,signals,notes\n"
            'Forcarei,42.63,-8.35,5,0.72,heuristic,0.7,GeaSpirit Phase 27,'
            'analyze_custom_aois.py,spectral|terrain,demo\n'
        )
        with tempfile.TemporaryDirectory() as td:
            self._write_csv(td, "demo.csv", body)
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        tags = sorted(e.tag for e in r.evidence)
        self.assertIn("geaspirit_prospectivity_high", tags)
        self.assertIn("geaspirit_signal_spectral", tags)
        self.assertIn("geaspirit_signal_terrain", tags)


class RadiusFilterTests(unittest.TestCase):
    def test_out_of_radius_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "far.json").write_text(json.dumps([
                {"aoi_name": "Africa", "lat": -1.0, "lon": 30.0, "score": 0.9},
            ]), encoding="utf-8")
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        self.assertEqual(r.status, "ok")
        self.assertEqual(r.evidence, ())


class BandThresholdTests(unittest.TestCase):
    def _one(self, score):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "x.json").write_text(json.dumps([
                {"aoi_name": "n", "lat": 42.64, "lon": -8.35, "score": score},
            ]), encoding="utf-8")
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                return geaspirit_prospectivity.query(_aoi())

    def test_high_threshold_exact(self):
        r = self._one(70)
        self.assertIn("geaspirit_prospectivity_high",
                      {e.tag for e in r.evidence})

    def test_medium_band(self):
        r = self._one(50)
        self.assertIn("geaspirit_prospectivity_medium",
                      {e.tag for e in r.evidence})

    def test_low_band(self):
        r = self._one(0.20)
        self.assertIn("geaspirit_prospectivity_low",
                      {e.tag for e in r.evidence})


class SignalFamilyHonestyTests(unittest.TestCase):
    def test_unknown_family_no_tag(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "x.json").write_text(json.dumps([
                {"aoi_name": "n", "lat": 42.64, "lon": -8.35,
                 "score": 0.8, "signals": ["unicorn-magic"]},
            ]), encoding="utf-8")
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        tags = {e.tag for e in r.evidence}
        self.assertIn("geaspirit_prospectivity_high", tags)
        for t in tags:
            self.assertFalse(t.startswith("geaspirit_signal_unicorn"),
                             f"unknown family leaked into tag {t!r}")

    def test_union_across_records(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "x.json").write_text(json.dumps([
                {"aoi_name": "a", "lat": 42.64, "lon": -8.35,
                 "score": 0.8, "signals": ["spectral"]},
                {"aoi_name": "b", "lat": 42.66, "lon": -8.40,
                 "score": 0.5, "signals": ["terrain"]},
            ]), encoding="utf-8")
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        tags = {e.tag for e in r.evidence}
        self.assertIn("geaspirit_signal_spectral", tags)
        self.assertIn("geaspirit_signal_terrain", tags)


class ScoreNormalisationTests(unittest.TestCase):
    def test_0_to_1_auto_promoted(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "x.json").write_text(json.dumps([
                {"aoi_name": "n", "lat": 42.64, "lon": -8.35, "score": 0.85},
            ]), encoding="utf-8")
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        band = [e for e in r.evidence
                if e.tag.startswith("geaspirit_prospectivity_")][0]
        self.assertEqual(band.tag, "geaspirit_prospectivity_high")
        self.assertGreaterEqual(band.data["max_score"], 70.0)

    def test_0_to_100_passes_through(self):
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "x.json").write_text(json.dumps([
                {"aoi_name": "n", "lat": 42.64, "lon": -8.35, "score": 85},
            ]), encoding="utf-8")
            with patch.object(geaspirit_prospectivity, "_DATA_ROOT", Path(td)):
                r = geaspirit_prospectivity.query(_aoi())
        band = [e for e in r.evidence
                if e.tag.startswith("geaspirit_prospectivity_")][0]
        self.assertEqual(band.tag, "geaspirit_prospectivity_high")


if __name__ == "__main__":
    unittest.main()
