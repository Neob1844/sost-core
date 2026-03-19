"""Campaign specification — configurable search campaigns.

Phase III.C: Formal campaign definitions for reproducible material searches.
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict

from ..shortlist.criteria import ShortlistCriteria

log = logging.getLogger(__name__)

CAMPAIGN_TYPES = [
    "novelty_hunt",
    "exotic_hunt",
    "stability_first",
    "band_gap_target",
    "thermo_pressure_watchlist",
    "custom",
]


class CampaignValidationError(ValueError):
    pass


@dataclass
class CampaignSpec:
    """Full specification for a search campaign."""
    name: str = ""
    campaign_type: str = "custom"
    objective: str = ""

    # Criteria (serialized ShortlistCriteria fields)
    criteria: Optional[dict] = None

    # Conditions
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None

    # Selection
    top_k: int = 20
    pool_limit: int = 50000

    def validate(self) -> None:
        if not self.name:
            raise CampaignValidationError("Campaign name is required")
        if self.campaign_type not in CAMPAIGN_TYPES:
            raise CampaignValidationError(
                f"Unknown type '{self.campaign_type}'. Valid: {CAMPAIGN_TYPES}")
        if self.top_k < 1:
            raise CampaignValidationError(f"top_k must be >= 1")
        if self.criteria:
            c = ShortlistCriteria.from_dict(self.criteria)
            c.validate()

    def get_criteria(self) -> ShortlistCriteria:
        if self.criteria:
            c = ShortlistCriteria.from_dict(self.criteria)
            c.top_k = self.top_k
            return c
        return ShortlistCriteria(top_k=self.top_k)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "CampaignSpec":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})

    def campaign_id(self) -> str:
        """Deterministic ID from spec content."""
        key = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:12]


# ================================================================
# Presets
# ================================================================

def exotic_materials_default() -> CampaignSpec:
    return CampaignSpec(
        name="Exotic Materials Hunt",
        campaign_type="exotic_hunt",
        objective="Find the rarest and most unexplored materials in corpus",
        criteria={
            "w_novelty": 0.20, "w_exotic": 0.45,
            "w_stability": 0.20, "w_property_fit": 0.15,
            "max_formation_energy": 2.0,
        },
        top_k=20,
    )


def low_formation_energy_default() -> CampaignSpec:
    return CampaignSpec(
        name="Low Formation Energy Stable Materials",
        campaign_type="stability_first",
        objective="Find thermodynamically stable materials with low formation energy",
        criteria={
            "max_formation_energy": 0.0,
            "w_novelty": 0.10, "w_exotic": 0.10,
            "w_stability": 0.60, "w_property_fit": 0.20,
        },
        top_k=20,
    )


def band_gap_window_default(target: float = 1.5, tolerance: float = 0.5) -> CampaignSpec:
    return CampaignSpec(
        name=f"Band Gap Window ({target}±{tolerance} eV)",
        campaign_type="band_gap_target",
        objective=f"Find materials with band gap near {target} eV for optoelectronics",
        criteria={
            "band_gap_target": target, "band_gap_tolerance": tolerance,
            "w_novelty": 0.15, "w_exotic": 0.15,
            "w_stability": 0.30, "w_property_fit": 0.40,
        },
        top_k=20,
    )


def tp_sensitive_candidates_default() -> CampaignSpec:
    return CampaignSpec(
        name="T/P Sensitive Watchlist",
        campaign_type="thermo_pressure_watchlist",
        objective="Find materials to monitor under elevated T/P conditions",
        criteria={
            "w_novelty": 0.15, "w_exotic": 0.20,
            "w_stability": 0.40, "w_property_fit": 0.25,
        },
        temperature_K=1200.0,
        pressure_GPa=10.0,
        top_k=20,
    )


def high_novelty_watchlist_default() -> CampaignSpec:
    return CampaignSpec(
        name="High Novelty Watchlist",
        campaign_type="novelty_hunt",
        objective="Find materials most different from the known corpus",
        criteria={
            "w_novelty": 0.50, "w_exotic": 0.25,
            "w_stability": 0.15, "w_property_fit": 0.10,
            "max_formation_energy": 3.0,
        },
        top_k=20,
    )


ALL_PRESETS = {
    "exotic_materials_default": exotic_materials_default,
    "low_formation_energy_default": low_formation_energy_default,
    "band_gap_window_default": band_gap_window_default,
    "tp_sensitive_candidates_default": tp_sensitive_candidates_default,
    "high_novelty_watchlist_default": high_novelty_watchlist_default,
}
