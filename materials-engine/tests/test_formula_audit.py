#!/usr/bin/env python3
"""Formula audit tests — canonical normalization and chemical consistency."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import unittest
from autonomous_discovery.chem_filters import normalize_formula, parse_formula
from material_mixer.generator import formula_from_dict


class TestCanonicalFormula(unittest.TestCase):

    def test_cation_before_anion(self):
        self.assertEqual(normalize_formula("OZn2"), "Zn2O")
        self.assertEqual(normalize_formula("O2Ti"), "TiO2")
        self.assertEqual(normalize_formula("SZn"), "ZnS")
        self.assertEqual(normalize_formula("NaO2Co"), "CoNaO2")

    def test_anion_order(self):
        self.assertEqual(normalize_formula("NSi"), "SiN")
        self.assertEqual(normalize_formula("AsIn"), "InAs")
        self.assertEqual(normalize_formula("AsGa"), "GaAs")
        self.assertEqual(normalize_formula("PIn"), "InP")

    def test_complex_formulas(self):
        self.assertEqual(normalize_formula("O2TiZn"), "TiZnO2")
        self.assertEqual(normalize_formula("LiO2Ti"), "LiTiO2")
        self.assertEqual(normalize_formula("CoO2Rb"), "CoRbO2")
        self.assertEqual(normalize_formula("BaTe3Ti"), "BaTiTe3")

    def test_already_canonical(self):
        self.assertEqual(normalize_formula("GaAs"), "GaAs")
        self.assertEqual(normalize_formula("LiCoO2"), "CoLiO2")  # Li and Co both cations, alphabetical
        self.assertEqual(normalize_formula("ZnO"), "ZnO")
        self.assertEqual(normalize_formula("TiO2"), "TiO2")

    def test_alloys(self):
        # No anion → pure alphabetical
        self.assertEqual(normalize_formula("AlGa"), "AlGa")
        self.assertEqual(normalize_formula("GaIn"), "GaIn")
        self.assertEqual(normalize_formula("GeSi"), "GeSi")

    def test_generator_uses_canonical(self):
        comp = {"Zn": 2, "O": 1}
        self.assertEqual(formula_from_dict(comp), "Zn2O")

        comp2 = {"Ti": 1, "O": 2}
        self.assertEqual(formula_from_dict(comp2), "TiO2")

        comp3 = {"In": 1, "As": 1}
        self.assertEqual(formula_from_dict(comp3), "InAs")


class TestRoundtrip(unittest.TestCase):

    def test_normalize_idempotent(self):
        formulas = ["GaAs", "TiO2", "LiCoO2", "InAs", "SiN", "Zn2O", "BaTiO3"]
        for f in formulas:
            n = normalize_formula(f)
            self.assertEqual(normalize_formula(n), n, f"Not idempotent: {f} → {n}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
