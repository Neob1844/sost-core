"""Niche campaign specification and result models.

Phase IV.F: Themed discovery campaigns combining frontier + triage + validation packs.
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict

# Niche tags
TAG_STABLE_SEMI = "stable_semiconductor"
TAG_WIDE_GAP = "wide_gap_exotic"
TAG_NOVEL_WATCH = "novel_watchlist"
TAG_GEN_INTEREST = "generated_high_interest"
TAG_KNOWN_REF = "known_reference"
TAG_BUDGET = "budget_candidate"


@dataclass
class NicheCampaignSpec:
    """Full specification for a niche discovery campaign."""
    name: str = ""
    objective: str = ""
    source_mode: str = "corpus"  # corpus | generated | mixed

    # Frontier profile name (from ALL_FRONTIER_PRESETS)
    frontier_profile: str = "balanced_frontier"
    # Triage profile name (from ALL_TRIAGE_PRESETS)
    triage_profile: str = "balanced_review_gate"

    # Filters
    band_gap_target: Optional[float] = None
    band_gap_tolerance: float = 2.0
    fe_max: float = 1.0
    novelty_min: float = 0.0
    exotic_min: float = 0.0
    require_structure: bool = False

    # Selection
    frontier_top_k: int = 50
    triage_top_k: int = 20
    pool_limit: int = 5000

    # Niche tags to assign
    niche_tags: List[str] = field(default_factory=list)
    notes: str = ""

    def campaign_id(self) -> str:
        key = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NicheCampaignSpec":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class NicheCandidate:
    """A candidate with niche tags and triage decision."""
    formula: str = ""
    source_type: str = ""
    frontier_score: float = 0.0
    triage_score: float = 0.0
    triage_decision: str = ""
    next_action: str = ""
    niche_tags: List[str] = field(default_factory=list)
    reason_codes: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    properties: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ================================================================
# Presets
# ================================================================

def stable_semiconductor_hunt() -> NicheCampaignSpec:
    return NicheCampaignSpec(
        name="stable_semiconductor_hunt",
        objective="Find thermodynamically stable materials with semiconductor band gap (0.5-3.0 eV)",
        frontier_profile="stable_semiconductor",
        triage_profile="stable_semiconductor_gate",
        band_gap_target=1.5, band_gap_tolerance=1.5, fe_max=0.0,
        niche_tags=[TAG_STABLE_SEMI, TAG_BUDGET],
        frontier_top_k=50, triage_top_k=20)


def wide_gap_exotic_hunt() -> NicheCampaignSpec:
    return NicheCampaignSpec(
        name="wide_gap_exotic_hunt",
        objective="Find exotic/rare wide-gap (>3 eV) materials for novel insulator/optical applications",
        frontier_profile="wide_gap_exotic",
        triage_profile="exotic_patience_gate",
        band_gap_target=5.0, band_gap_tolerance=3.0, fe_max=2.0,
        niche_tags=[TAG_WIDE_GAP],
        frontier_top_k=50, triage_top_k=20)


def high_novelty_watchlist() -> NicheCampaignSpec:
    return NicheCampaignSpec(
        name="high_novelty_watchlist",
        objective="Maximize novelty and exoticism — find the most unexplored materials",
        frontier_profile="high_novelty_watchlist",
        triage_profile="exotic_patience_gate",
        novelty_min=0.0, fe_max=3.0,
        niche_tags=[TAG_NOVEL_WATCH],
        frontier_top_k=50, triage_top_k=20)


def balanced_exotic_opportunities() -> NicheCampaignSpec:
    return NicheCampaignSpec(
        name="balanced_exotic_opportunities",
        objective="Balanced search across stability, band gap, novelty, and exoticism",
        frontier_profile="balanced_frontier",
        triage_profile="balanced_review_gate",
        niche_tags=[TAG_BUDGET],
        frontier_top_k=50, triage_top_k=20)


def generated_candidate_review() -> NicheCampaignSpec:
    return NicheCampaignSpec(
        name="generated_candidate_review",
        objective="Review generated/evaluated candidates for validation potential",
        source_mode="generated",
        frontier_profile="balanced_frontier",
        triage_profile="balanced_review_gate",
        niche_tags=[TAG_GEN_INTEREST],
        frontier_top_k=30, triage_top_k=15)


ALL_NICHE_PRESETS = {
    "stable_semiconductor_hunt": stable_semiconductor_hunt,
    "wide_gap_exotic_hunt": wide_gap_exotic_hunt,
    "high_novelty_watchlist": high_novelty_watchlist,
    "balanced_exotic_opportunities": balanced_exotic_opportunities,
    "generated_candidate_review": generated_candidate_review,
}
