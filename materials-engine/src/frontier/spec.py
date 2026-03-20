"""Frontier specification — profiles, candidates, and results.

Phase IV.C: Dual-target multiobjectve frontier using promoted production models.
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict

# Source types
SRC_CORPUS = "known_corpus_candidate"
SRC_GENERATED = "generated_hypothesis"
SRC_EVALUATED = "evaluation_candidate"

# Evidence levels (propagated from intelligence layer)
EV_KNOWN = "known"
EV_PREDICTED = "predicted"
EV_STRUCTURE = "computed_from_structure"
EV_COMPOSITION = "computed_from_composition"
EV_PROXY = "proxy"
EV_UNAVAILABLE = "unavailable"


@dataclass
class FrontierProfile:
    """Configurable multiobjectve frontier profile."""
    name: str = ""
    description: str = ""

    # Weights (must sum to 1.0)
    w_stability: float = 0.25       # formation_energy signal
    w_band_gap_fit: float = 0.20    # band gap window fit
    w_novelty: float = 0.20         # novelty score
    w_exotic: float = 0.15          # exotic score
    w_structure_quality: float = 0.10  # structure availability / descriptor richness
    w_validation_priority: float = 0.10  # validation priority from dossier

    # Band gap target window
    band_gap_target: Optional[float] = None   # eV center
    band_gap_tolerance: float = 2.0           # eV half-width

    # Formation energy threshold
    fe_max: float = 1.0   # reject above this (eV/atom)

    # Filters
    novelty_min: float = 0.0
    exotic_min: float = 0.0
    top_k: int = 50
    pool_limit: int = 5000

    def validate(self):
        s = self.w_stability + self.w_band_gap_fit + self.w_novelty + self.w_exotic + self.w_structure_quality + self.w_validation_priority
        if abs(s - 1.0) > 0.02:
            raise ValueError(f"Weights must sum to 1.0, got {s:.4f}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FrontierProfile":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class FrontierCandidate:
    """A scored candidate in the frontier."""
    canonical_id: str = ""
    formula: str = ""
    source_type: str = SRC_CORPUS
    spacegroup: Optional[int] = None
    elements: List[str] = field(default_factory=list)

    # Raw values
    formation_energy: Optional[float] = None
    formation_energy_evidence: str = EV_UNAVAILABLE
    band_gap: Optional[float] = None
    band_gap_evidence: str = EV_UNAVAILABLE
    density: Optional[float] = None
    has_structure: bool = False

    # Scores (0-1)
    stability_score: float = 0.0
    band_gap_fit_score: float = 0.0
    novelty_score: float = 0.0
    exotic_score: float = 0.0
    structure_quality: float = 0.0
    validation_priority_score: float = 0.0
    frontier_score: float = 0.0

    # Decision
    rank: int = 0
    reason_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "canonical_id": self.canonical_id,
            "formula": self.formula,
            "source_type": self.source_type,
            "spacegroup": self.spacegroup,
            "properties": {
                "formation_energy": {"value": self.formation_energy, "evidence": self.formation_energy_evidence},
                "band_gap": {"value": self.band_gap, "evidence": self.band_gap_evidence},
                "density": self.density,
                "has_structure": self.has_structure,
            },
            "scores": {
                "stability": round(self.stability_score, 4),
                "band_gap_fit": round(self.band_gap_fit_score, 4),
                "novelty": round(self.novelty_score, 4),
                "exotic": round(self.exotic_score, 4),
                "structure_quality": round(self.structure_quality, 4),
                "validation_priority": round(self.validation_priority_score, 4),
                "frontier": round(self.frontier_score, 4),
            },
            "rank": self.rank,
            "reason_codes": self.reason_codes,
        }


# ================================================================
# Presets
# ================================================================

def balanced_frontier() -> FrontierProfile:
    return FrontierProfile(
        name="balanced_frontier",
        description="Equal emphasis on stability, electronic utility, and novelty",
        w_stability=0.25, w_band_gap_fit=0.20, w_novelty=0.20,
        w_exotic=0.15, w_structure_quality=0.10, w_validation_priority=0.10,
        fe_max=1.0, top_k=50)


def stable_semiconductor() -> FrontierProfile:
    return FrontierProfile(
        name="stable_semiconductor",
        description="Thermodynamically stable materials with semiconductor band gap (0.5-3.0 eV)",
        w_stability=0.35, w_band_gap_fit=0.30, w_novelty=0.10,
        w_exotic=0.05, w_structure_quality=0.10, w_validation_priority=0.10,
        band_gap_target=1.5, band_gap_tolerance=1.5, fe_max=0.0, top_k=50)


def wide_gap_exotic() -> FrontierProfile:
    return FrontierProfile(
        name="wide_gap_exotic",
        description="Wide band gap (>3 eV) exotic/rare materials for novel insulator/optical applications",
        w_stability=0.15, w_band_gap_fit=0.25, w_novelty=0.25,
        w_exotic=0.20, w_structure_quality=0.05, w_validation_priority=0.10,
        band_gap_target=5.0, band_gap_tolerance=3.0, fe_max=2.0, top_k=50)


def high_novelty_watchlist() -> FrontierProfile:
    return FrontierProfile(
        name="high_novelty_watchlist",
        description="Maximize novelty and exoticism — find the most unexplored materials",
        w_stability=0.10, w_band_gap_fit=0.10, w_novelty=0.35,
        w_exotic=0.30, w_structure_quality=0.05, w_validation_priority=0.10,
        fe_max=3.0, top_k=50)


ALL_FRONTIER_PRESETS = {
    "balanced_frontier": balanced_frontier,
    "stable_semiconductor": stable_semiconductor,
    "wide_gap_exotic": wide_gap_exotic,
    "high_novelty_watchlist": high_novelty_watchlist,
}
