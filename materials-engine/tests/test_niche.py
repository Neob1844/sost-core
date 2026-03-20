"""Tests for Niche Discovery Campaign Engine."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.niche.spec import (
    NicheCampaignSpec, ALL_NICHE_PRESETS,
    stable_semiconductor_hunt, wide_gap_exotic_hunt, high_novelty_watchlist,
    TAG_STABLE_SEMI, TAG_WIDE_GAP, TAG_BUDGET,
)
from src.niche.engine import NicheCampaignEngine


def _make_material(formula, elements, spacegroup=None, band_gap=None,
                   formation_energy=None, source="test", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 band_gap=band_gap, formation_energy=formation_energy,
                 has_valid_structure=True, source=source,
                 source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("Si", ["Si"], 227, 1.1, 0.0),
    _make_material("GaAs", ["As", "Ga"], 216, 1.4, -0.7),
    _make_material("NaCl", ["Cl", "Na"], 225, 8.5, -4.2),
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5),
    _make_material("TiO2", ["O", "Ti"], 136, 3.2, -3.4),
]


@pytest.fixture
def test_db():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    db = MaterialsDB(f.name)
    for m in CORPUS:
        db.insert_material(m)
    yield db
    os.unlink(f.name)


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


class TestPresets:
    def test_all_presets_have_name(self):
        for name, fn in ALL_NICHE_PRESETS.items():
            spec = fn()
            assert spec.name == name

    def test_stable_semi_has_bg_target(self):
        s = stable_semiconductor_hunt()
        assert s.band_gap_target == 1.5
        assert TAG_STABLE_SEMI in s.niche_tags

    def test_wide_gap_tags(self):
        s = wide_gap_exotic_hunt()
        assert TAG_WIDE_GAP in s.niche_tags

    def test_campaign_id_deterministic(self):
        s = stable_semiconductor_hunt()
        assert s.campaign_id() == s.campaign_id()

    def test_serialization(self):
        s = high_novelty_watchlist()
        d = s.to_dict()
        s2 = NicheCampaignSpec.from_dict(d)
        assert s2.name == s.name


class TestEngine:
    def test_run_campaign(self, test_db, temp_dir):
        engine = NicheCampaignEngine(test_db, output_dir=temp_dir)
        result = engine.run(stable_semiconductor_hunt())
        assert "campaign_id" in result
        assert "summary" in result
        assert "candidates" in result
        assert "disclaimer" in result

    def test_niche_tags_assigned(self, test_db, temp_dir):
        engine = NicheCampaignEngine(test_db, output_dir=temp_dir)
        result = engine.run(wide_gap_exotic_hunt())
        for c in result["candidates"]:
            assert TAG_WIDE_GAP in c["niche_tags"]

    def test_run_and_save(self, test_db, temp_dir):
        engine = NicheCampaignEngine(test_db, output_dir=temp_dir)
        result, path = engine.run_and_save(stable_semiconductor_hunt())
        assert os.path.exists(path)
        md_path = path.replace(".json", ".md")
        assert os.path.exists(md_path)

    def test_run_batch(self, test_db, temp_dir):
        engine = NicheCampaignEngine(test_db, output_dir=temp_dir)
        specs = [stable_semiconductor_hunt(), wide_gap_exotic_hunt()]
        results = engine.run_batch(specs)
        assert len(results) == 2

    def test_compare(self, test_db, temp_dir):
        engine = NicheCampaignEngine(test_db, output_dir=temp_dir)
        r1 = engine.run(stable_semiconductor_hunt())
        r2 = engine.run(wide_gap_exotic_hunt())
        comp = engine.compare([r1, r2])
        assert "comparison" in comp
        assert len(comp["comparison"]) == 2
        for row in comp["comparison"]:
            assert "signal_ratio" in row

    def test_summary_fields(self, test_db, temp_dir):
        engine = NicheCampaignEngine(test_db, output_dir=temp_dir)
        result = engine.run(stable_semiconductor_hunt())
        s = result["summary"]
        assert "total_evaluated" in s
        assert "decisions" in s
        assert "top_reasons" in s
        assert "top_risks" in s

    def test_list_runs(self, test_db, temp_dir):
        engine = NicheCampaignEngine(test_db, output_dir=temp_dir)
        engine.run_and_save(stable_semiconductor_hunt())
        runs = engine.list_runs()
        assert len(runs) >= 1


class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        for m in CORPUS:
            srv._db.insert_material(m)
        yield
        os.unlink(f.name)
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_presets(self):
        r = self._client().get("/niche/presets")
        assert r.status_code == 200
        assert "stable_semiconductor_hunt" in r.json()["presets"]

    def test_run(self):
        r = self._client().post("/niche/run", json={
            "preset": "stable_semiconductor_hunt", "pool_limit": 5})
        assert r.status_code == 200
        assert "campaign_id" in r.json()

    def test_status(self):
        r = self._client().get("/niche/status")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/frontier/presets").status_code == 200
        assert c.get("/triage/presets").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.5.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
