"""Tests for Phase IV.U: Public Demo + Operational Acceptance."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.release.demo import (
    generate_demo_surface, generate_golden_workflows,
    generate_acceptance_checklist, generate_release_notes,
    save_all_demo_artifacts,
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


class TestDemoSurface:
    def test_structure(self):
        ds = generate_demo_surface()
        assert "demo_endpoints" in ds
        assert len(ds["demo_endpoints"]) >= 10
        assert "do_not_demo" in ds
        json.dumps(ds)

    def test_endpoints_have_fields(self):
        for ep in generate_demo_surface()["demo_endpoints"]:
            assert "method" in ep
            assert "path" in ep
            assert "purpose" in ep


class TestGoldenWorkflows:
    def test_count(self):
        wf = generate_golden_workflows()
        assert len(wf) == 5

    def test_structure(self):
        for w in generate_golden_workflows():
            assert "name" in w
            assert "steps" in w
            assert "value" in w
            assert len(w["steps"]) >= 1
        json.dumps(generate_golden_workflows())


class TestAcceptance:
    def test_checklist(self):
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        db.insert_material(_make_material("Si", ["Si"], 227, 0.0, 1.1))
        ac = generate_acceptance_checklist(db)
        assert ac["overall"] in ("ACCEPTED", "CONDITIONAL")
        assert ac["total_checks"] > 0
        assert "checks" in ac
        json.dumps(ac)
        os.unlink(f.name)


class TestReleaseNotes:
    def test_content(self):
        notes = generate_release_notes()
        assert "3.2.0" in notes
        assert "Formation Energy" in notes
        assert "Band Gap" in notes
        assert "76,193" in notes


class TestArtifacts:
    def test_save_all(self):
        td = tempfile.mkdtemp()
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        db = MaterialsDB(f.name)
        db.insert_material(_make_material("Si", ["Si"], 227, 0.0, 1.1))
        ds = generate_demo_surface()
        wf = generate_golden_workflows()
        ac = generate_acceptance_checklist(db)
        rn = generate_release_notes()
        save_all_demo_artifacts(ds, wf, ac, rn, output_dir=td)
        for fname in ("public_demo_surface.json", "public_demo_surface.md",
                      "golden_workflows.json", "golden_workflows.md",
                      "operational_acceptance.json", "operational_acceptance.md",
                      "release_notes_v3_2_rc1.md"):
            assert os.path.exists(os.path.join(td, fname)), f"Missing: {fname}"
        os.unlink(f.name)


class TestAPI:
    @pytest.fixture(autouse=True)
    def setup(self):
        import src.api.server as srv
        f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        f.close()
        srv._db = MaterialsDB(f.name)
        srv._db.insert_material(_make_material("Si", ["Si"], 227, 0.0, 1.1))
        yield
        os.unlink(f.name)
        srv._db = None

    def _client(self):
        from fastapi.testclient import TestClient
        from src.api.server import app
        return TestClient(app)

    def test_demo_surface(self):
        assert self._client().get("/release/demo-surface").status_code == 200

    def test_golden_workflows(self):
        assert self._client().get("/release/golden-workflows").status_code == 200

    def test_acceptance(self):
        assert self._client().get("/release/acceptance-checklist").status_code == 200

    def test_release_notes(self):
        assert self._client().get("/release/release-notes").status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/release/status").status_code == 200
        assert c.get("/release/manifest").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert "3.2.0" in d["version"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
