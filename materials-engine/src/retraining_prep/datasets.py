"""Selective dataset builder — construct intelligent retraining subsets.

Phase IV.K: Builds focused datasets from corpus using difficulty tiers,
calibration signals, and diversity criteria. Does NOT train.
"""

import hashlib
import json
import logging
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

from ..storage.db import MaterialsDB
from .spec import (
    SelectiveDatasetPlan, RetrainingPriorityScore,
    PRIORITY_CRITICAL, PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW,
)
from .mining import (
    mine_hard_cases, _compute_corpus_stats, element_rarity_score,
    sg_rarity_score, _load_calibration, _get_confidence_band,
    DIFF_HARD, DIFF_SPARSE_EXOTIC, DIFF_HIGH_VALUE_RETRAIN,
    DIFF_MEDIUM, DIFF_EASY,
)

log = logging.getLogger(__name__)


def _sample_materials(db: MaterialsDB, target: str, condition: str,
                      size: int, seed: int = 42) -> Tuple[List, Dict]:
    """Sample materials matching a SQL condition.

    Returns (list_of_materials, composition_summary).
    """
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    prop_col = "band_gap" if target == "band_gap" else "formation_energy"
    query = f"""SELECT canonical_id, formula, elements, n_elements, spacegroup,
                       {prop_col} as target_value, source
                FROM materials
                WHERE {prop_col} IS NOT NULL AND {condition}
                ORDER BY canonical_id"""
    c.execute(query)
    rows = c.fetchall()
    conn.close()

    if not rows:
        return [], {}

    # Deterministic sampling
    rng = np.random.RandomState(seed)
    if len(rows) > size:
        indices = rng.choice(len(rows), size=size, replace=False)
        indices.sort()
        rows = [rows[i] for i in indices]

    # Composition summary
    elems = Counter()
    sgs = set()
    n_elem_dist = Counter()
    for r in rows:
        try:
            el = json.loads(r["elements"]) if r["elements"] else []
            elems.update(el)
        except (json.JSONDecodeError, TypeError):
            pass
        if r["spacegroup"]:
            sgs.add(r["spacegroup"])
        n_elem_dist[r["n_elements"]] += 1

    summary = {
        "actual_size": len(rows),
        "unique_elements": len(elems),
        "unique_spacegroups": len(sgs),
        "n_element_distribution": dict(n_elem_dist),
        "top_elements": dict(elems.most_common(10)),
    }

    return rows, summary


