"""MITECO Catastro Minero connector — disk-only, network-free tests.

Each test points the connector at a fresh temp directory so we never
read the real operator dropbox. We assert:
  * graceful "skipped" when no files are present
  * operator-pasted JSON parses into the right status tag
  * visor GeoJSON parses into the right status tag
  * dominant-status priority works (active beats expired beats clear)
  * out-of-radius records are filtered
  * holders containing "@" are belt-and-braces redacted
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geaspirit.opportunity.contracts import AOI
from geaspirit.opportunity.connectors import miteco_catastro


def _aoi(lat=42.64, lon=-8.35, radius_km=30) -> AOI:
    return AOI(name="Test", lat=lat, lon=lon, radius_km=radius_km,
               country="ES", metals_of_interest=("W", "Sn"))


def _pasted(status, lat=42.64, lon=-8.35, holder="redacted", right_id="X-1"):
    return {
        "version": "miteco_record.v0",
        "records": [{
            "right_id": right_id,
            "name": f"Demo {status}",
            "kind": "concesion_explotacion",
            "section": "C",
            "status": status,
            "holder": holder,
            "centroid": {"lat": lat, "lon": lon},
            "valid_from": "1985-04-12",
            "expires_at": "2015-04-12",
            "source_url": "https://geoportal.minetur.gob.es/CatastroMinero/",
            "imported_at": "2026-05-28T00:00:00Z",
            "confidence": 0.7,
        }],
    }


def _visor_feature(estado, lon=-8.35, lat=42.64, titular="Redacted SL"):
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "properties": {
                "EXPEDIENTE": "PCS-Lugo-3265",
                "NOMBRE":     "Demo right",
                "TIPO":       "Concesion de Explotacion",
                "SECCION":    "C",
                "ESTADO":     estado,
                "TITULAR":    titular,
            },
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
        }],
    }


class _IsolatedRoot:
    """Re-points the connector's _DATA_ROOT at a temp directory."""
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)
        self._patch = patch.object(miteco_catastro, "_DATA_ROOT", self.path)
        self._patch.start()
        return self
    def __exit__(self, *exc):
        self._patch.stop()
        self._tmp.cleanup()
    def write_json(self, name, payload):
        (self.path / name).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class SkippedWhenEmptyTests(unittest.TestCase):
    def test_no_files_yields_skipped(self):
        with _IsolatedRoot():
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.status, "skipped")
        self.assertEqual(r.evidence, ())
        self.assertIn("no MITECO", r.error_message)

    def test_missing_dir_yields_skipped(self):
        with patch.object(miteco_catastro, "_DATA_ROOT",
                          Path("/tmp/does-not-exist-for-miteco-tests-xyz")):
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.status, "skipped")


class PastedJsonTests(unittest.TestCase):
    def test_expired_yields_title_expired(self):
        with _IsolatedRoot() as iso:
            iso.write_json("a.json", _pasted("expired"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.status, "ok")
        self.assertEqual(len(r.evidence), 1)
        self.assertEqual(r.evidence[0].tag, "title_expired")
        self.assertEqual(r.evidence[0].data["dominant_status"], "expired")
        self.assertEqual(r.evidence[0].data["import_mode"], "operator_pasted_json")

    def test_conflicting_yields_title_conflicting(self):
        with _IsolatedRoot() as iso:
            iso.write_json("a.json", _pasted("conflicting"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.evidence[0].tag, "title_conflicting")

    def test_active_third_party_yields_partnership_tag(self):
        with _IsolatedRoot() as iso:
            iso.write_json("a.json", _pasted("active_third_party"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.evidence[0].tag, "title_active_by_third_party")

    def test_out_of_radius_records_are_filtered(self):
        with _IsolatedRoot() as iso:
            # Record placed ~600 km away from the AOI center
            iso.write_json("a.json", _pasted("expired", lat=38.0, lon=-3.5))
            r = miteco_catastro.query(_aoi(radius_km=30))
        self.assertEqual(r.evidence[0].tag, "no_known_titles_in_radius")

    def test_email_in_holder_is_redacted(self):
        with _IsolatedRoot() as iso:
            iso.write_json("a.json", _pasted("expired",
                                              holder="someone@example.com"))
            r = miteco_catastro.query(_aoi())
        hits = r.evidence[0].data["hits"]
        self.assertEqual(hits[0]["holder"], "redacted")


class VisorGeoJsonTests(unittest.TestCase):
    def test_caducado_maps_to_expired(self):
        with _IsolatedRoot() as iso:
            iso.write_json("visor_export.geojson", _visor_feature("Caducado"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.evidence[0].tag, "title_expired")
        self.assertEqual(r.evidence[0].data["import_mode"], "visor_geojson")

    def test_vigente_maps_to_active(self):
        with _IsolatedRoot() as iso:
            iso.write_json("visor_export.geojson", _visor_feature("Vigente"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.evidence[0].tag, "title_active_or_pending")

    def test_wfs_named_file_is_tagged_as_wfs_mode(self):
        with _IsolatedRoot() as iso:
            iso.write_json("miteco_wfs__galicia.geojson",
                           _visor_feature("Vigente"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.evidence[0].data["import_mode"], "official_wfs")


class DominantStatusPriorityTests(unittest.TestCase):
    def test_conflicting_beats_active_beats_expired(self):
        with _IsolatedRoot() as iso:
            iso.write_json("a.json", _pasted("expired", right_id="A"))
            iso.write_json("b.json", _pasted("active", right_id="B"))
            iso.write_json("c.json", _pasted("conflicting", right_id="C"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.evidence[0].tag, "title_conflicting")
        # All three hits surfaced in the payload.
        self.assertEqual(r.evidence[0].data["count"], 3)

    def test_active_beats_expired_when_no_conflict(self):
        with _IsolatedRoot() as iso:
            iso.write_json("a.json", _pasted("expired",  right_id="A"))
            iso.write_json("b.json", _pasted("active",   right_id="B"))
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.evidence[0].tag, "title_active_or_pending")


class GalicianSampleEndToEnd(unittest.TestCase):
    """The shipped sample must parse cleanly when dropped in the
    operator dropbox and produce an actionable evidence tag."""

    def test_sample_loads_and_yields_expired_or_cancelled(self):
        sample = (Path(__file__).resolve()
                  .parent.parent.parent.parent
                  / "data" / "opportunity" / "samples"
                  / "galicia_miteco_sample.json")
        self.assertTrue(sample.exists(),
                        f"missing demo sample at {sample}")
        with _IsolatedRoot() as iso:
            (iso.path / "demo.json").write_text(
                sample.read_text(encoding="utf-8"), encoding="utf-8")
            r = miteco_catastro.query(_aoi())
        self.assertEqual(r.status, "ok")
        # Both demo records are "expired" + "cancelled" → expired wins
        # by priority (expired:50 > cancelled:45 in _STATUS_PRIORITY).
        self.assertEqual(r.evidence[0].tag, "title_expired")
        self.assertEqual(r.evidence[0].data["count"], 2)


if __name__ == "__main__":
    unittest.main()
