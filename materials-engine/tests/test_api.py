"""Tests for the FastAPI server."""
import sys, os, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from src.api.server import app, _db, _get_db
from src.storage.db import MaterialsDB
from src.schema import Material


@pytest.fixture(autouse=True)
def setup_test_db():
    """Use a temp DB for each test."""
    import src.api.server as srv
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    srv._db = MaterialsDB(f.name)
    # Insert test data
    for i, (formula, bg, elements) in enumerate([
        ("Fe2O3", 2.1, ["Fe", "O"]),
        ("TiO2", 3.2, ["O", "Ti"]),
        ("NaCl", 8.5, ["Cl", "Na"]),
        ("Si", 1.1, ["Si"]),
    ]):
        m = Material(formula=formula, elements=elements, n_elements=len(elements),
                     band_gap=bg, source="test", source_id=str(i), confidence=0.8)
        m.compute_canonical_id()
        srv._db.insert_material(m)
    yield
    os.unlink(f.name)
    srv._db = None


client = TestClient(app)


def test_status():
    r = client.get("/status")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["materials_count"] == 4


def test_health():
    r = client.get("/health")
    assert r.status_code == 200


def test_stats():
    r = client.get("/stats")
    assert r.status_code == 200
    assert r.json()["total"] == 4


def test_list_materials():
    r = client.get("/materials?limit=2&offset=0")
    assert r.status_code == 200
    d = r.json()
    assert d["limit"] == 2
    assert len(d["data"]) == 2


def test_get_material():
    # Get a known material's canonical_id
    r = client.get("/materials?limit=1")
    cid = r.json()["data"][0]["canonical_id"]
    r2 = client.get(f"/materials/{cid}")
    assert r2.status_code == 200
    assert r2.json()["canonical_id"] == cid


def test_get_material_not_found():
    r = client.get("/materials/nonexistent")
    assert r.status_code == 404


def test_search_formula():
    r = client.get("/search?formula=Fe2O3")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_search_elements():
    r = client.get("/search?elements=Fe,O")
    assert r.status_code == 200
    data = r.json()["data"]
    assert len(data) >= 1
    assert all("Fe" in m["elements"] for m in data)


def test_search_band_gap_range():
    r = client.get("/search?band_gap_min=2.0&band_gap_max=4.0")
    assert r.status_code == 200
    data = r.json()["data"]
    assert all(2.0 <= m["band_gap"] <= 4.0 for m in data)


def test_search_min_gt_max_rejected():
    r = client.get("/search?band_gap_min=5.0&band_gap_max=1.0")
    assert r.status_code == 400


def test_predict_requires_body():
    r = client.post("/predict")
    assert r.status_code == 422  # missing required fields


def test_predict_invalid_cif():
    r = client.post("/predict", json={"cif": "not a cif", "target": "band_gap"})
    assert r.status_code in (400, 404)  # invalid structure or no model


def test_similar_not_found():
    r = client.get("/similar/nonexistent")
    assert r.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