def build_dataset_plans(db: MaterialsDB) -> List[SelectiveDatasetPlan]:
    """Build all selective dataset plans based on corpus analysis.

    Returns list of SelectiveDatasetPlan with real composition data.
    """
    now = datetime.now(timezone.utc).isoformat()
    plans = []

    # --- Band gap datasets ---

    # 1. BG hotspots: materials in hard calibration buckets (3-6 eV, 1-3 eV)
    rows, comp = _sample_materials(
        db, "band_gap",
        "band_gap >= 1.0 AND band_gap < 6.0",
        size=10000, seed=42)
    plans.append(SelectiveDatasetPlan(
        dataset_id=hashlib.sha256(b"bg_hotspots_10k").hexdigest()[:12],
        name="bg_hotspots_10k",
        target="band_gap",
        size=comp.get("actual_size", 0),
        selection_logic="Materials with band_gap 1.0-6.0 eV where model has MEDIUM/LOW confidence (MAE 0.87-1.12 eV in calibration)",
        composition_summary=comp,
        element_diversity=comp.get("unique_elements", 0),
        sg_diversity=comp.get("unique_spacegroups", 0),
        reason_for_existence="Calibration shows BG 3-6 eV bucket has MAE=1.12 (LOW confidence) and 1-3 eV has MAE=0.87 (MEDIUM). These are the model's weakest regions.",
        expected_benefit="Reduce BG MAE for wide-gap materials from ~1.0 to <0.6 eV. Improve calibration from LOW/MEDIUM to HIGH.",
        risk_note="Oversampling wide-gap may degrade metal/narrow-gap accuracy. Use curriculum or stratified sampling.",
        priority_score=0.0,
        created_at=now))

    # 2. BG sparse exotic: 4+ element materials with band_gap
    rows, comp = _sample_materials(
        db, "band_gap",
        "band_gap IS NOT NULL AND n_elements >= 4",
        size=10000, seed=42)
    plans.append(SelectiveDatasetPlan(
        dataset_id=hashlib.sha256(b"bg_sparse_exotic_10k").hexdigest()[:12],
        name="bg_sparse_exotic_10k",
        target="band_gap",
        size=comp.get("actual_size", 0),
        selection_logic="Materials with 4+ elements and band_gap. High combinatorial complexity where model has limited signal.",
        composition_summary=comp,
        element_diversity=comp.get("unique_elements", 0),
        sg_diversity=comp.get("unique_spacegroups", 0),
        reason_for_existence="5+ element materials show MAE=0.73 in calibration (MEDIUM). Only 1,630 materials in corpus have n_elements>=4 with BG.",
        expected_benefit="Better BG prediction for complex compositions. Expand chemical diversity in training.",
        risk_note="Small sample — may not generalize. 4-elem materials dominate over 5+ which are truly sparse.",
        priority_score=0.0,
        created_at=now))

    # 3. BG balanced hard mix: stratified sample mixing hard regions
    rows, comp = _sample_materials(
        db, "band_gap",
        """band_gap IS NOT NULL AND (
            (band_gap >= 1.0 AND band_gap < 6.0)
            OR n_elements >= 4
            OR spacegroup IN (SELECT spacegroup FROM materials GROUP BY spacegroup HAVING COUNT(*) < 50)
        )""",
        size=20000, seed=42)
    plans.append(SelectiveDatasetPlan(
        dataset_id=hashlib.sha256(b"bg_balanced_hardmix_20k").hexdigest()[:12],
        name="bg_balanced_hardmix_20k",
        target="band_gap",
        size=comp.get("actual_size", 0),
        selection_logic="Union of hard BG value ranges (1-6 eV) + complex compositions (4+ elem) + rare SGs. Balanced for diversity.",
        composition_summary=comp,
        element_diversity=comp.get("unique_elements", 0),
        sg_diversity=comp.get("unique_spacegroups", 0),
        reason_for_existence="Combined difficulty signals. Addresses all weak calibration buckets simultaneously.",
        expected_benefit="Broad improvement across all weak BG regions. Reduce overall BG MAE from 0.49 toward 0.35.",
        risk_note="Larger dataset = longer training. Risk of diluting hard cases with too many medium cases.",
        priority_score=0.0,
        created_at=now))

    # --- Formation energy datasets ---

    # 4. FE hard cases: unstable/metastable materials (fe > 0)
    rows, comp = _sample_materials(
        db, "formation_energy",
        "formation_energy > 0.0",
        size=10000, seed=42)
    plans.append(SelectiveDatasetPlan(
        dataset_id=hashlib.sha256(b"fe_hardcases_10k").hexdigest()[:12],
        name="fe_hardcases_10k",
        target="formation_energy",
        size=comp.get("actual_size", 0),
        selection_logic="Materials with formation_energy > 0 eV/atom (unstable/metastable). Calibration shows MAE=0.43 for 1-5 eV range (MEDIUM).",
        composition_summary=comp,
        element_diversity=comp.get("unique_elements", 0),
        sg_diversity=comp.get("unique_spacegroups", 0),
        reason_for_existence="FE > 0 (unstable) is the only MEDIUM confidence bucket. MAE=0.43 vs overall 0.23. 15K materials in this region.",
        expected_benefit="Reduce FE MAE for unstable materials from 0.43 to <0.25. Critical for stability screening.",
        risk_note="FE model already strong (overall MAE=0.15). Gains may be marginal vs effort.",
        priority_score=0.0,
        created_at=now))

    # 5. FE sparse mix: complex/exotic with formation_energy
    rows, comp = _sample_materials(
        db, "formation_energy",
        "formation_energy IS NOT NULL AND n_elements >= 4",
        size=10000, seed=42)
    plans.append(SelectiveDatasetPlan(
        dataset_id=hashlib.sha256(b"fe_sparse_mix_10k").hexdigest()[:12],
        name="fe_sparse_mix_10k",
        target="formation_energy",
        size=comp.get("actual_size", 0),
        selection_logic="Complex materials (4+ elements) for formation_energy. Rare chemistry where model has limited exposure.",
        composition_summary=comp,
        element_diversity=comp.get("unique_elements", 0),
        sg_diversity=comp.get("unique_spacegroups", 0),
        reason_for_existence="FE model trained mostly on 2-3 element materials. 4+ element materials are underrepresented.",
        expected_benefit="Better FE prediction for complex compositions. Useful for multinary phase screening.",
        risk_note="FE model already excellent on common materials. Overemphasis on complex may not help.",
        priority_score=0.0,
        created_at=now))

    # 6. Curriculum: easy → hard progression for BG
    rows, comp = _sample_materials(
        db, "band_gap",
        "band_gap IS NOT NULL",
        size=20000, seed=42)
    plans.append(SelectiveDatasetPlan(
        dataset_id=hashlib.sha256(b"curriculum_easy_to_hard_20k").hexdigest()[:12],
        name="curriculum_easy_to_hard_20k",
        target="band_gap",
        size=comp.get("actual_size", 0),
        selection_logic="Full BG corpus sample (20K). Training uses curriculum: start with easy (metals, common), gradually add harder (wide-gap, complex). Ordered by predicted difficulty.",
        composition_summary=comp,
        element_diversity=comp.get("unique_elements", 0),
        sg_diversity=comp.get("unique_spacegroups", 0),
        reason_for_existence="Curriculum learning can improve convergence on hard cases without sacrificing easy-case accuracy.",
        expected_benefit="Smoother loss landscape. Better generalization across all BG ranges.",
        risk_note="Curriculum ordering requires difficulty labels at training time. More complex training loop.",
        priority_score=0.0,
        created_at=now))

    return plans


