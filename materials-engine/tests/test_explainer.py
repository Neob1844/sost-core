"""Tests for dual-output candidate explainer."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from autonomous_discovery.explainer import explain_candidate

CORPUS = {"Fe2O3", "GaAs", "TiO2", "SiO2", "ZnO", "AlN", "Si", "Ge", "NaCl", "SiC"}


def test_known_material():
    c = {"formula": "Fe2O3", "method": "element_substitution", "parent_a": "Fe2S3", "parent_b": "Al2O3",
         "scores": {"composite_score": 0.55, "plausibility": 0.85, "value": 0.85, "decision": "accepted"}}
    result = explain_candidate(c, CORPUS)
    assert result["technical_report"]["known_or_candidate_status"] == "Known material"
    assert result["plain_language"]["status_category"] == "Known material"
    assert "already" in result["plain_language"]["novelty_clarity"].lower()
    assert result["plain_language"]["known_name_status"].startswith("Has a well-known name")


def test_theoretical_candidate():
    c = {"formula": "FeInO3", "method": "element_substitution", "parent_a": "Fe2O3", "parent_b": "InP",
         "scores": {"composite_score": 0.50, "plausibility": 0.85, "value": 0.62, "novelty": 0.55, "decision": "accepted"}}
    result = explain_candidate(c, CORPUS)
    assert result["technical_report"]["known_or_candidate_status"] == "Theoretical candidate"
    assert "not found" in result["plain_language"]["novelty_clarity"].lower()
    assert "heuristic" in result["plain_language"]["risk_and_uncertainty"][2].lower()


def test_near_known():
    c = {"formula": "Fe3O4", "method": "element_substitution", "parent_a": "Fe2O3", "parent_b": "FeO",
         "scores": {"composite_score": 0.45, "plausibility": 0.7, "decision": "accepted"}}
    # Fe3O4 not in corpus but Fe2O3 is (same elements Fe+O)
    result = explain_candidate(c, CORPUS)
    assert result["technical_report"]["corpus_match"]["near_known_match"] is True


def test_name_detection_known():
    c = {"formula": "GaAs", "method": "test", "parent_a": "", "parent_b": "",
         "scores": {"composite_score": 0.6, "plausibility": 0.9, "decision": "accepted"}}
    result = explain_candidate(c, CORPUS)
    assert result["plain_language"]["known_name_status"].startswith("Has a well-known name")


def test_name_detection_unknown():
    c = {"formula": "AlFeTe3", "method": "test", "parent_a": "", "parent_b": "",
         "scores": {"composite_score": 0.5, "plausibility": 0.8, "decision": "accepted"}}
    result = explain_candidate(c, set())
    assert "No standard" in result["plain_language"]["known_name_status"]


def test_three_summary_formats():
    c = {"formula": "FeInO3", "method": "element_substitution", "parent_a": "Fe2O3", "parent_b": "InP",
         "scores": {"composite_score": 0.50, "plausibility": 0.85, "value": 0.62, "decision": "accepted"}}
    result = explain_candidate(c, CORPUS)
    pl = result["plain_language"]
    assert isinstance(pl["short_summary"], str) and len(pl["short_summary"]) > 10
    assert isinstance(pl["standard_summary"], str) and len(pl["standard_summary"]) > 30
    assert isinstance(pl["extended_summary"], str) and len(pl["extended_summary"]) > 50


def test_honesty_labels():
    c = {"formula": "AlFeSe3", "method": "element_substitution", "parent_a": "Fe2O3", "parent_b": "Al2Se3",
         "scores": {"composite_score": 0.50, "plausibility": 0.80, "decision": "accepted"}}
    result = explain_candidate(c, set())
    pl = result["plain_language"]
    # Must contain honesty markers
    assert "heuristic" in pl["one_paragraph_summary"].lower() or "hypothesis" in pl["one_paragraph_summary"].lower()
    assert any("not" in r.lower() for r in pl["risk_and_uncertainty"])


def test_technical_has_limitations():
    c = {"formula": "Si", "method": "test", "scores": {"decision": "rejected"}, "parent_a": "", "parent_b": ""}
    result = explain_candidate(c, CORPUS)
    assert len(result["technical_report"]["technical_limitations"]) >= 3


def test_origin_explanation():
    c = {"formula": "AlAs", "method": "element_substitution", "parent_a": "GaAs", "parent_b": "AlN",
         "scores": {"composite_score": 0.55, "decision": "accepted"}}
    result = explain_candidate(c, CORPUS)
    assert "GaAs" in result["plain_language"]["origin_explanation"]


if __name__ == "__main__":
    tests = [f for f in dir() if f.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            globals()[t]()
            print(f"  PASS: {t}")
            passed += 1
        except Exception as e:
            print(f"  FAIL: {t} — {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} tests passed")
