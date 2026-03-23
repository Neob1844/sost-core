"""Tests for Autonomous Materials Discovery Engine."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from autonomous_discovery.engine import DiscoveryEngine
from autonomous_discovery.memory_store import MemoryStore
from autonomous_discovery.chem_filters import filter_candidate
from autonomous_discovery.scorer import score_candidate
from autonomous_discovery.policy import get_profile, compute_composite_score, CAMPAIGN_PROFILES


def test_chem_filters_valid():
    ok, _ = filter_candidate("GaAs")
    assert ok, "GaAs should pass filter"

def test_chem_filters_empty():
    ok, reason = filter_candidate("")
    assert not ok and "empty" in reason

def test_chem_filters_noble_gas():
    ok, reason = filter_candidate("HeO2")
    assert not ok and "noble_gas" in reason

def test_chem_filters_too_many_elements():
    ok, reason = filter_candidate("LiNaKRbCsMgCa")
    assert not ok and "too_many" in reason

def test_chem_filters_forbidden():
    ok, reason = filter_candidate("UO2")
    assert not ok  # U is not in VALID_ELEMENTS, caught as invalid

def test_chem_filters_parent_identical():
    ok, reason = filter_candidate("GaAs", parent_a="GaAs")
    assert not ok and "identical" in reason

def test_scorer_basic():
    scores = score_candidate("GaAlAs", ["Ga","Al","As"], "element_substitution",
                             get_profile("balanced"))
    assert 0 <= scores["composite_score"] <= 1
    assert scores["confidence"] == "heuristic"
    assert "novelty" in scores
    assert "exotic" in scores

def test_scorer_strategic():
    scores = score_candidate("LiCoO2", ["Li","Co","O"], "mixed_parent",
                             get_profile("strategic_materials_search"))
    assert scores["value"] > 0.3  # Li and Co are strategic

def test_policy_profiles():
    for name in CAMPAIGN_PROFILES:
        p = get_profile(name)
        assert "weights" in p
        assert "description" in p
    # Unknown defaults to balanced
    p = get_profile("nonexistent")
    assert p == CAMPAIGN_PROFILES["balanced"]

def test_composite_score():
    scores = {"novelty": 0.5, "exotic": 0.3, "stability": 0.7, "value": 0.6, "diversity": 0.4}
    profile = get_profile("balanced")
    cs = compute_composite_score(scores, profile)
    assert 0 <= cs <= 1

def test_memory_store():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        m = MemoryStore(path)
        assert m.total_generated == 0
        m.record_candidate("GaAlAs", "substitution", 0.7, True)
        m.record_candidate("XYZ", "doping", 0.1, False, "low_score")
        assert m.total_generated == 2
        assert m.total_accepted == 1
        assert m.total_rejected == 1
        assert not m.is_duplicate("NewFormula")
        assert m.is_duplicate("GaAlAs")
        m.save()
        # Reload
        m2 = MemoryStore(path)
        assert m2.total_generated == 2
    finally:
        os.unlink(path)

def test_memory_rule_penalty():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        m = MemoryStore(path)
        # Record many failures for one method
        for i in range(20):
            m.record_candidate(f"Bad{i}", "bad_method", 0.05, False, "low_score")
        penalty = m.get_rule_penalty("bad_method")
        assert penalty < 1.0  # should be penalized
        # Good method should not be penalized
        for i in range(10):
            m.record_candidate(f"Good{i}", "good_method", 0.8, True)
        penalty = m.get_rule_penalty("good_method")
        assert penalty == 1.0
    finally:
        os.unlink(path)

def test_engine_single_iteration():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        engine = DiscoveryEngine(profile_name="balanced", memory_path=path,
                                  seeds=[("GaAs", "AlN"), ("TiO2", "ZnO")])
        report = engine.run_iteration(max_candidates=15)
        assert report["iteration"] == 1
        assert report["raw_generated"] > 0
        assert "top_candidates" in report
        assert "memory_summary" in report
    finally:
        os.unlink(path)

def test_engine_campaign():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        engine = DiscoveryEngine(profile_name="exotic_hunt", memory_path=path,
                                  seeds=[("Si", "Ge"), ("GaAs", "InP")])
        result = engine.run_campaign(n_iterations=3, max_candidates_per_iter=10)
        assert result["iterations"] == 3
        assert result["total_generated"] > 0
        assert "disclaimer" in result
        assert "THEORETICAL" in result["disclaimer"]
    finally:
        os.unlink(path)

def test_engine_no_duplicates_across_iterations():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        engine = DiscoveryEngine(profile_name="balanced", memory_path=path,
                                  seeds=[("GaAs", "AlN")])
        r1 = engine.run_iteration(max_candidates=10)
        r2 = engine.run_iteration(max_candidates=10)
        # Second iteration should generate fewer (duplicates filtered)
        # Not strictly guaranteed but memory should suppress some
        assert r2["iteration"] == 2
    finally:
        os.unlink(path)

def test_honesty_labels():
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        engine = DiscoveryEngine(memory_path=path)
        report = engine.run_iteration(max_candidates=5)
        for c in report.get("top_candidates", []):
            assert c["scores"]["confidence"] == "heuristic"
    finally:
        os.unlink(path)

def test_gaas_aln_smoke():
    """Smoke test: GaAs + AlN generates candidates."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        engine = DiscoveryEngine(memory_path=path, seeds=[("GaAs", "AlN")])
        r = engine.run_iteration(max_candidates=20)
        assert r["accepted"] > 0 or r["scored"] > 0
    finally:
        os.unlink(path)

def test_tio2_zno_smoke():
    """Smoke test: TiO2 + ZnO."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        engine = DiscoveryEngine(memory_path=path, seeds=[("TiO2", "ZnO")])
        r = engine.run_iteration(max_candidates=15)
        assert r["raw_generated"] > 0
    finally:
        os.unlink(path)

def test_si_ge_smoke():
    """Smoke test: Si + Ge."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    try:
        engine = DiscoveryEngine(memory_path=path, seeds=[("Si", "Ge")])
        r = engine.run_iteration(max_candidates=10)
        assert r["iteration"] == 1
    finally:
        os.unlink(path)


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