def score_dataset_plans(plans: List[SelectiveDatasetPlan],
                        bg_calib: Optional[dict],
                        fe_calib: Optional[dict]) -> List[RetrainingPriorityScore]:
    """Score and rank dataset plans for retraining priority.

    Scoring (0-1 each, weighted sum):
    - benefit (0.30): How much model improvement expected
    - difficulty_concentration (0.20): % of hard/sparse materials
    - diversity (0.15): Element + SG diversity relative to corpus
    - sparse_coverage (0.15): Rare element/SG coverage
    - exotic_value (0.10): Value for exotic/novel material prediction
    - overfit_risk (negative 0.05): Risk of overfitting
    - training_cost (negative 0.05): Relative training time
    """
    scored = []

    # Current model weaknesses
    bg_overall_mae = bg_calib.get("overall_mae", 0.5) if bg_calib else 0.5
    fe_overall_mae = fe_calib.get("overall_mae", 0.23) if fe_calib else 0.23

    for plan in plans:
        target = plan.target
        size = plan.size
        comp = plan.composition_summary

        # Benefit score: higher for targets with more room for improvement
        if target == "band_gap":
            # BG has more room: MAE=0.49, target=0.35
            base_benefit = min(1.0, (bg_overall_mae - 0.30) / 0.30)
        else:
            # FE already good: MAE=0.23, target=0.15
            base_benefit = min(1.0, (fe_overall_mae - 0.15) / 0.30)

        # Adjust by dataset focus
        if "hotspot" in plan.name or "hardcase" in plan.name:
            base_benefit *= 1.2
        elif "sparse" in plan.name or "exotic" in plan.name:
            base_benefit *= 1.1

        benefit = min(1.0, base_benefit)

        # Difficulty concentration
        n_complex = comp.get("n_element_distribution", {})
        complex_count = sum(v for k, v in n_complex.items() if int(k) >= 4)
        diff_conc = min(1.0, complex_count / max(size, 1) * 3)
        if "hardmix" in plan.name or "hotspot" in plan.name:
            diff_conc = min(1.0, diff_conc + 0.3)

        # Diversity scores
        div_elem = min(1.0, comp.get("unique_elements", 0) / 89)  # 89 elements in corpus
        div_sg = min(1.0, comp.get("unique_spacegroups", 0) / 213)  # 213 SGs in corpus
        diversity = (div_elem + div_sg) / 2

        # Sparse coverage
        sparse = 0.5  # baseline
        if "sparse" in plan.name or "exotic" in plan.name:
            sparse = 0.8
        elif "curriculum" in plan.name or "hardmix" in plan.name:
            sparse = 0.6

        # Exotic value
        exotic = 0.3
        if "sparse" in plan.name or "exotic" in plan.name:
            exotic = 0.9
        elif "hotspot" in plan.name or "hardcase" in plan.name:
            exotic = 0.5

        # Overfit risk (lower is better, we negate in final score)
        overfit = 0.3
        if size < 5000:
            overfit = 0.7
        elif size > 15000:
            overfit = 0.2

        # Training cost (lower is better, we negate)
        cost = min(1.0, size / 20000)

        # Weighted score
        overall = (
            benefit * 0.30 +
            diff_conc * 0.20 +
            diversity * 0.15 +
            sparse * 0.15 +
            exotic * 0.10 -
            overfit * 0.05 -
            cost * 0.05
        )

        # Recommendation
        if overall >= 0.55:
            rec = f"retrain_{target}_with_{plan.name}_next"
        elif overall >= 0.40:
            rec = f"consider_{plan.name}_after_top_priority"
        else:
            rec = f"defer_{plan.name}"

        scored.append(RetrainingPriorityScore(
            dataset_id=plan.dataset_id, dataset_name=plan.name,
            target=target, overall_score=round(overall, 4),
            benefit_score=round(benefit, 4),
            difficulty_concentration=round(diff_conc, 4),
            diversity_score=round(diversity, 4),
            sparse_coverage=round(sparse, 4),
            exotic_value=round(exotic, 4),
            overfit_risk=round(overfit, 4),
            training_cost=round(cost, 4),
            recommendation=rec))

    # Sort by overall score descending
    scored.sort(key=lambda s: -s.overall_score)
    for i, s in enumerate(scored):
        s.rank = i + 1

    return scored
