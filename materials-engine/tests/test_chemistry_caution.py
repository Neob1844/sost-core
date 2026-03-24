#!/usr/bin/env python3
"""Chemistry caution label tests."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.chemistry_caution import label_candidate


class TestFamilyIdentification(unittest.TestCase):

    def test_known_layered_oxide(self):
        r = label_candidate("CoNaO2")
        self.assertIn("Layered oxide", r["family"])
        self.assertEqual(r["risk_level"], "familiar")

    def test_iii_v_semiconductor(self):
        r = label_candidate("InAs")
        self.assertIn("III-V", r["family"])
        self.assertEqual(r["risk_level"], "familiar")

    def test_cdte_family(self):
        r = label_candidate("CdInTe")
        self.assertIn("CdTe", r["family"])
        self.assertEqual(r["risk_level"], "familiar")

    def test_battery_material(self):
        r = label_candidate("LiTiO2")
        self.assertIn("Battery", r["family"])
        self.assertEqual(r["risk_level"], "familiar")

    def test_nitride_ceramic(self):
        r = label_candidate("SiN")
        self.assertIn("Nitride", r["family"])
        self.assertEqual(r["risk_level"], "familiar")


class TestCautionLabels(unittest.TestCase):

    def test_suboxide_flagged(self):
        r = label_candidate("Zn3O")
        self.assertIn("SUBOXIDE-LIKE", r["caution_labels"])

    def test_alloy_flagged(self):
        r = label_candidate("AlGa")
        self.assertIn("ALLOY-LIKE", r["caution_labels"])

    def test_familiar_no_caution(self):
        r = label_candidate("CoNaO2")
        self.assertIsNone(r["short_caution"])

    def test_complex_composition(self):
        r = label_candidate("BaCdTiZnO4")
        self.assertIn("COMPLEX COMPOSITION", r["caution_labels"])


class TestRiskLevels(unittest.TestCase):

    def test_familiar_risk(self):
        self.assertEqual(label_candidate("GaAs")["risk_level"], "familiar")
        self.assertEqual(label_candidate("InAs")["risk_level"], "familiar")
        self.assertEqual(label_candidate("ZnO")["risk_level"], "familiar")

    def test_plausible_risk(self):
        r = label_candidate("CoLiS2")
        self.assertIn(r["risk_level"], ("familiar", "plausible"))

    def test_unusual_risk(self):
        r = label_candidate("Zr5B")
        self.assertEqual(r["risk_level"], "unusual")

    def test_short_why_populated(self):
        r = label_candidate("GaAs")
        self.assertGreater(len(r["short_why"]), 0)


class TestNoRegression(unittest.TestCase):

    def test_canonical_formulas_labeled(self):
        """All top candidates should get labels without errors."""
        formulas = ["CoNaO2", "Zn2O", "CdInTe", "CdSeTe", "CoLiS2",
                     "InAs", "SiN", "CdCuTe", "CoKO2", "CoRbO2"]
        for f in formulas:
            r = label_candidate(f)
            self.assertIsNotNone(r["risk_level"])
            self.assertIsInstance(r["caution_labels"], list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
