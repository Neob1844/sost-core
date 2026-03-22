"""Tests for Phase IV.R: Three-Tier Band Gap Pipeline."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.hierarchical_bandgap.three_tier import (
    ThreeTierResult, PromotionScorecard, FinalDecision,
    build_scorecard, make_final_decision, save_all_artifacts,
    BUCKET_RANGES,
)
from src.hierarchical_bandgap.narrow_gap import NARROW_LOW, NARROW_HIGH


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   band_gap=None, source="jarvis", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, band_gap=band_gap,
                 has_valid_structure=True,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


class TestSpec:
    def test_narrow_gap_range(self):
        assert NARROW_LOW == 0.05
        assert NARROW_HIGH == 1.0

    def test_three_tier_result(self):
        r = ThreeTierResult(name="test", overall_mae=0.25)
        json.dumps(r.to_dict())

    def test_scorecard(self):
        s = PromotionScorecard(promote=True)
        json.dumps(s.to_dict())

    def test_final_decision(self):
        d = FinalDecision(decision="PROMOTE_THREE_TIER_BG")
        json.dumps(d.to_dict())

    def test_bucket_ranges(self):
        assert len(BUCKET_RANGES) == 5


class TestScorecard:
    def _bm_promote(self):
        return {"entries": {
            "production": {"name": "prod", "overall_mae": 0.34,
                "bucket_mae": {"0.0-0.05": 0.19, "0.05-1.0": 0.51, "1.0-3.0": 0.80, "3.0-6.0": 0.87, "6.0+": 1.67},
                "bucket_counts": {}},
            "two_tier": {"name": "2t", "overall_mae": 0.26,
                "bucket_mae": {"0.0-0.05": 0.09, "0.05-1.0": 0.65, "1.0-3.0": 0.81, "3.0-6.0": 0.81, "6.0+": 0.77},
                "bucket_counts": {}},
            "three_tier": {"name": "3t", "overall_mae": 0.24,
                "bucket_mae": {"0.0-0.05": 0.09, "0.05-1.0": 0.48, "1.0-3.0": 0.81, "3.0-6.0": 0.82, "6.0+": 0.77},
                "bucket_counts": {}},
        }}

    def _bm_hold(self):
        bm = self._bm_promote()
        bm["entries"]["three_tier"]["bucket_mae"]["0.05-1.0"] = 0.70  # still bad
        return bm

    def test_promote(self):
        sc = build_scorecard(self._bm_promote())
        assert sc.promote is True
        assert sc.narrow_gap_acceptable
        assert sc.metals_preserved

    def test_hold_narrow(self):
        sc = build_scorecard(self._bm_hold())
        assert sc.promote is False

    def test_decision_promote(self):
        bm = self._bm_promote()
        sc = build_scorecard(bm)
        dec = make_final_decision(sc, bm)
        assert dec.decision == "PROMOTE_THREE_TIER_BG"
        assert dec.registry_updated

    def test_decision_hold(self):
        bm = self._bm_hold()
        sc = build_scorecard(bm)
        dec = make_final_decision(sc, bm)
        assert dec.decision == "HOLD_SINGLE_STAGE_BG"
        assert not dec.registry_updated

    def test_serializable(self):
        bm = self._bm_promote()
        sc = build_scorecard(bm)
        dec = make_final_decision(sc, bm)
        json.dumps(dec.to_dict())


class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        specialist = {"name": "specialist", "test_mae": 0.35}
        bm = {"entries": {
            "production": {"name": "p", "overall_mae": 0.34, "overall_rmse": 0.68, "overall_r2": 0.77,
                           "bucket_mae": {"0.0-0.05": 0.19}, "bucket_counts": {"0.0-0.05": 100}},
            "two_tier": {"name": "2", "overall_mae": 0.26, "overall_rmse": 0.67, "overall_r2": 0.77,
                         "bucket_mae": {"0.0-0.05": 0.09}, "bucket_counts": {"0.0-0.05": 100}},
            "three_tier": {"name": "3", "overall_mae": 0.24, "overall_rmse": 0.60, "overall_r2": 0.80,
                           "bucket_mae": {"0.0-0.05": 0.09}, "bucket_counts": {"0.0-0.05": 100},
                           "gate_metals": 1400, "gate_narrow": 100, "gate_general": 500},
        }, "sample_size": 2000, "seed": 42, "created_at": "now"}
        sc = PromotionScorecard(promote=True, overall_improvement=0.10)
        dec = FinalDecision(decision="PROMOTE_THREE_TIER_BG", improvement_vs_production=0.10)
        save_all_artifacts(specialist, bm, sc, dec, output_dir=td)
        for f in ("three_tier_pipeline.json", "three_tier_pipeline.md",
                  "bucket_scorecard.json", "bucket_scorecard.md",
                  "final_scorecard.json", "final_scorecard.md",
                  "final_decision.json", "final_decision.md"):
            assert os.path.exists(os.path.join(td, f)), f"Missing: {f}"


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
        r = self._client().get("/three-tier-band-gap/status")
        assert r.status_code == 200
        assert r.json()["phase"] == "IV.R"

    def test_specialist(self):
        assert self._client().get("/three-tier-band-gap/specialist").status_code == 200

    def test_pipeline(self):
        assert self._client().get("/three-tier-band-gap/pipeline").status_code == 200

    def test_scorecard(self):
        assert self._client().get("/three-tier-band-gap/scorecard").status_code == 200

    def test_decision(self):
        assert self._client().get("/three-tier-band-gap/decision").status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/hierarchical-band-gap-final/status").status_code == 200
        assert c.get("/hierarchical-band-gap/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        assert self._client().get("/status").json()["version"] == "3.1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
