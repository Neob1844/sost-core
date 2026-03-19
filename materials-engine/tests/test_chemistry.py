"""Tests for robust chemical formula parsing."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.normalization.chemistry import parse_formula


def test_simple_formula():
    elems, method = parse_formula("Fe2O3")
    assert set(elems) == {"Fe", "O"}
    assert method in ("pymatgen", "regex_fallback")


def test_complex_with_parens():
    elems, method = parse_formula("Ca(OH)2")
    assert "Ca" in elems
    assert "O" in elems
    assert "H" in elems


def test_single_element():
    elems, method = parse_formula("Cu")
    assert elems == ["Cu"]


def test_hydrated():
    elems, method = parse_formula("CuSO4·5H2O")
    # pymatgen may or may not parse the dot; regex will extract Cu,S,O,H
    assert "Cu" in elems or "S" in elems


def test_empty():
    elems, method = parse_formula("")
    assert elems == []
    assert method == "empty"


def test_unparseable():
    elems, method = parse_formula("???!!!###")
    assert method in ("failed", "regex_fallback")


def test_perovskite():
    elems, method = parse_formula("BaTiO3")
    assert set(elems) == {"Ba", "Ti", "O"}


def test_alloy():
    elems, method = parse_formula("Ni3Al")
    assert "Ni" in elems
    assert "Al" in elems


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
