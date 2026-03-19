"""Shortlist criteria — configurable selection and ranking parameters.

Phase III.B: Reproducible criteria for candidate filtering and ranking.
All weights and thresholds are explicit, serializable, and documented.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List

log = logging.getLogger(__name__)


class CriteriaValidationError(ValueError):
    """Raised when criteria are invalid."""
    pass


@dataclass
class ShortlistCriteria:
    """Configurable criteria for shortlist building.

    Hard filters (reject if not met):
      - require_valid_structure: material must have validated crystal structure
      - require_properties: list of property fields that must be non-null
      - max_formation_energy: reject if formation_energy > threshold (eV/atom)
      - novelty_min: reject if novelty_score < threshold

    Soft filters (penalize but don't reject):
      - exotic_min: below this → watchlist instead of accepted
      - band_gap_target: preferred band gap center (eV)
      - band_gap_tolerance: accepted band gap range around target (eV)

    Ranking weights (must sum to 1.0):
      - w_novelty, w_exotic, w_stability, w_property_fit

    Selection:
      - top_k: maximum number of candidates in final shortlist
    """
    # Hard filters
    require_valid_structure: bool = False
    require_properties: List[str] = field(default_factory=lambda: ["formation_energy"])
    max_formation_energy: Optional[float] = 1.0     # eV/atom — reject above
    novelty_min: float = 0.0                         # no novelty requirement by default

    # Soft filters
    exotic_min: float = 0.0                          # no exotic requirement by default
    band_gap_target: Optional[float] = None          # eV — center of desired range
    band_gap_tolerance: float = 2.0                  # eV — half-width around target

    # Ranking weights
    w_novelty: float = 0.25
    w_exotic: float = 0.25
    w_stability: float = 0.30
    w_property_fit: float = 0.20

    # Selection
    top_k: int = 20

    def validate(self) -> None:
        """Validate criteria consistency."""
        weight_sum = self.w_novelty + self.w_exotic + self.w_stability + self.w_property_fit
        if abs(weight_sum - 1.0) > 0.01:
            raise CriteriaValidationError(
                f"Ranking weights must sum to 1.0, got {weight_sum:.4f}")
        if self.top_k < 1:
            raise CriteriaValidationError(f"top_k must be >= 1, got {self.top_k}")
        for w_name in ["w_novelty", "w_exotic", "w_stability", "w_property_fit"]:
            val = getattr(self, w_name)
            if val < 0.0 or val > 1.0:
                raise CriteriaValidationError(f"{w_name}={val} out of range [0, 1]")
        if self.novelty_min < 0.0 or self.novelty_min > 1.0:
            raise CriteriaValidationError(f"novelty_min={self.novelty_min} out of [0,1]")
        if self.exotic_min < 0.0 or self.exotic_min > 1.0:
            raise CriteriaValidationError(f"exotic_min={self.exotic_min} out of [0,1]")
        if self.band_gap_tolerance < 0:
            raise CriteriaValidationError("band_gap_tolerance must be >= 0")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "ShortlistCriteria":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


def default_criteria() -> ShortlistCriteria:
    """Sensible defaults for general-purpose candidate selection."""
    return ShortlistCriteria()


def stability_focused() -> ShortlistCriteria:
    """Criteria focused on thermodynamic stability."""
    return ShortlistCriteria(
        max_formation_energy=0.0,
        w_novelty=0.15, w_exotic=0.15, w_stability=0.50, w_property_fit=0.20)


def novelty_focused() -> ShortlistCriteria:
    """Criteria focused on discovering novel candidates."""
    return ShortlistCriteria(
        novelty_min=0.0, exotic_min=0.1,
        max_formation_energy=2.0,
        w_novelty=0.40, w_exotic=0.30, w_stability=0.15, w_property_fit=0.15)
