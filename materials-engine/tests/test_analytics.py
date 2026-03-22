"""Tests for real structure analytics and physical descriptors."""
import sys, os, tempfile, json, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.analytics.descriptors import (
    compute_descriptors, COMPUTED_STRUCTURE, COMPUTED_COMPOSITION, PROXY, UNAVAILABLE,
)
from src.intelligence.dossier import build_dossier
from src.features.fingerprint_store import FingerprintStore

NACL_CIF = """data_NaCl
_cell_length_a 5.64
_cell_length_b 5.64
_cell_length_c 5.64
_cell_angle_alpha 90
_cell_angle_beta 90
_cell_angle_gamma 90
_symmetry_space_group_name_H-M 'F m -3 m'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Na Na 0.0 0.0 0.0
Cl Cl 0.5 0.5 0.5
"""


def _make_material(formula, elements, spacegroup=None, band_gap=None,
                   formation_energy=None, structure_data=None,
                   source="test", source_id=None):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 band_gap=band_gap, formation_energy=formation_energy,
                 structure_data=structure_data,
                 has_valid_structure=structure_data is not None,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("NaCl", ["Cl", "Na"], 225, 8.5, -4.2, structure_data=NACL_CIF),
    _make_material("Fe2O3", ["Fe", "O"], 167, 2.1, -1.5),
    _make_material("Si", ["Si"], 227, 1.1, 0.0),
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
def fp_store(test_db):
    d = tempfile.mkdtemp()
    store = FingerprintStore(store_dir=d)
    store.build(test_db)
    yield store
    shutil.rmtree(d)


# ================================================================
# Descriptor computation tests
# ================================================================

class TestDescriptors:
    def test_with_structure(self):
        from pymatgen.core import Structure
        s = Structure.from_str(NACL_CIF, fmt="cif")
        desc = compute_descriptors(structure=s, formula="NaCl", elements=["Cl", "Na"])

        assert "density_g_cm3" in desc
        assert desc["density_g_cm3"]["evidence"] == COMPUTED_STRUCTURE
        assert desc["density_g_cm3"]["value"] > 0

        assert "volume_A3" in desc
        assert desc["volume_A3"]["value"] > 0

        assert "volume_per_atom_A3" in desc
        assert desc["volume_per_atom_A3"]["value"] > 0

    def test_without_structure(self):
        desc = compute_descriptors(formula="NaCl", elements=["Cl", "Na"])
        assert desc["density_g_cm3"]["evidence"] == UNAVAILABLE
        assert desc["density_g_cm3"]["value"] is None
        # Composition descriptors should still work
        assert "nelements" in desc
        assert desc["nelements"]["value"] == 2

    def test_formula_weight(self):
        desc = compute_descriptors(formula="NaCl", elements=["Cl", "Na"])
        assert "formula_weight" in desc
        assert desc["formula_weight"]["evidence"] == COMPUTED_COMPOSITION
        assert abs(desc["formula_weight"]["value"] - 58.44) < 1.0

    def test_element_statistics(self):
        desc = compute_descriptors(formula="Fe2O3", elements=["Fe", "O"])
        assert "atomic_number_mean" in desc
        assert "electronegativity_mean" in desc
        assert "atomic_mass_mean" in desc

    def test_composition_fractions(self):
        desc = compute_descriptors(formula="Fe2O3", elements=["Fe", "O"])
        assert desc["fraction_metal"]["value"] == 0.5  # Fe is metal
        assert desc["fraction_nonmetal"]["value"] == 0.5  # O is nonmetal

    def test_transition_metal_fraction(self):
        desc = compute_descriptors(formula="TiO2", elements=["O", "Ti"])
        assert desc["fraction_transition_metal"]["value"] == 0.5

    def test_lattice_parameters(self):
        from pymatgen.core import Structure
        s = Structure.from_str(NACL_CIF, fmt="cif")
        desc = compute_descriptors(structure=s, formula="NaCl", elements=["Cl", "Na"])
        assert "lattice_a" in desc
        assert desc["lattice_a"]["evidence"] == COMPUTED_STRUCTURE
        assert abs(desc["lattice_a"]["value"] - 5.64) < 0.1

    def test_bond_distances(self):
        from pymatgen.core import Structure
        s = Structure.from_str(NACL_CIF, fmt="cif")
        desc = compute_descriptors(structure=s, formula="NaCl", elements=["Cl", "Na"])
        assert "min_neighbor_distance" in desc
        assert "mean_neighbor_distance" in desc
        assert desc["min_neighbor_distance"]["value"] > 0

    def test_symmetry(self):
        from pymatgen.core import Structure
        s = Structure.from_str(NACL_CIF, fmt="cif")
        desc = compute_descriptors(structure=s, formula="NaCl", elements=["Cl", "Na"])
        assert "spacegroup_number" in desc
        assert desc["spacegroup_number"]["value"] == 225
        assert "crystal_system" in desc
        assert desc["crystal_system"]["value"] == "cubic"

    def test_evidence_tagging_consistent(self):
        from pymatgen.core import Structure
        s = Structure.from_str(NACL_CIF, fmt="cif")
        desc = compute_descriptors(structure=s, formula="NaCl", elements=["Cl", "Na"])
        for key, entry in desc.items():
            assert "evidence" in entry, f"{key} missing evidence field"
            assert entry["evidence"] in (
                COMPUTED_STRUCTURE, COMPUTED_COMPOSITION, PROXY, UNAVAILABLE
            ), f"{key} has unexpected evidence: {entry['evidence']}"

    def test_empty_elements(self):
        desc = compute_descriptors(formula="", elements=[])
        assert desc["nelements"]["value"] == 0


