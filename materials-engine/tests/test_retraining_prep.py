"""Tests for Phase IV.K: Hard-Case Mining + Selective Retraining Datasets."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from src.schema import Material
from src.storage.db import MaterialsDB
from src.retraining_prep.spec import (
    HardCaseRecord, DifficultyTierSummary, SelectiveDatasetPlan,
    RetrainingPriorityScore, RetrainingPrepReport,
    DIFF_EASY, DIFF_MEDIUM, DIFF_HARD, DIFF_SPARSE_EXOTIC,
    DIFF_HIGH_VALUE_RETRAIN, DIFF_HOLDOUT_CANDIDATE,
    ALL_DIFFICULTY_TIERS, DIFF_DESCRIPTIONS,
)
from src.retraining_prep.mining import (
    mine_hard_cases, classify_difficulty, element_rarity_score,
    sg_rarity_score, _compute_corpus_stats,
)
from src.retraining_prep.datasets import (
    build_dataset_plans, score_dataset_plans,
)
from src.retraining_prep.report import (
    generate_full_report, save_report,
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


CORPUS = [
    _make_material("Si", ["Si"], 227, 0.0, 1.1),
    _make_material("GaAs", ["As", "Ga"], 216, -0.7, 1.4),
    _make_material("NaCl", ["Cl", "Na"], 225, -4.2, 5.0),
    _make_material("Fe2O3", ["Fe", "O"], 167, -1.5, 2.1),
    _make_material("TiO2", ["O", "Ti"], 136, -3.4, 3.0),
    # Complex / exotic materials
    _make_material("LiMgAlSi", ["Al", "Li", "Mg", "Si"], 62, -0.5, 0.3),
    _make_material("ScRh3B", ["B", "Rh", "Sc"], 221, -1.2, None),
    _make_material("YBa2Cu3O7", ["Ba", "Cu", "O", "Y"], 47, -2.0, 0.0),
    _make_material("HfZrTiNiSn", ["Hf", "Ni", "Sn", "Ti", "Zr"], 216, -0.3, 0.5),
    _make_material("CrMnFeCoNi", ["Co", "Cr", "Fe", "Mn", "Ni"], 225, 0.8, 0.0),
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


# ===== SPEC =====

class TestSpec:
    def test_all_tiers_defined(self):
        assert len(ALL_DIFFICULTY_TIERS) == 6
        for t in ALL_DIFFICULTY_TIERS:
            assert t in DIFF_DESCRIPTIONS

    def test_hardcase_record(self):
        r = HardCaseRecord(canonical_id="abc", formula="NaCl",
                           target="band_gap", difficulty_tier=DIFF_HARD)
        d = r.to_dict()
        assert d["difficulty_tier"] == "hard"
        json.dumps(d)

    def test_dataset_plan(self):
        p = SelectiveDatasetPlan(name="test", target="band_gap", size=100)
        d = p.to_dict()
        assert d["name"] == "test"
        json.dumps(d)

    def test_priority_score(self):
        s = RetrainingPriorityScore(dataset_name="test", overall_score=0.75)
        d = s.to_dict()
        assert d["overall_score"] == 0.75
        json.dumps(d)

    def test_report(self):
        r = RetrainingPrepReport(recommendation="test", next_action="wait")
        d = r.to_dict()
        json.dumps(d)


# ===== MINING =====

class TestMining:
    def test_element_rarity(self):
        from collections import Counter
        counts = Counter({"Si": 1000, "O": 5000, "Sc": 2, "Lu": 1})
        total = 10000
        # Common element
        score_si = element_rarity_score(["Si"], counts, total)
        # Rare element
        score_sc = element_rarity_score(["Sc"], counts, total)
        assert score_sc > score_si

    def test_sg_rarity(self):
        sg_counts = {225: 7000, 1: 5}
        total = 10000
        r_225 = sg_rarity_score(225, sg_counts, total)
        r_1 = sg_rarity_score(1, sg_counts, total)
        assert r_1 > r_225

    def test_sg_rarity_none(self):
        r = sg_rarity_score(None, {}, 100)
        assert r == 0.5

    def test_classify_easy(self):
        tier, reasons = classify_difficulty("high", 0.2, 0.1, 0.1, 2, "band_gap")
        assert tier == DIFF_EASY
        assert "high_confidence" in reasons

    def test_classify_hard(self):
        tier, reasons = classify_difficulty("low", 1.5, 0.3, 0.3, 2, "band_gap")
        assert tier == DIFF_HARD

    def test_classify_sparse_exotic(self):
        tier, reasons = classify_difficulty("medium", 0.5, 0.8, 0.7, 5, "band_gap")
        assert tier == DIFF_SPARSE_EXOTIC

    def test_classify_high_value(self):
        tier, reasons = classify_difficulty("low", 1.5, 0.7, 0.3, 3, "band_gap")
        assert tier == DIFF_HIGH_VALUE_RETRAIN

    def test_classify_medium(self):
        tier, reasons = classify_difficulty("medium", 0.6, 0.2, 0.2, 3, "band_gap")
        assert tier == DIFF_MEDIUM

    def test_mine_hard_cases_bg(self, test_db):
        summary, cases = mine_hard_cases(test_db, target="band_gap")
        assert summary.target == "band_gap"
        assert summary.total_materials > 0
        assert sum(summary.tier_counts.values()) == summary.total_materials
        for t in summary.tier_counts:
            assert t in ALL_DIFFICULTY_TIERS

    def test_mine_hard_cases_fe(self, test_db):
        summary, cases = mine_hard_cases(test_db, target="formation_energy")
        assert summary.target == "formation_energy"
        assert summary.total_materials > 0

    def test_mine_summary_serializable(self, test_db):
        summary, cases = mine_hard_cases(test_db, target="band_gap")
        json.dumps(summary.to_dict())

    def test_hardcases_serializable(self, test_db):
        _, cases = mine_hard_cases(test_db, target="band_gap")
        for c in cases:
            json.dumps(c.to_dict())

    def test_corpus_stats(self, test_db):
        stats = _compute_corpus_stats(test_db)
        assert stats["total"] == 10
        assert "Si" in stats["elem_counts"]
        assert len(stats["sg_counts"]) > 0


# ===== DATASETS =====

class TestDatasets:
    def test_build_plans(self, test_db):
        plans = build_dataset_plans(test_db)
        assert len(plans) == 6
        names = [p.name for p in plans]
        assert "bg_hotspots_10k" in names
        assert "bg_sparse_exotic_10k" in names
        assert "fe_hardcases_10k" in names
        assert "curriculum_easy_to_hard_20k" in names

    def test_plans_serializable(self, test_db):
        plans = build_dataset_plans(test_db)
        for p in plans:
            json.dumps(p.to_dict())

    def test_plans_have_composition(self, test_db):
        plans = build_dataset_plans(test_db)
        for p in plans:
            assert "actual_size" in p.composition_summary
            assert p.element_diversity >= 0
            assert p.sg_diversity >= 0

    def test_score_plans(self, test_db):
        plans = build_dataset_plans(test_db)
        scored = score_dataset_plans(plans, None, None)
        assert len(scored) == 6
        # Should be sorted by score descending
        for i in range(len(scored) - 1):
            assert scored[i].overall_score >= scored[i + 1].overall_score
        # Each has a rank
        assert scored[0].rank == 1
        assert scored[-1].rank == 6

    def test_scores_serializable(self, test_db):
        plans = build_dataset_plans(test_db)
        scored = score_dataset_plans(plans, None, None)
        for s in scored:
            json.dumps(s.to_dict())

    def test_scores_have_recommendation(self, test_db):
        plans = build_dataset_plans(test_db)
        scored = score_dataset_plans(plans, None, None)
        for s in scored:
            assert s.recommendation
            assert s.target in ("band_gap", "formation_energy")

    def test_bg_prioritized_over_fe(self, test_db):
        """BG has more room for improvement → should rank higher."""
        plans = build_dataset_plans(test_db)
        # Use real-ish calibration data
        bg_calib = {"overall_mae": 0.49}
        fe_calib = {"overall_mae": 0.23}
        scored = score_dataset_plans(plans, bg_calib, fe_calib)
        # Top dataset should be band_gap (more room for improvement)
        assert scored[0].target == "band_gap"


# ===== REPORT =====

class TestReport:
    def test_generate_report(self, test_db):
        report = generate_full_report(test_db)
        assert report.recommendation
        assert report.next_action
        assert len(report.do_not) > 0
        assert len(report.datasets) == 6
        assert len(report.priority_ranking) == 6

    def test_report_serializable(self, test_db):
        report = generate_full_report(test_db)
        json.dumps(report.to_dict())

    def test_save_report(self, test_db):
        td = tempfile.mkdtemp()
        report = generate_full_report(test_db)
        save_report(report, output_dir=td)
        assert os.path.exists(os.path.join(td, "hardcase_summary.json"))
        assert os.path.exists(os.path.join(td, "hardcase_summary.md"))
        assert os.path.exists(os.path.join(td, "difficulty_tiers.json"))
        assert os.path.exists(os.path.join(td, "difficulty_tiers.md"))
        assert os.path.exists(os.path.join(td, "selective_datasets.json"))
        assert os.path.exists(os.path.join(td, "selective_datasets.md"))
        assert os.path.exists(os.path.join(td, "retraining_priority.json"))
        assert os.path.exists(os.path.join(td, "retraining_priority.md"))

    def test_report_no_training(self, test_db):
        """Report must explicitly say no training happened."""
        report = generate_full_report(test_db)
        assert any("NOT" in d for d in report.do_not)


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

    def test_status(self):
        r = self._client().get("/retraining-prep/status")
        assert r.status_code == 200
        d = r.json()
        assert d["models_retrained"] is False
        assert "NOT" in d["note"]

    def test_hardcases(self):
        r = self._client().get("/retraining-prep/hardcases?target=band_gap")
        assert r.status_code == 200
        d = r.json()
        assert "summary" in d
        assert d["summary"]["target"] == "band_gap"

    def test_hardcases_fe(self):
        r = self._client().get("/retraining-prep/hardcases?target=formation_energy")
        assert r.status_code == 200
        assert r.json()["summary"]["target"] == "formation_energy"

    def test_tiers(self):
        r = self._client().get("/retraining-prep/tiers")
        assert r.status_code == 200
        d = r.json()
        assert "band_gap" in d
        assert "formation_energy" in d

    def test_datasets_build(self):
        r = self._client().post("/retraining-prep/datasets/build")
        assert r.status_code == 200
        d = r.json()
        assert len(d["datasets"]) == 6
        assert len(d["priority_ranking"]) == 6
        assert d["recommendation"]

    def test_recommendation(self):
        # Build first
        self._client().post("/retraining-prep/datasets/build")
        r = self._client().get("/retraining-prep/recommendation")
        assert r.status_code == 200
        d = r.json()
        assert "ranking" in d
        assert "recommendation" in d

    def test_backward_compat(self):
        c = self._client()
        assert c.get("/status").status_code == 200
        assert c.get("/corpus-sources/registry").status_code == 200
        assert c.get("/corpus-sources/tiers/status").status_code == 200
        assert c.get("/orchestrator/status").status_code == 200

    def test_version(self):
        d = self._client().get("/status").json()
        assert d["version"] == "3.1.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
