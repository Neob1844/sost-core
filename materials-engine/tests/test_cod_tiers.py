"""Tests for Phase IV.J: Real-Source COD Pilot + Labeled/Unlabeled Corpus Tiers."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.corpus_sources.spec import (
    DEDUP_EXACT, DEDUP_UNIQUE, DEDUP_SAME_FORMULA_DIFF_STRUCT,
    DEDUP_UNIQUE_STRUCTURE_ONLY, DEDUP_UNIQUE_TRAINING_CANDIDATE,
    DEDUP_STRUCTURE_NEAR_MATCH, NormalizedCandidate,
)
from src.corpus_sources.dedup import check_dedup, batch_dedup
from src.corpus_sources.tiers import (
    classify_material_tier, compute_tier_summary, save_tier_summary,
    CorpusTierSummary, TieredMaterialRecord,
    TIER_TRAINING_READY, TIER_STRUCTURE_ONLY, TIER_REFERENCE_ONLY,
    TIER_GENERATED_CANDIDATE, TIER_EXTERNAL_UNLABELED, ALL_TIERS,
)
from src.corpus_sources.cod_pilot import (
    generate_cod_plan, execute_cod_pilot, compute_value_report,
    save_cod_artifacts, CODPilotCandidate, CODPilotPlan, CODPilotResult,
    ValueContributionReport, _generate_cod_candidates,
)


def _make_material(formula, elements, spacegroup=None, formation_energy=None,
                   band_gap=None, source="jarvis", source_id=None,
                   has_valid_structure=True):
    m = Material(formula=formula, elements=sorted(elements),
                 n_elements=len(elements), spacegroup=spacegroup,
                 formation_energy=formation_energy, band_gap=band_gap,
                 has_valid_structure=has_valid_structure,
                 source=source, source_id=source_id or formula, confidence=0.8)
    m.compute_canonical_id()
    return m


CORPUS = [
    _make_material("Si", ["Si"], 227, 0.0, 1.1),
    _make_material("GaAs", ["As", "Ga"], 216, -0.7, 1.4),
    _make_material("NaCl", ["Cl", "Na"], 225, -4.2, 5.0),
    _make_material("Fe2O3", ["Fe", "O"], 167, -1.5, 2.1),
    _make_material("TiO2", ["O", "Ti"], 136, -3.4, 3.0),
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


# ===== TIER CLASSIFICATION =====

class TestTierClassification:
    def test_training_ready_with_fe(self):
        tier, reason = classify_material_tier("jarvis", True, False, True, True)
        assert tier == TIER_TRAINING_READY

    def test_training_ready_with_bg(self):
        tier, reason = classify_material_tier("aflow", False, True, True, True)
        assert tier == TIER_TRAINING_READY

    def test_training_ready_with_both(self):
        tier, reason = classify_material_tier("mp", True, True, True, True)
        assert tier == TIER_TRAINING_READY

    def test_structure_only_from_cod(self):
        tier, reason = classify_material_tier("cod", False, False, True, True)
        assert tier == TIER_STRUCTURE_ONLY

    def test_external_unlabeled_cod_no_struct(self):
        tier, reason = classify_material_tier("cod", False, False, False, False)
        assert tier == TIER_EXTERNAL_UNLABELED

    def test_structure_only_unknown_source(self):
        tier, reason = classify_material_tier("unknown", False, False, True, True)
        assert tier == TIER_STRUCTURE_ONLY

    def test_reference_only(self):
        tier, reason = classify_material_tier("jarvis", False, False, False, False)
        assert tier == TIER_REFERENCE_ONLY

    def test_generated_candidate(self):
        tier, reason = classify_material_tier("generated", False, False, True, True)
        assert tier == TIER_GENERATED_CANDIDATE

    def test_generated_even_with_props(self):
        tier, reason = classify_material_tier("generated", True, True, True, True)
        assert tier == TIER_GENERATED_CANDIDATE

    def test_all_tiers_defined(self):
        assert len(ALL_TIERS) == 5
        assert TIER_TRAINING_READY in ALL_TIERS
        assert TIER_STRUCTURE_ONLY in ALL_TIERS


class TestTierSummary:
    def test_compute_summary(self, test_db):
        summary = compute_tier_summary(test_db)
        assert summary.total_materials == 5
        assert summary.tier_counts.get(TIER_TRAINING_READY, 0) == 5
        assert summary.training_ready_with_fe == 5
        assert summary.training_ready_with_bg == 5
        assert summary.training_ready_with_both == 5
        assert summary.element_coverage > 0
        assert summary.unique_spacegroups > 0

    def test_summary_serializable(self, test_db):
        summary = compute_tier_summary(test_db)
        json.dumps(summary.to_dict())

    def test_save_summary(self, test_db):
        td = tempfile.mkdtemp()
        summary = compute_tier_summary(test_db)
        save_tier_summary(summary, output_dir=td)
        assert os.path.exists(os.path.join(td, "tiers_summary.json"))
        assert os.path.exists(os.path.join(td, "tiers_summary.md"))

    def test_summary_by_source(self, test_db):
        summary = compute_tier_summary(test_db)
        assert "jarvis" in summary.by_source
        assert summary.by_source["jarvis"].get(TIER_TRAINING_READY, 0) == 5

    def test_structure_coverage(self, test_db):
        summary = compute_tier_summary(test_db)
        assert summary.structure_coverage == 100.0
        assert summary.spacegroup_coverage == 100.0

    def test_mixed_tier_corpus(self, test_db):
        """Add a COD structure-only material and verify mixed tiers."""
        m = Material(formula="ScRh3B", elements=["B", "Rh", "Sc"],
                     n_elements=3, spacegroup=221,
                     source="cod", source_id="cod-1000037",
                     confidence=0.6, has_valid_structure=True)
        m.compute_canonical_id()
        test_db.insert_material(m)

        summary = compute_tier_summary(test_db)
        assert summary.total_materials == 6
        assert summary.tier_counts.get(TIER_TRAINING_READY, 0) == 5
        assert summary.tier_counts.get(TIER_STRUCTURE_ONLY, 0) == 1


# ===== ENHANCED DEDUP =====

class TestEnhancedDedup:
    def test_exact_match(self, test_db):
        c = NormalizedCandidate(formula="Si", spacegroup=227, source_name="cod")
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_EXACT

    def test_same_formula_diff_sg(self, test_db):
        c = NormalizedCandidate(formula="Si", spacegroup=12, source_name="cod")
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_SAME_FORMULA_DIFF_STRUCT

    def test_unique_with_props(self, test_db):
        """Unique material with properties → training candidate."""
        c = NormalizedCandidate(formula="ScRh3B", spacegroup=221,
                                source_name="aflow",
                                formation_energy=-1.5, band_gap=0.5)
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_UNIQUE_TRAINING_CANDIDATE

    def test_unique_structure_only(self, test_db):
        """Unique material with structure but no props → structure only."""
        c = NormalizedCandidate(formula="HoRhSn", spacegroup=189,
                                source_name="cod", has_structure=True)
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_UNIQUE_STRUCTURE_ONLY

    def test_unique_no_props_no_struct(self, test_db):
        """Unique material with nothing → generic unique."""
        c = NormalizedCandidate(formula="UPu3", source_name="reference")
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_UNIQUE

    def test_batch_dedup_enhanced(self, test_db):
        candidates = [
            NormalizedCandidate(formula="Si", spacegroup=227, source_name="cod"),
            NormalizedCandidate(formula="ScRh3B", spacegroup=221,
                                source_name="aflow", formation_energy=-1.0),
            NormalizedCandidate(formula="HoRhSn", spacegroup=189,
                                source_name="cod", has_structure=True),
            NormalizedCandidate(formula="NaCl", spacegroup=225, source_name="mp"),
        ]
        result = batch_dedup(candidates, test_db)
        assert result["summary"]["exact"] == 2  # Si + NaCl
        assert result["summary"]["unique_training_candidate"] == 1  # ScRh3B
        assert result["summary"]["unique_structure_only"] == 1  # HoRhSn

    def test_backward_compat_unique(self, test_db):
        """Old-style DEDUP_UNIQUE still works for materials with no info."""
        c = NormalizedCandidate(formula="ZZZ999", source_name="test")
        d = check_dedup(c, test_db)
        assert d.decision == DEDUP_UNIQUE


# ===== COD PILOT =====

class TestCODPilotPlan:
    def test_generate_plan(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=20)
        assert plan.plan_id
        assert plan.source == "cod"
        assert plan.total_candidates > 0
        assert plan.selected_for_ingestion >= 0
        assert len(candidates) <= 20

    def test_plan_serializable(self, test_db):
        plan, _ = generate_cod_plan(test_db, target_count=10)
        json.dumps(plan.to_dict())

    def test_plan_api_status(self, test_db):
        plan, _ = generate_cod_plan(test_db, target_count=10)
        # API will be unreachable in test env
        assert plan.api_status in ("available", "unreachable")

    def test_plan_tier_assignment(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=20)
        for c in candidates:
            assert c.tier == TIER_STRUCTURE_ONLY

    def test_dedup_removes_known(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=50)
        # Known materials (Si, GaAs, Fe2O3) should not be selected as unique
        for c in candidates:
            if c.dedup_decision == DEDUP_EXACT:
                assert not c.selected


class TestCODPilotExecution:
    def test_dry_run(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=20)
        before = test_db.count()
        result = execute_cod_pilot(test_db, plan, candidates, dry_run=True)
        after = test_db.count()
        assert after == before  # dry run doesn't modify DB
        assert result.ingested >= 0
        assert result.tier_assigned == TIER_STRUCTURE_ONLY
        assert "none" in result.training_impact.lower()

    def test_real_run(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=10)
        before = test_db.count()
        result = execute_cod_pilot(test_db, plan, candidates, dry_run=False)
        after = test_db.count()
        assert result.corpus_before == before
        assert result.corpus_after == after
        assert result.ingested >= 0
        assert result.recommendation

    def test_result_serializable(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=5)
        result = execute_cod_pilot(test_db, plan, candidates, dry_run=True)
        json.dumps(result.to_dict())

    def test_no_training_contamination(self, test_db):
        """Verify COD materials are NOT marked with FE/BG."""
        plan, candidates = generate_cod_plan(test_db, target_count=10)
        execute_cod_pilot(test_db, plan, candidates, dry_run=False)

        # Check that COD materials in DB have no FE/BG
        cod_materials = test_db.search_materials(source="cod", limit=100)
        for m in cod_materials:
            assert m.formation_energy is None, f"COD {m.formula} should NOT have formation_energy"
            assert m.band_gap is None, f"COD {m.formula} should NOT have band_gap"


class TestValueReport:
    def test_compute_value(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=20)
        result = execute_cod_pilot(test_db, plan, candidates, dry_run=True)
        vr = compute_value_report(test_db, plan, result, candidates)
        assert vr.source == "cod"
        assert vr.training_value == "none"
        assert "search_space_benefit" in vr.to_dict()
        assert len(vr.search_space_benefit) >= 4

    def test_value_serializable(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=10)
        result = execute_cod_pilot(test_db, plan, candidates, dry_run=True)
        vr = compute_value_report(test_db, plan, result, candidates)
        json.dumps(vr.to_dict())

    def test_value_honest_training(self, test_db):
        plan, candidates = generate_cod_plan(test_db, target_count=10)
        result = execute_cod_pilot(test_db, plan, candidates, dry_run=True)
        vr = compute_value_report(test_db, plan, result, candidates)
        assert "cannot" in vr.training_value_reason.lower() or "not" in vr.training_value_reason.lower()


class TestCODArtifacts:
    def test_save_artifacts(self, test_db):
        td = tempfile.mkdtemp()
        plan, candidates = generate_cod_plan(test_db, target_count=10)
        result = execute_cod_pilot(test_db, plan, candidates, dry_run=True)
        vr = compute_value_report(test_db, plan, result, candidates)
        save_cod_artifacts(plan, result, candidates, vr, output_dir=td)

        assert os.path.exists(os.path.join(td, "cod_pilot_plan.json"))
        assert os.path.exists(os.path.join(td, "cod_pilot_plan.md"))
        assert os.path.exists(os.path.join(td, "cod_pilot_run.json"))
        assert os.path.exists(os.path.join(td, "cod_pilot_run.md"))
        assert os.path.exists(os.path.join(td, "cod_value_report.json"))
        assert os.path.exists(os.path.join(td, "cod_value_report.md"))
        assert os.path.exists(os.path.join(td, "cod_recommendation.json"))
        assert os.path.exists(os.path.join(td, "cod_recommendation.md"))


class TestCODCandidates:
    def test_generate_candidates(self):
        candidates = _generate_cod_candidates(20, seed=42)
        assert len(candidates) == 20
        for c in candidates:
            assert c.source == "cod"
            assert c.codid
            assert c.formula
            assert c.tier == TIER_STRUCTURE_ONLY

    def test_candidates_have_lattice(self):
        candidates = _generate_cod_candidates(5, seed=42)
        for c in candidates:
            assert c.lattice_params is not None
            assert "a" in c.lattice_params


# ===== API =====

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

    def test_tiers_status(self):
        r = self._client().get("/corpus-sources/tiers/status")
        assert r.status_code == 200
        assert "tiers" in r.json()
        assert len(r.json()["tiers"]) == 5

    def test_tiers_summary(self):
        r = self._client().get("/corpus-sources/tiers/summary")
        assert r.status_code == 200
        d = r.json()
        assert d["total_materials"] == 5
        assert TIER_TRAINING_READY in d["tier_counts"]

    def test_cod_pilot_plan(self):
        r = self._client().post("/corpus-sources/cod/pilot/plan?target_count=10")
        assert r.status_code == 200
        assert "plan" in r.json()
        assert r.json()["plan"]["source"] == "cod"

    def test_cod_pilot_run_dry(self):
        r = self._client().post("/corpus-sources/cod/pilot/run?target_count=10&dry_run=true")
        assert r.status_code == 200
        d = r.json()
        assert d["ingested"] >= 0
        assert d["tier_assigned"] == TIER_STRUCTURE_ONLY

    def test_cod_recommendation(self):
        # Run pilot first to generate artifacts
        self._client().post("/corpus-sources/cod/pilot/run?target_count=10&dry_run=true")
        r = self._client().get("/corpus-sources/cod/recommendation")
        assert r.status_code == 200

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200
        assert c.get("/corpus-sources/status").status_code == 200
        assert c.get("/corpus-sources/pilot/status").status_code == 200
        assert c.get("/orchestrator/status").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "2.6.0"

    def test_cod_registry_status(self):
        r = self._client().get("/corpus-sources/registry")
        cod = [s for s in r.json()["sources"] if s["name"] == "cod"][0]
        assert cod["status"] == "experimental"
        assert cod["has_formation_energy"] is False
        assert cod["has_band_gap"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
