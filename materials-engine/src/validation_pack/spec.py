"""Validation Pack — actionable candidate package for review/validation.

Phase IV.D: Converts frontier results into concrete, exportable, prioritized
packs with evidence, risk flags, and recommended next steps.
"""

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict


# Next-step recommendations
NEXT_KEEP_REF = "keep_as_known_reference"
NEXT_WATCH = "watch_only"
NEXT_PROXY_REVIEW = "queue_for_proxy_review"
NEXT_DFT_QUEUE = "queue_for_dft_when_budget_allows"
NEXT_NEEDS_STRUCTURE = "needs_better_structure"
NEXT_DISCARD = "discard_low_priority"

# Risk flags
RISK_KNOWN = "known_material"
RISK_WEAK_BG = "weak_band_gap_confidence"
RISK_WEAK_STRUCT = "weak_structure_quality"
RISK_HIGH_PROXY = "high_proxy_dependence"
RISK_LIMITED_EV = "limited_evidence"
RISK_GEN_UNVAL = "generated_not_validated"
RISK_NOT_CORPUS = "candidate_not_in_corpus"


@dataclass
class ValidationPack:
    """Complete validation package for a single candidate."""
    pack_id: str = ""
    formula: str = ""
    source_type: str = ""
    material_id: Optional[str] = None
    candidate_id: Optional[str] = None

    # Existence
    existence_status: str = "unknown"

    # Frontier context
    frontier_profile: str = ""
    frontier_score: float = 0.0
    score_breakdown: Dict[str, float] = field(default_factory=dict)

    # Properties with evidence
    properties: Dict[str, dict] = field(default_factory=dict)

    # Scores
    novelty_score: float = 0.0
    exotic_score: float = 0.0

    # Calibration
    calibration_band: str = "unknown"
    expected_error: Optional[float] = None

    # Structure
    has_structure: bool = False
    density: Optional[float] = None
    spacegroup: Optional[int] = None
    n_sites: Optional[int] = None

    # Comparators
    nearest_neighbors: List[dict] = field(default_factory=list)

    # Applications
    likely_applications: List[dict] = field(default_factory=list)

    # Decision
    reason_codes: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)
    recommended_next_step: str = NEXT_WATCH
    human_summary: str = ""

    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_summary_row(self) -> dict:
        """Compact row for CSV/table export."""
        fe = self.properties.get("formation_energy", {}).get("value")
        bg = self.properties.get("band_gap", {}).get("value")
        return {
            "formula": self.formula,
            "source": self.source_type,
            "fe": fe,
            "bg": bg,
            "frontier_score": round(self.frontier_score, 4),
            "novelty": round(self.novelty_score, 4),
            "exotic": round(self.exotic_score, 4),
            "next_step": self.recommended_next_step,
            "risk_flags": "|".join(self.risk_flags),
            "reasons": "|".join(self.reason_codes[:3]),
        }

    def to_markdown(self) -> str:
        """Human-readable markdown card."""
        fe = self.properties.get("formation_energy", {})
        bg = self.properties.get("band_gap", {})
        md = f"### {self.formula}\n\n"
        md += f"- **Source:** {self.source_type}\n"
        md += f"- **Frontier score:** {self.frontier_score:.4f} ({self.frontier_profile})\n"
        md += f"- **Formation energy:** {fe.get('value', '?')} eV/atom [{fe.get('evidence', '?')}]\n"
        md += f"- **Band gap:** {bg.get('value', '?')} eV [{bg.get('evidence', '?')}]\n"
        md += f"- **Novelty:** {self.novelty_score:.3f} | **Exotic:** {self.exotic_score:.3f}\n"
        md += f"- **Structure:** {'yes' if self.has_structure else 'no'}"
        if self.density:
            md += f" | Density: {self.density:.2f} g/cm³"
        md += f"\n- **Calibration:** {self.calibration_band}"
        if self.expected_error:
            md += f" (expected error: {self.expected_error:.3f})"
        md += f"\n- **Next step:** `{self.recommended_next_step}`\n"
        if self.risk_flags:
            md += f"- **Risks:** {', '.join(self.risk_flags)}\n"
        if self.reason_codes:
            md += f"- **Reasons:** {', '.join(self.reason_codes[:5])}\n"
        if self.likely_applications:
            apps = [a['label'] for a in self.likely_applications[:3]]
            md += f"- **Applications:** {', '.join(apps)}\n"
        if self.human_summary:
            md += f"\n> {self.human_summary}\n"
        return md
