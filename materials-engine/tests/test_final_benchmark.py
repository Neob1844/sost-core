"""Tests for Phase IV.Q: Final Hierarchical Promotion Benchmark."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.hierarchical_bandgap.final_benchmark import (
    BenchmarkEntry, PromotionScorecard, FinalDecision,
    build_scorecard, make_final_decision, save_all_artifacts,
    BUCKET_RANGES,
)


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   band_gap=None, source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, band_gap=band_gap,
                 has_valid_structure=True,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


# ===== SPEC =====

class TestSpec:
    def test_benchmark_entry(self):
        e = BenchmarkEntry(name="test", overall_mae=0.3)
        json.dumps(e.to_dict())

    def test_scorecard(self):
        s = PromotionScorecard(promote=True, overall_improvement=0.05)
        json.dumps(s.to_dict())

    def test_final_decision(self):
        d = FinalDecision(decision="PROMOTE_HIERARCHICAL_BG")
        json.dumps(d.to_dict())

    def test_bucket_ranges(self):
        assert len(BUCKET_RANGES) == 5
        labels = [b[0] for b in BUCKET_RANGES]
        assert "0.0-0.05" in labels
        assert "0.05-1.0" in labels


# ===== SCORECARD =====

class TestScorecard:
    def _benchmark_promote(self):
        return {"entries": [
            {"role": "production", "name": "prod", "overall_mae": 0.34,
             "bucket_mae": {"0.0-0.05": 0.30, "0.05-1.0": 0.50, "1.0-3.0": 0.85, "3.0-6.0": 1.10, "6.0+": 0.90},
             "bucket_counts": {"0.0-0.05": 1400, "0.05-1.0": 150, "1.0-3.0": 200, "3.0-6.0": 100, "6.0+": 50}},
            {"role": "hierarchical", "name": "hier", "overall_mae": 0.25,
             "bucket_mae": {"0.0-0.05": 0.01, "0.05-1.0": 0.55, "1.0-3.0": 0.70, "3.0-6.0": 0.90, "6.0+": 0.80},
             "bucket_counts": {"0.0-0.05": 1400, "0.05-1.0": 150, "1.0-3.0": 200, "3.0-6.0": 100, "6.0+": 50}},
        ]}

    def _benchmark_hold(self):
        return {"entries": [
            {"role": "production", "name": "prod", "overall_mae": 0.34,
             "bucket_mae": {"0.0-0.05": 0.30, "0.05-1.0": 0.50, "1.0-3.0": 0.85, "3.0-6.0": 1.10, "6.0+": 0.90},
             "bucket_counts": {}},
            {"role": "hierarchical", "name": "hier", "overall_mae": 0.30,
             "bucket_mae": {"0.0-0.05": 0.01, "0.05-1.0": 0.80, "1.0-3.0": 0.85, "3.0-6.0": 1.10, "6.0+": 0.90},
             "bucket_counts": {}},
        ]}

    def test_scorecard_promote(self):
        sc = build_scorecard(self._benchmark_promote())
        assert sc.promote is True
        assert sc.overall_improvement > 0.01
        assert sc.narrow_gap_acceptable  # +0.05 within +0.10 tolerance
        assert sc.metals_preserved

    def test_scorecard_hold_narrow_gap(self):
        sc = build_scorecard(self._benchmark_hold())
        assert sc.promote is False  # narrow gap regressed by +0.30

    def test_decision_promote(self):
        bm = self._benchmark_promote()
        sc = build_scorecard(bm)
        dec = make_final_decision(sc, bm)
        assert dec.decision == "PROMOTE_HIERARCHICAL_BG"
        assert dec.registry_updated is True

    def test_decision_hold(self):
        bm = self._benchmark_hold()
        sc = build_scorecard(bm)
        dec = make_final_decision(sc, bm)
        assert dec.decision == "HOLD_SINGLE_STAGE_BG"
        assert dec.registry_updated is False

    def test_decision_serializable(self):
        bm = self._benchmark_promote()
        sc = build_scorecard(bm)
        dec = make_final_decision(sc, bm)
        json.dumps(dec.to_dict())


# ===== ARTIFACTS =====

class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        bm = {"entries": [
            {"role": "production", "name": "prod", "overall_mae": 0.34, "overall_rmse": 0.73,
             "overall_r2": 0.70, "bucket_mae": {"0.0-0.05": 0.30}, "bucket_counts": {"0.0-0.05": 100},
             "elapsed_sec": 10},
            {"role": "hierarchical", "name": "hier", "overall_mae": 0.25, "overall_rmse": 0.60,
             "overall_r2": 0.78, "bucket_mae": {"0.0-0.05": 0.01}, "bucket_counts": {"0.0-0.05": 100},
             "elapsed_sec": 15},
        ], "sample_size": 200, "seed": 42, "created_at": "now"}
        sc = PromotionScorecard(promote=True, overall_improvement=0.09)
        dec = FinalDecision(decision="PROMOTE_HIERARCHICAL_BG", improvement=0.09)
        save_all_artifacts(bm, sc, dec, output_dir=td)
        for f in ("final_benchmark.json", "final_benchmark.md",
                  "bucket_scorecard.json", "bucket_scorecard.md",
                  "promotion_scorecard.json", "promotion_scorecard.md",
                  "final_decision.json", "final_decision.md"):
            assert os.path.exists(os.path.join(td, f)), f"Missing: {f}"


# ===== API =====

class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        m = _make_material("Si", ["Si"], 227, 0.0, 1.1)
        srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_status(self):
        r = self._client().get("/hierarchical-band-gap-final/status")
        assert r.status_code == 200
        assert r.json()["phase"] == "IV.Q"

    def test_benchmark(self):
        assert self._client().get("/hierarchical-band-gap-final/benchmark").status_code == 200

    def test_scorecard(self):
        assert self._client().get("/hierarchical-band-gap-final/scorecard").status_code == 200

    def test_decision(self):
        assert self._client().get("/hierarchical-band-gap-final/decision").status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/hierarchical-band-gap-regressor/status").status_code == 200
        assert c.get("/hierarchical-band-gap/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "3.1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
