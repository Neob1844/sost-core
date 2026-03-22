"""Tests for Validation Pack builder and bridge."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.validation_pack.spec import (
    ValidationPack, NEXT_KEEP_REF, NEXT_WATCH, NEXT_PROXY_REVIEW,
    NEXT_DFT_QUEUE, NEXT_DISCARD, RISK_KNOWN, RISK_GEN_UNVAL,
)
from src.validation_pack.builder import ValidationPackBuilder
from src.frontier.engine import FrontierEngine
from src.frontier.spec import balanced_frontier, stable_semiconductor
from src.validation.queue import ValidationQueue


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


class TestValidationPack:
    def test_to_dict(self):
        p = ValidationPack(formula="Si", frontier_score=0.5,
                           source_type="known_corpus_candidate")
        d = p.to_dict()
        assert d["formula"] == "Si"
        assert d["frontier_score"] == 0.5

    def test_to_summary_row(self):
        p = ValidationPack(formula="Si", frontier_score=0.5,
                           novelty_score=0.3, exotic_score=0.2,
                           recommended_next_step="watch_only")
        row = p.to_summary_row()
        assert row["formula"] == "Si"
        assert row["next_step"] == "watch_only"

    def test_to_markdown(self):
        p = ValidationPack(formula="Si", frontier_score=0.5,
                           frontier_profile="balanced",
                           properties={"formation_energy": {"value": 0.0, "evidence": "known"},
                                       "band_gap": {"value": 1.1, "evidence": "known"}},
                           reason_codes=["strong_stability_signal"],
                           risk_flags=["known_material"])
        md = p.to_markdown()
        assert "Si" in md
        assert "known" in md


class TestBuilder:
    def test_build_from_frontier(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run(profile=balanced_frontier())
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=3)
        assert len(packs) == 3
        for p in packs:
            assert p.formula
            assert p.frontier_score > 0
            assert p.recommended_next_step

    def test_risk_flags(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run()
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=5)
        # Corpus materials should have RISK_KNOWN
        for p in packs:
            assert RISK_KNOWN in p.risk_flags

    def test_next_step_assigned(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run()
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=3)
        valid_steps = {NEXT_KEEP_REF, NEXT_WATCH, NEXT_PROXY_REVIEW,
                       NEXT_DFT_QUEUE, NEXT_DISCARD, "needs_better_structure"}
        for p in packs:
            assert p.recommended_next_step in valid_steps

    def test_human_summary(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run()
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=1)
        assert packs[0].human_summary
        assert "frontier=" in packs[0].human_summary

    def test_build_one(self, test_db, temp_dir):
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        pack = builder.build_one("Si", ["Si"], spacegroup=227)
        assert pack.formula == "Si"
        assert pack.recommended_next_step

    def test_save_batch(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run()
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=3)
        path = builder.save_batch(packs, label="test")
        assert os.path.exists(path)
        md_path = path.replace(".json", ".md")
        assert os.path.exists(md_path)

    def test_export_csv(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run()
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=3)
        csv_path = builder.export_csv(packs)
        assert os.path.exists(csv_path)

    def test_push_to_queue(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run()
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=3)
        queue = ValidationQueue(output_dir=temp_dir)
        qr = builder.push_to_queue(packs, queue)
        assert qr["added"] >= 1
        assert qr["total_in_queue"] >= 1

    def test_dedup_on_push(self, test_db, temp_dir):
        engine = FrontierEngine(test_db, output_dir=temp_dir)
        result = engine.run()
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        packs = builder.build_from_frontier(result, top_k=3)
        queue = ValidationQueue(output_dir=temp_dir)
        builder.push_to_queue(packs, queue)
        # Push same again — should dedup
        qr2 = builder.push_to_queue(packs, queue)
        assert qr2["duplicates"] >= 1

    def test_generated_candidate_risks(self, test_db, temp_dir):
        builder = ValidationPackBuilder(test_db, output_dir=temp_dir)
        pack = builder.build_one("XY", ["Fe", "O"], source_type="generated_hypothesis")
        assert RISK_GEN_UNVAL in pack.risk_flags


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

    def test_build_one(self):
        r = self._client().post("/validation-pack/build-one", json={
            "formula": "Si", "elements": ["Si"]})
        assert r.status_code == 200
        assert "recommended_next_step" in r.json()

    def test_pack_status(self):
        r = self._client().get("/validation-pack/status")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/frontier/presets").status_code == 200
        assert c.get("/generation/presets").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "3.2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
