"""Active learning proposals — error analysis and retraining recommendations.

Phase IV.G: Does NOT retrain. Only analyzes and proposes.
"""

import json
import logging
import os
from typing import List, Optional, Dict

from ..calibration.confidence import load_calibration
from .spec import (
    ErrorHotspot, RetrainingProposal, CorpusExpansionItem, SOURCES,
    PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW, PRIORITY_WAIT,
)

log = logging.getLogger(__name__)


def detect_error_hotspots() -> List[ErrorHotspot]:
    """Detect regions where the model performs poorly from saved calibrations."""
    hotspots = []

    for target in ["formation_energy", "band_gap"]:
        cal = load_calibration(target)
        if not cal:
            continue

        overall_mae = cal.get("overall_mae", 999)

        # Check per-bucket
        for bucket_type in ["by_element_count", "by_value_range"]:
            buckets = cal.get(bucket_type, {})
            for label, stats in buckets.items():
                mae = stats.get("mae", 0)
                count = stats.get("count", 0)
                band = stats.get("confidence_band", "unknown")

                # Flag if MAE is significantly worse than overall
                if mae > overall_mae * 1.5 and count >= 5:
                    hotspots.append(ErrorHotspot(
                        target=target,
                        bucket_type=bucket_type.replace("by_", ""),
                        bucket_label=label,
                        mae=mae,
                        sample_count=count,
                        confidence_band=band,
                        severity=PRIORITY_HIGH if mae > overall_mae * 2 else PRIORITY_MEDIUM,
                        recommendation=f"Model struggles with {target} in {bucket_type} bucket '{label}' — "
                                       f"MAE={mae:.4f} vs overall {overall_mae:.4f}",
                    ))

    return hotspots


def generate_retraining_proposals(hotspots: List[ErrorHotspot]) -> List[RetrainingProposal]:
    """Generate reasoned retraining proposals from error analysis."""
    proposals = []

    # Check if band_gap needs more attention
    bg_hotspots = [h for h in hotspots if h.target == "band_gap"]
    fe_hotspots = [h for h in hotspots if h.target == "formation_energy"]

    if len(bg_hotspots) > len(fe_hotspots):
        proposals.append(RetrainingProposal(
            proposal_id="retrain_bg_priority",
            target="band_gap",
            priority=PRIORITY_HIGH,
            reason=f"Band gap has {len(bg_hotspots)} error hotspots vs {len(fe_hotspots)} for formation energy",
            expected_benefit="Reduce MAE in underperforming buckets",
            required_data="More materials with diverse band gap values, especially extreme ranges",
            recommended_rung="20K selective (focus on underperforming regions)",
            notes="Consider ALIGNN-Lite with lower learning rate or more epochs for problematic ranges",
        ))

    if fe_hotspots:
        proposals.append(RetrainingProposal(
            proposal_id="retrain_fe_targeted",
            target="formation_energy",
            priority=PRIORITY_MEDIUM,
            reason=f"{len(fe_hotspots)} error hotspots detected in formation energy prediction",
            expected_benefit="Improve accuracy for complex/multi-element materials",
            required_data="Materials from underperforming element count or value range buckets",
            recommended_rung="20K with augmented sampling from sparse regions",
        ))

    # General expansion proposal
    proposals.append(RetrainingProposal(
        proposal_id="expand_then_retrain",
        target="both",
        priority=PRIORITY_MEDIUM,
        reason="Corpus expansion before retraining typically yields better gains than retraining alone",
        expected_benefit="Broader coverage → better generalization → lower error across all buckets",
        required_data="COD (~530K), Materials Project (~150K), AFLOW (~3.5M)",
        recommended_rung="After expansion: 40K or selective 20K from expanded corpus",
        notes="Expand corpus first, then retrain — this is the highest ROI strategy",
    ))

    # Wait proposal if few hotspots
    if len(hotspots) < 2:
        proposals.append(RetrainingProposal(
            proposal_id="wait_for_evidence",
            target="both",
            priority=PRIORITY_WAIT,
            reason="Few error hotspots detected — current models are performing adequately",
            expected_benefit="Save compute for when more evidence accumulates",
            required_data="More feedback entries, more benchmark results, more evidence imports",
            recommended_rung="Wait until 50+ feedback entries or significant corpus expansion",
        ))

    return proposals


def plan_corpus_expansion() -> List[CorpusExpansionItem]:
    """Plan which sources to expand the corpus with, prioritized by value."""
    items = []

    priorities = {
        "materials_project": (PRIORITY_HIGH, "high", "low",
                              "Best-curated open DFT database — high-quality properties + structures"),
        "cod": (PRIORITY_MEDIUM, "medium", "moderate",
                "Huge structure database — adds structural diversity but fewer computed properties"),
        "aflow": (PRIORITY_MEDIUM, "high", "moderate",
                  "Large autonomous DFT library — good for rare combinations"),
        "oqmd": (PRIORITY_LOW, "medium", "moderate",
                 "Large but overlaps significantly with JARVIS and MP"),
        "nomad": (PRIORITY_LOW, "medium", "hard",
                  "Massive but heterogeneous — needs significant parsing work"),
    }

    for source, info in SOURCES.items():
        if info["status"] == "integrated":
            continue  # Already done
        pri, exotic_val, dedup_risk, note = priorities.get(source, (PRIORITY_LOW, "low", "high", ""))
        items.append(CorpusExpansionItem(
            source=source,
            status=info["status"],
            estimated_materials=info["materials"],
            cost=info["cost"],
            difficulty=info["difficulty"],
            priority=pri,
            value_for_exotic=exotic_val,
            dedup_risk=dedup_risk,
            note=note or info.get("note", ""),
        ))

    items.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2, "wait_for_more_evidence": 3}[x.priority])
    return items
