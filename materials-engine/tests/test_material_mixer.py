"""Tests for Material Mixer MVP."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from material_mixer.generator import generate_candidates, parse_formula, formula_from_dict
from material_mixer.scorer import score_candidate, rank_candidates
from material_mixer.mixer import run_mix


def test_parse_formula():
    assert parse_formula("GaAs") == {"Ga": 1, "As": 1}
    assert parse_formula("TiO2") == {"Ti": 1, "O": 2}
    assert parse_formula("BaTiO3") == {"Ba": 1, "Ti": 1, "O": 3}
    assert parse_formula("Fe2O3") == {"Fe": 2, "O": 3}
    assert parse_formula("Si") == {"Si": 1}


def test_formula_from_dict():
    assert formula_from_dict({"Ga": 1, "As": 1}) == "AsGa"  # sorted
    assert formula_from_dict({"Ti": 1, "O": 2}) == "O2Ti"
    assert formula_from_dict({"Si": 1}) == "Si"


def test_generate_gaas_aln():
    """Classic III-V semiconductor mix."""
    candidates = generate_candidates("GaAs", "AlN")
    assert len(candidates) > 0
    formulas = [c["formula"] for c in candidates]
    # Should not contain parents
    assert "GaAs" not in formulas or "AsGa" not in formulas
    assert "AlN" not in formulas
    # Should have various methods
    methods = set(c["method"] for c in candidates)
    assert len(methods) >= 2


def test_generate_si_ge():
    """Group 14 semiconductor mix."""
    candidates = generate_candidates("Si", "Ge")
    assert len(candidates) > 0
    # Si+Ge should generate mixed/doped variants
    for c in candidates:
        assert "formula" in c
        assert "method" in c
        assert "elements" in c


def test_generate_tio2_zno():
    """Oxide ceramic mix."""
    candidates = generate_candidates("TiO2", "ZnO")
    assert len(candidates) > 0
    for c in candidates:
        assert len(c["elements"]) >= 2
        assert c["parent_a"] == "TiO2"
        assert c["parent_b"] == "ZnO"


def test_no_duplicates():
    """Candidates should have unique formulas."""
    candidates = generate_candidates("GaAs", "AlN")
    formulas = [c["formula"] for c in candidates]
    assert len(formulas) == len(set(formulas))


def test_scoring():
    """Score should return valid structure."""
    candidate = {
        "formula": "AlAs",
        "elements": ["Al", "As"],
        "method": "element_substitution",
    }
    scores = score_candidate(candidate)
    assert 0 <= scores["composite_score"] <= 1
    assert "rarity_label" in scores
    assert scores["confidence"] == "heuristic"


def test_ranking():
    """Ranked candidates should be sorted by composite score."""
    candidates = generate_candidates("GaAs", "AlN")
    ranked = rank_candidates(candidates)
    for i in range(len(ranked) - 1):
        assert ranked[i]["composite_score"] >= ranked[i + 1]["composite_score"]
    assert ranked[0]["rank"] == 1


def test_full_mix():
    """Full mixer run should return valid report."""
    result = run_mix("GaAs", "AlN")
    assert result["parent_a"] == "GaAs"
    assert result["parent_b"] == "AlN"
    assert result["total_candidates"] > 0
    assert "disclaimer" in result
    for c in result["candidates"]:
        assert "rank" in c
        assert "formula" in c
        assert "why_interesting" in c
        assert "risks" in c
        assert "recommended_next_step" in c


def test_empty_input():
    """Should handle invalid inputs gracefully."""
    result = run_mix("", "GaAs")
    assert result["total_candidates"] == 0


def test_honesty():
    """Report should contain honest disclaimers."""
    result = run_mix("TiO2", "ZnO")
    assert "THEORETICAL" in result["disclaimer"]
    assert "validation" in result["disclaimer"].lower()
    for c in result["candidates"]:
        assert c["scores"]["confidence"] == "heuristic"


if __name__ == "__main__":
    tests = [f for f in dir() if f.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            globals()[t]()
            print(f"  PASS: {t}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {t} — {e}")
    print(f"\n{passed}/{len(tests)} tests passed")
