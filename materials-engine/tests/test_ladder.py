"""Tests for training ladder system."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.storage.db import MaterialsDB
from src.training.ladder import RUNGS, SEED, ladder_status


class TestLadderSpec:
    def test_rungs_defined(self):
        assert len(RUNGS) == 5
        sizes = [r["size"] for r in RUNGS]
        assert sizes == [5000, 10000, 20000, 40000, 75993]

    def test_seed_fixed(self):
        assert SEED == 42

    def test_rungs_have_names(self):
        for r in RUNGS:
            assert "name" in r
            assert "size" in r


class TestLadderStatus:
    def test_status_returns_dict(self):
        s = ladder_status()
        assert "rungs" in s

    def test_real_rungs_present(self):
        """After training, real rungs should appear in status."""
        s = ladder_status()
        rung_names = [r["rung"] for r in s["rungs"]]
        # At least rung_5k should exist from the actual training
        assert "rung_5k" in rung_names


class TestRealRungs:
    """Verify actual training artifacts exist."""

    def test_rung_5k_exists(self):
        path = "artifacts/training_ladder/rung_5k/cgcnn_formation_energy_manifest.json"
        assert os.path.exists(path)
        with open(path) as f:
            m = json.load(f)
        assert m["dataset_size"] == 5000
        assert m["test_mae"] > 0

    def test_rung_10k_exists(self):
        path = "artifacts/training_ladder/rung_10k/cgcnn_formation_energy_manifest.json"
        assert os.path.exists(path)
        with open(path) as f:
            m = json.load(f)
        assert m["dataset_size"] == 10000

    def test_rung_20k_exists(self):
        path = "artifacts/training_ladder/rung_20k/cgcnn_formation_energy_manifest.json"
        assert os.path.exists(path)

    def test_rung_20k_alignn_exists(self):
        path = "artifacts/training_ladder/rung_20k/alignn_lite_formation_energy_manifest.json"
        assert os.path.exists(path)

    def test_rung_40k_exists(self):
        path = "artifacts/training_ladder/rung_40k/cgcnn_formation_energy_manifest.json"
        assert os.path.exists(path)

    def test_manifests_have_required_fields(self):
        path = "artifacts/training_ladder/rung_5k/cgcnn_formation_energy_manifest.json"
        with open(path) as f:
            m = json.load(f)
        for field in ["rung_name", "target", "architecture", "dataset_size",
                      "test_mae", "test_rmse", "test_r2", "training_time_sec",
                      "seed", "checkpoint"]:
            assert field in m, f"Missing field: {field}"

    def test_reproducible_seed(self):
        for rung in ["rung_5k", "rung_10k"]:
            path = f"artifacts/training_ladder/{rung}/cgcnn_formation_energy_manifest.json"
            with open(path) as f:
                m = json.load(f)
            assert m["seed"] == 42


class TestBandGapRungs:
    """Verify band_gap training ladder artifacts."""

    def test_bg_rung_5k_exists(self):
        path = "artifacts/training_ladder_band_gap/rung_5k/cgcnn_band_gap_manifest.json"
        assert os.path.exists(path)
        with open(path) as f:
            m = json.load(f)
        assert m["dataset_size"] == 5000
        assert m["test_mae"] > 0

    def test_bg_rung_10k_exists(self):
        path = "artifacts/training_ladder_band_gap/rung_10k/cgcnn_band_gap_manifest.json"
        assert os.path.exists(path)

    def test_bg_rung_20k_cgcnn_exists(self):
        path = "artifacts/training_ladder_band_gap/rung_20k/cgcnn_band_gap_manifest.json"
        assert os.path.exists(path)

    def test_bg_rung_20k_alignn_exists(self):
        path = "artifacts/training_ladder_band_gap/rung_20k/alignn_lite_band_gap_manifest.json"
        assert os.path.exists(path)

    def test_bg_rung_40k_exists(self):
        path = "artifacts/training_ladder_band_gap/rung_40k/cgcnn_band_gap_manifest.json"
        assert os.path.exists(path)

    def test_bg_rung_full_exists(self):
        path = "artifacts/training_ladder_band_gap/rung_full/cgcnn_band_gap_manifest.json"
        assert os.path.exists(path)

    def test_bg_best_is_alignn_20k(self):
        """The promoted band_gap model should be ALIGNN-Lite 20K."""
        path = "artifacts/training/model_registry.json"
        with open(path) as f:
            registry = json.load(f)
        bg_models = [m for m in registry if m["target"] == "band_gap" and m.get("promoted_for_production")]
        assert len(bg_models) == 1
        assert bg_models[0]["model"] == "alignn_lite"
        assert bg_models[0]["dataset_size"] == 20000

    def test_bg_comparison_exists(self):
        path = "artifacts/training_ladder_band_gap/ladder_comparison.json"
        assert os.path.exists(path)
        with open(path) as f:
            d = json.load(f)
        assert d["target"] == "band_gap"
        assert len(d["ladder_results"]) >= 5

    def test_fe_model_not_touched(self):
        """Formation energy model must still be CGCNN 20K."""
        path = "artifacts/training/model_registry.json"
        with open(path) as f:
            registry = json.load(f)
        fe_models = [m for m in registry if m["target"] == "formation_energy" and m.get("promoted_for_production")]
        assert len(fe_models) == 1
        assert fe_models[0]["model"] == "cgcnn"
        assert fe_models[0]["test_mae"] == 0.1528


class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        srv._db = MaterialsDB("materials.db")
        yield
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_ladder_status(self):
        c = self._client()
        r = c.get("/training/ladder/status")
        assert r.status_code == 200
        assert "rungs" in r.json()

    def test_ladder_models(self):
        c = self._client()
        r = c.get("/training/ladder/models")
        assert r.status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "2.8.0"

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/generation/presets").status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
