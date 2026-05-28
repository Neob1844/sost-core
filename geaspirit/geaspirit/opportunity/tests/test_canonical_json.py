"""Canonical JSON must be deterministic across runs and dict orderings."""
from __future__ import annotations

import hashlib
import unittest

from geaspirit.opportunity.canonical import (
    canonical_json, sha256_of_canonical,
)
from geaspirit.opportunity.contracts import AOI, Evidence


class CanonicalDeterminismTests(unittest.TestCase):
    def test_key_order_irrelevant(self):
        a = {"b": 1, "a": 2, "c": 3}
        b = {"c": 3, "a": 2, "b": 1}
        self.assertEqual(canonical_json(a), canonical_json(b))

    def test_float_rounding_stable(self):
        a = {"x": 1.0}
        b = {"x": 1.00000000001}     # 11 decimals — rounded away at 6
        self.assertEqual(canonical_json(a), canonical_json(b))

    def test_dataclass_round_trip_hash_stable(self):
        aoi = AOI(name="x", lat=42.64, lon=-8.35,
                  radius_km=30, country="ES",
                  metals_of_interest=("W", "Sn"))
        h1 = sha256_of_canonical(aoi)
        h2 = sha256_of_canonical(aoi)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_tuple_serialises_as_list(self):
        out = canonical_json({"a": (1, 2, 3)})
        self.assertEqual(out, b'{"a":[1,2,3]}')

    def test_bool_not_coerced_to_float(self):
        out = canonical_json({"b": True})
        self.assertIn(b"true", out)
        self.assertNotIn(b"1.0", out)

    def test_rejects_nan(self):
        with self.assertRaises(ValueError):
            canonical_json({"x": float("nan")})

    def test_evidence_canonical_hash_is_deterministic(self):
        e = Evidence(tag="nearby_road_access",
                     source="OSM",
                     fetched_at="2026-05-28T00:00:00Z",
                     confidence=0.85,
                     license="ODbL-1.0",
                     data={"distance_km": 3.14159265})
        digest = sha256_of_canonical(e)
        # Same evidence → same digest, every time.
        self.assertEqual(digest, sha256_of_canonical(e))


if __name__ == "__main__":
    unittest.main()