# ================================================================
# Dossier integration tests
# ================================================================

class TestDossierAnalytics:
    def test_dossier_has_structure_analytics(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], spacegroup=225,
                          db=test_db, store=fp_store)
        assert "structure_analytics" in d
        sa = d["structure_analytics"]
        assert "descriptors" in sa
        assert sa["descriptor_count"] > 0

    def test_dossier_structure_available(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], spacegroup=225,
                          db=test_db, store=fp_store)
        sa = d["structure_analytics"]
        assert sa["available"]
        # Should have structure-derived descriptors
        assert "density_g_cm3" in sa["descriptors"]
        assert sa["descriptors"]["density_g_cm3"]["evidence"] == COMPUTED_STRUCTURE

    def test_dossier_no_structure(self, test_db, fp_store):
        d = build_dossier("Fe2O3", ["Fe", "O"], spacegroup=167,
                          db=test_db, store=fp_store)
        sa = d["structure_analytics"]
        assert not sa["available"]
        # Should still have composition descriptors
        assert "nelements" in sa["descriptors"]

    def test_dossier_backward_compat(self, test_db, fp_store):
        d = build_dossier("NaCl", ["Cl", "Na"], db=test_db, store=fp_store)
        # All existing fields must still be present
        assert "existence_status" in d
        assert "known_properties" in d
        assert "calibration" in d
        assert "validation_priority" in d
        assert "limitations" in d


# ================================================================
# API tests
# ================================================================

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

    def test_analytics_material(self):
        c = self._client()
        r = c.get("/materials?limit=1")
        cid = r.json()["data"][0]["canonical_id"]
        r2 = c.get(f"/analytics/material/{cid}")
        assert r2.status_code == 200
        d = r2.json()
        assert "descriptors" in d
        assert len(d["descriptors"]) > 0

    def test_analytics_material_not_found(self):
        c = self._client()
        r = c.get("/analytics/material/nonexistent")
        assert r.status_code == 404

    def test_analytics_report(self):
        c = self._client()
        r = c.post("/analytics/report", json={
            "formula": "NaCl", "elements": ["Cl", "Na"]})
        assert r.status_code == 200
        d = r.json()
        assert "descriptors" in d
        assert "nelements" in d["descriptors"]

    def test_analytics_report_with_cif(self):
        c = self._client()
        r = c.post("/analytics/report", json={
            "formula": "NaCl", "elements": ["Cl", "Na"],
            "cif": NACL_CIF})
        assert r.status_code == 200
        d = r.json()
        assert d["structure_available"]
        assert "density_g_cm3" in d["descriptors"]
        assert d["descriptors"]["density_g_cm3"]["value"] > 0

    def test_backward_compatibility(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/health").status_code == 200
        assert c.get("/materials?limit=1").status_code == 200
        assert c.get("/generation/presets").status_code == 200
        assert c.get("/validation/presets").status_code == 200
        assert c.get("/evidence/status").status_code == 200
        assert c.get("/benchmark/presets").status_code == 200
        assert c.get("/calibration/status").status_code == 200

    def test_status_version(self):
        c = self._client()
        d = c.get("/status").json()
        assert d["version"] == "3.1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
