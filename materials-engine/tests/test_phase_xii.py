#!/usr/bin/env python3
"""Phase XII Tests — Physics screening, structure sanity, pre-DFT readiness."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.physics_screening import screen_structure, compute_pre_dft_score
from autonomous_discovery.policy import get_profile


class TestStructureSanity(unittest.TestCase):

    def _get_real_cif(self, formula="GaAs"):
        """Get a real CIF from corpus for testing."""
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), "..", "materials.db")
        if not os.path.exists(db_path):
            return None
        try:
            db = sqlite3.connect(db_path)
            cur = db.cursor()
            cur.execute("SELECT structure_data FROM materials WHERE formula=? AND has_valid_structure=1 LIMIT 1", (formula,))
            row = cur.fetchone()
            db.close()
            return row[0] if row else None
        except Exception:
            return None

    def test_valid_gaas_structure(self):
        cif = self._get_real_cif("GaAs")
        if not cif:
            self.skipTest("No GaAs CIF in corpus")
        r = screen_structure(cif, "GaAs", "III-V semiconductor")
        self.assertGreater(r["structure_sanity_score"], 0.50)
        self.assertTrue(r["bond_distance_sanity"])
        self.assertIsNotNone(r["density"])
        self.assertGreater(r["density"], 2.0)

    def test_valid_tio2_structure(self):
        cif = self._get_real_cif("TiO2")
        if not cif:
            self.skipTest("No TiO2 CIF in corpus")
        r = screen_structure(cif, "TiO2", "Oxide (TiO2 family)")
        self.assertGreater(r["structure_sanity_score"], 0.40)
        self.assertTrue(r["density_sanity"])

    def test_no_cif_returns_zero(self):
        r = screen_structure(None, "XYZ")
        self.assertEqual(r["structure_sanity_score"], 0.0)
        self.assertIn("NO_STRUCTURE_AVAILABLE", r["geometry_warnings"])

    def test_invalid_cif_handled(self):
        r = screen_structure("INVALID CIF DATA", "XYZ")
        self.assertEqual(r["structure_sanity_score"], 0.0)
        self.assertGreater(len(r["geometry_warnings"]), 0)

    def test_physics_flags_populated(self):
        cif = self._get_real_cif("GaAs")
        if not cif:
            self.skipTest("No GaAs CIF")
        r = screen_structure(cif, "GaAs", "III-V semiconductor")
        self.assertIsInstance(r["physics_flags"], list)
        # GaAs should pass sanity
        self.assertIn("STRUCTURE_SANITY_PASS", r["physics_flags"])

    def test_pre_dft_ready_for_good_structure(self):
        cif = self._get_real_cif("GaAs")
        if not cif:
            self.skipTest("No GaAs CIF")
        r = screen_structure(cif, "GaAs", "III-V semiconductor")
        self.assertTrue(r["pre_dft_ready"])


class TestPreDFTScore(unittest.TestCase):

    def test_good_candidate(self):
        phys = {"structure_sanity_score": 0.70, "pre_dft_ready": True}
        unc = {"confidence_score": 0.65}
        ready = {"validation_readiness_score": 0.60}
        scores = {"composite_score": 0.70}
        ctx = {"risk_level": "familiar"}

        r = compute_pre_dft_score(phys, unc, ready, scores, ctx)
        self.assertGreater(r["pre_dft_physics_score"], 0.50)
        self.assertTrue(r["relaxation_candidate"])
        self.assertEqual(r["relaxation_recommendation"], "good_relaxation_candidate")

    def test_bad_geometry(self):
        phys = {"structure_sanity_score": 0.15, "pre_dft_ready": False}
        unc = {"confidence_score": 0.40}
        ready = {"validation_readiness_score": 0.30}
        scores = {"composite_score": 0.40}

        r = compute_pre_dft_score(phys, unc, ready, scores)
        self.assertFalse(r["relaxation_candidate"])
        self.assertIn(r["relaxation_recommendation"], ("unstable_geometry_suspected", "watchlist"))

    def test_needs_repair(self):
        phys = {"structure_sanity_score": 0.45, "pre_dft_ready": False}
        unc = {"confidence_score": 0.55}
        ready = {"validation_readiness_score": 0.50}
        scores = {"composite_score": 0.55}

        r = compute_pre_dft_score(phys, unc, ready, scores)
        self.assertEqual(r["relaxation_recommendation"], "needs_structure_repair")

    def test_chemistry_risk_affects_score(self):
        phys = {"structure_sanity_score": 0.60, "pre_dft_ready": True}
        unc = {"confidence_score": 0.60}
        ready = {"validation_readiness_score": 0.55}
        scores = {"composite_score": 0.60}

        r1 = compute_pre_dft_score(phys, unc, ready, scores, {"risk_level": "familiar"})
        r2 = compute_pre_dft_score(phys, unc, ready, scores, {"risk_level": "risky"})
        self.assertGreater(r1["pre_dft_physics_score"], r2["pre_dft_physics_score"])


class TestProfile(unittest.TestCase):

    def test_physics_screened_exists(self):
        p = get_profile("physics_screened_discovery")
        self.assertTrue(p.get("require_physics_screen", False))
        self.assertGreater(p["weights"]["stability"], 0.3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
