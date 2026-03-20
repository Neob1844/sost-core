"""Frontier scoring — dual-target multiobjectve scoring functions.

Phase IV.C: Combines formation_energy + band_gap + novelty + exotic + structure
into a single configurable frontier score.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


def stability_score(formation_energy: Optional[float]) -> float:
    """Map formation energy to [0, 1]. Lower fe → higher stability."""
    if formation_energy is None:
        return 0.2  # unknown → low default
    return max(0.0, min(1.0, (2.0 - formation_energy) / 5.0))


def band_gap_fit_score(band_gap: Optional[float],
                       target: Optional[float],
                       tolerance: float = 2.0) -> float:
    """How close band gap is to target window. Returns 0-1."""
    if target is None:
        return 0.5  # no preference → neutral
    if band_gap is None:
        return 0.2  # missing → low
    dist = abs(band_gap - target)
    if tolerance <= 0:
        return 1.0 if dist == 0 else 0.0
    return max(0.0, 1.0 - dist / tolerance)


def structure_quality_score(has_structure: bool,
                            density: Optional[float] = None) -> float:
    """Quality signal from structure availability and computed descriptors."""
    score = 0.0
    if has_structure:
        score += 0.6
    if density is not None and density > 0:
        score += 0.4  # has real density = structure analytics available
    return min(1.0, score)


def compute_frontier_score(profile, candidate) -> float:
    """Compute the weighted frontier score."""
    return (profile.w_stability * candidate.stability_score
            + profile.w_band_gap_fit * candidate.band_gap_fit_score
            + profile.w_novelty * candidate.novelty_score
            + profile.w_exotic * candidate.exotic_score
            + profile.w_structure_quality * candidate.structure_quality
            + profile.w_validation_priority * candidate.validation_priority_score)


def assign_reason_codes(candidate) -> list:
    """Generate explanation reason codes for a frontier candidate."""
    codes = []
    if candidate.stability_score > 0.7:
        codes.append("strong_stability_signal")
    elif candidate.stability_score < 0.3:
        codes.append("weak_stability_signal")
    if candidate.band_gap_fit_score > 0.7:
        codes.append("good_band_gap_window_fit")
    elif candidate.band_gap_fit_score < 0.3:
        codes.append("poor_band_gap_fit")
    if candidate.novelty_score > 0.3:
        codes.append("high_novelty")
    if candidate.exotic_score > 0.2:
        codes.append("high_exotic_score")
    if candidate.structure_quality < 0.3:
        codes.append("low_structure_quality")
    if candidate.source_type == "known_corpus_candidate":
        codes.append("known_material")
    if candidate.validation_priority_score < 0.2:
        codes.append("weak_validation_priority")
    return codes
