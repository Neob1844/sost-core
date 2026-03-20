"""Hard-case mining — detect difficult materials from calibration and corpus signals.

Phase IV.K: Uses calibration buckets, element rarity, SG frequency, and
value-range difficulty to classify every material by difficulty tier.
Does NOT retrain. Does NOT modify models.
"""

import json
import logging
import math
import os
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..storage.db import MaterialsDB
from .spec import (
    HardCaseRecord, DifficultyTierSummary,
    DIFF_EASY, DIFF_MEDIUM, DIFF_HARD,
    DIFF_SPARSE_EXOTIC, DIFF_HIGH_VALUE_RETRAIN, DIFF_HOLDOUT_CANDIDATE,
    ALL_DIFFICULTY_TIERS,
)

log = logging.getLogger(__name__)

# Calibration artifact paths
CALIB_DIR = "artifacts/calibration"

# Element rarity threshold: elements appearing in <0.5% of corpus are "rare"
RARE_ELEMENT_THRESHOLD = 0.005
# SG rarity: spacegroups with <50 materials
RARE_SG_THRESHOLD = 50


def _load_calibration(target: str) -> Optional[dict]:
    """Load calibration data for a target."""
    path = os.path.join(CALIB_DIR, f"calibration_{target}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _compute_corpus_stats(db: MaterialsDB) -> dict:
    """Compute element and SG frequency from corpus."""
    conn = sqlite3.connect(db.db_path)
    c = conn.cursor()

    # Element frequencies
    c.execute("SELECT elements FROM materials")
    elem_counts = Counter()
    total = 0
    for row in c.fetchall():
        try:
            elems = json.loads(row[0]) if row[0] else []
            elem_counts.update(elems)
            total += 1
        except (json.JSONDecodeError, TypeError):
            pass

    # SG frequencies
    c.execute("SELECT spacegroup, COUNT(*) FROM materials WHERE spacegroup IS NOT NULL GROUP BY spacegroup")
    sg_counts = {row[0]: row[1] for row in c.fetchall()}

    # n_elements distribution
    c.execute("SELECT n_elements, COUNT(*) FROM materials GROUP BY n_elements")
    nelem_counts = {row[0]: row[1] for row in c.fetchall()}

    conn.close()
    return {
        "elem_counts": elem_counts,
        "total": total,
        "sg_counts": sg_counts,
        "nelem_counts": nelem_counts,
    }


def element_rarity_score(elements: list, elem_counts: Counter, total: int) -> float:
    """IDF-based element rarity: average of log(N/(1+count))/log(N) for each element."""
    if not elements or total < 2:
        return 0.0
    log_n = math.log(total)
    scores = []
    for e in elements:
        count = elem_counts.get(e, 0)
        scores.append(math.log(total / (1 + count)) / log_n)
    return min(1.0, sum(scores) / len(scores))


def sg_rarity_score(sg: Optional[int], sg_counts: dict, total: int) -> float:
    """Rarity score for a spacegroup: log(N/(1+sg_count))/log(N)."""
    if sg is None or total < 2:
        return 0.5  # unknown SG gets medium rarity
    count = sg_counts.get(sg, 0)
    return min(1.0, math.log(total / (1 + count)) / math.log(total))


def _get_confidence_band(target: str, n_elements: int,
                         value: Optional[float], calib: dict) -> Tuple[str, float]:
    """Get confidence band and expected error for a material from calibration."""
    # Check by value range first (more informative)
    if value is not None and "by_value_range" in calib:
        for bucket_label, bdata in calib["by_value_range"].items():
            try:
                parts = bucket_label.split("-")
                if len(parts) == 2:
                    lo, hi = float(parts[0]), float(parts[1])
                elif len(parts) == 3 and parts[0] == "":
                    lo, hi = -float(parts[1]), float(parts[2])
                elif len(parts) == 4:
                    lo, hi = -float(parts[1]), -float(parts[3])
                else:
                    continue
                if lo <= value < hi:
                    return bdata.get("confidence_band", "unknown"), bdata.get("mae", 0.0)
            except (ValueError, IndexError):
                continue

    # Fallback to element count bucket
    if "by_element_count" in calib:
        key = f"{n_elements}-{n_elements}" if n_elements <= 4 else "5-99"
        if key in calib["by_element_count"]:
            bdata = calib["by_element_count"][key]
            return bdata.get("confidence_band", "unknown"), bdata.get("mae", 0.0)
        # Try "other" bucket
        if "other" in calib["by_element_count"]:
            bdata = calib["by_element_count"]["other"]
            return bdata.get("confidence_band", "unknown"), bdata.get("mae", 0.0)

    return "unknown", calib.get("overall_mae", 0.5)


def classify_difficulty(confidence_band: str, expected_error: float,
                        elem_rarity: float, sg_rarity: float,
                        n_elements: int, target: str) -> Tuple[str, List[str]]:
    """Classify a material into a difficulty tier with reasons.

    Decision tree:
    1. If rare elements (rarity > 0.6) AND n_elements >= 4 → sparse_exotic
    2. If confidence_band == "low" OR expected_error > HIGH threshold → hard
    3. If confidence_band == "low" AND (rare elems OR rare SG) → high_value_retrain
    4. If confidence_band == "medium" → medium
    5. If confidence_band == "high" AND rarity < 0.3 → easy
    6. If easy AND good for holdout (common, well-predicted) → holdout_candidate (10% random)
    """
    reasons = []

    # Thresholds per target
    if target == "band_gap":
        high_err = 1.0
        med_err = 0.5
    else:
        high_err = 0.6
        med_err = 0.3

    is_rare_elem = elem_rarity > 0.6
    is_rare_sg = sg_rarity > 0.6
    is_complex = n_elements >= 4

    # Sparse exotic: rare chemistry regardless of model performance
    if is_rare_elem and is_complex:
        reasons.append("rare_element_combination")
        reasons.append(f"n_elements={n_elements}")
        if is_rare_sg:
            reasons.append("rare_spacegroup")
        return DIFF_SPARSE_EXOTIC, reasons

    # High value retrain: model struggles AND rare chemistry
    if confidence_band == "low" and (is_rare_elem or is_rare_sg):
        reasons.append(f"low_confidence_band")
        reasons.append(f"expected_error={expected_error:.3f}")
        if is_rare_elem:
            reasons.append("rare_elements")
        if is_rare_sg:
            reasons.append("rare_spacegroup")
        return DIFF_HIGH_VALUE_RETRAIN, reasons

    # Hard: model struggles
    if confidence_band == "low" or expected_error > high_err:
        reasons.append(f"confidence_band={confidence_band}")
        reasons.append(f"expected_error={expected_error:.3f}")
        if is_rare_elem:
            reasons.append("rare_elements")
        return DIFF_HARD, reasons

    # Medium: moderate performance
    if confidence_band == "medium" or expected_error > med_err:
        reasons.append(f"confidence_band={confidence_band}")
        if is_rare_elem:
            reasons.append("rare_elements")
        return DIFF_MEDIUM, reasons

    # Easy: well-predicted, common chemistry
    reasons.append("high_confidence")
    if elem_rarity < 0.2:
        reasons.append("common_chemistry")

    return DIFF_EASY, reasons


def mine_hard_cases(db: MaterialsDB, target: str = "band_gap",
                    limit: int = 5000) -> Tuple[DifficultyTierSummary, List[HardCaseRecord]]:
    """Mine hard cases for a target.

    Returns (DifficultyTierSummary, List[HardCaseRecord] for hard/sparse/high_value only).
    """
    now = datetime.now(timezone.utc).isoformat()
    calib = _load_calibration(target)
    if calib is None:
        # No calibration — use defaults
        calib = {"overall_mae": 0.5, "by_value_range": {}, "by_element_count": {}}

    stats = _compute_corpus_stats(db)
    tier_counts = Counter()
    hard_cases = []
    sparse_elems = set()
    rare_sgs = set()

    total = db.count()
    batch_size = 5000
    offset = 0

    while offset < total:
        materials = db.list_materials(limit=batch_size, offset=offset)
        if not materials:
            break
        for m in materials:
            # Skip materials without the target property
            value = getattr(m, target, None) if target in ("band_gap", "formation_energy") else None
            if target == "band_gap" and m.band_gap is None:
                continue
            if target == "formation_energy" and m.formation_energy is None:
                continue
            value = m.band_gap if target == "band_gap" else m.formation_energy

            elem_rar = element_rarity_score(
                m.elements, stats["elem_counts"], stats["total"])
            sg_rar = sg_rarity_score(
                m.spacegroup, stats["sg_counts"], stats["total"])
            conf_band, exp_err = _get_confidence_band(
                target, m.n_elements, value, calib)

            tier, reasons = classify_difficulty(
                conf_band, exp_err, elem_rar, sg_rar, m.n_elements, target)
            tier_counts[tier] += 1

            # Track sparse elements and rare SGs
            if elem_rar > 0.5:
                sparse_elems.update(m.elements)
            if sg_rar > 0.6 and m.spacegroup:
                rare_sgs.add(m.spacegroup)

            # Keep hard/sparse/high_value records (up to limit)
            if tier in (DIFF_HARD, DIFF_SPARSE_EXOTIC, DIFF_HIGH_VALUE_RETRAIN) and len(hard_cases) < limit:
                hard_cases.append(HardCaseRecord(
                    canonical_id=m.canonical_id, formula=m.formula,
                    source=m.source, target=target,
                    difficulty_tier=tier, n_elements=m.n_elements,
                    spacegroup=m.spacegroup, actual_value=value,
                    confidence_band=conf_band, expected_error=exp_err,
                    element_rarity=round(elem_rar, 4),
                    sg_rarity=round(sg_rar, 4), reasons=reasons))

        offset += batch_size

    # Build hardest buckets from calibration
    hardest = []
    if calib and "by_value_range" in calib:
        for label, bdata in sorted(calib["by_value_range"].items(),
                                    key=lambda x: -x[1].get("mae", 0)):
            if bdata.get("confidence_band") in ("low", "medium"):
                hardest.append({
                    "bucket": label, "mae": bdata["mae"],
                    "count": bdata["count"],
                    "confidence_band": bdata["confidence_band"]})

    total_classified = sum(tier_counts.values())
    pcts = {}
    for t in ALL_DIFFICULTY_TIERS:
        pcts[t] = round(tier_counts.get(t, 0) / max(total_classified, 1) * 100, 2)

    summary = DifficultyTierSummary(
        target=target, total_materials=total_classified,
        tier_counts=dict(tier_counts), tier_percentages=pcts,
        hardest_buckets=hardest,
        sparse_elements=sorted(sparse_elems)[:30],
        rare_spacegroups=sorted(rare_sgs)[:20],
        created_at=now)

    return summary, hard_cases
