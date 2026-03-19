"""Shortlist ranking — score computation and decision assignment.

Phase III.B: Reproducible ranking with explicit decision bands.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger(__name__)

# Decision thresholds (applied to shortlist_score)
ACCEPTED_THRESHOLD = 0.35
WATCHLIST_THRESHOLD = 0.15


@dataclass
class CandidateResult:
    """Full assessment for a single shortlist candidate."""
    canonical_id: str = ""
    formula: str = ""
    source: str = ""
    spacegroup: Optional[int] = None
    band_gap: Optional[float] = None
    formation_energy: Optional[float] = None

    # Scores
    novelty_score: float = 0.0
    exotic_score: float = 0.0
    stability_score: float = 0.0
    property_fit_score: float = 0.0
    shortlist_score: float = 0.0

    # Screening
    screening_reliability: str = "not_available"

    # Decision
    rank: int = 0
    decision: str = "rejected"       # accepted | watchlist | rejected
    reason_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "canonical_id": self.canonical_id,
            "formula": self.formula,
            "source": self.source,
            "spacegroup": self.spacegroup,
            "band_gap": self.band_gap,
            "formation_energy": self.formation_energy,
            "scores": {
                "novelty": round(self.novelty_score, 4),
                "exotic": round(self.exotic_score, 4),
                "stability": round(self.stability_score, 4),
                "property_fit": round(self.property_fit_score, 4),
                "shortlist": round(self.shortlist_score, 4),
            },
            "screening_reliability": self.screening_reliability,
            "rank": self.rank,
            "decision": self.decision,
            "reason_codes": self.reason_codes,
        }


def compute_stability_score(formation_energy: Optional[float],
                            energy_above_hull: Optional[float] = None) -> float:
    """Stability score from thermodynamic properties.

    Returns 0.0 (unstable/unknown) to 1.0 (very stable).
    Uses formation energy as primary signal:
      fe < -3 eV/atom → score ~1.0
      fe ~ 0 eV/atom  → score ~0.5
      fe > 1 eV/atom  → score ~0.0
    """
    if formation_energy is None:
        return 0.3  # unknown → moderate-low default
    # Sigmoid-like mapping: lower fe → higher stability
    # Map [-5, +2] → [1.0, 0.0] roughly
    score = max(0.0, min(1.0, (2.0 - formation_energy) / 5.0))
    # Boost if energy_above_hull is available and low
    if energy_above_hull is not None and energy_above_hull < 0.05:
        score = min(1.0, score + 0.15)
    return score


def compute_property_fit(band_gap: Optional[float],
                         target: Optional[float],
                         tolerance: float = 2.0) -> float:
    """Property fit score — how close band gap is to target.

    Returns 1.0 if band_gap == target, decreasing with distance.
    Returns 0.5 if no target specified or no band_gap available.
    """
    if target is None:
        return 0.5  # no preference → neutral
    if band_gap is None:
        return 0.3  # missing data → low but not zero
    distance = abs(band_gap - target)
    if tolerance <= 0:
        return 1.0 if distance == 0 else 0.0
    return max(0.0, 1.0 - distance / tolerance)


def assign_decision(shortlist_score: float,
                    reason_codes: List[str]) -> str:
    """Assign decision band based on score and flags."""
    # Hard rejection reasons override score
    hard_rejects = {"missing_required_property", "structure_invalid",
                    "formation_energy_too_high", "below_novelty_minimum"}
    if hard_rejects & set(reason_codes):
        return "rejected"
    if shortlist_score >= ACCEPTED_THRESHOLD:
        return "accepted"
    if shortlist_score >= WATCHLIST_THRESHOLD:
        return "watchlist"
    return "rejected"
