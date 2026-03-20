"""Triage specification — profiles, decisions, and actions.

Phase IV.E: Pre-DFT triage gate — cheap-first decision on which candidates
deserve budget for more serious validation.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict

# Triage decisions
DECISION_APPROVED = "approved_for_budgeted_validation"
DECISION_MANUAL = "needs_manual_review"
DECISION_WATCHLIST = "watchlist_only"
DECISION_REJECT = "reject_for_now"

# Next actions
ACTION_PROMOTE = "promote_to_budget_candidate"
ACTION_REVIEW = "review_with_human"
ACTION_KEEP = "keep_in_queue"
ACTION_HOLD = "hold_as_reference"
ACTION_DEFER = "defer_until_better_evidence"
ACTION_DROP = "drop_from_priority_set"


@dataclass
class TriageProfile:
    """Configurable triage gate profile."""
    name: str = ""
    description: str = ""

    # Thresholds
    approve_min_frontier: float = 0.45
    approve_min_novelty: float = 0.1
    reject_max_risk_flags: int = 4
    reject_if_known_low_novelty: bool = True
    require_structure: bool = False

    # Weights for triage score
    w_frontier: float = 0.30
    w_calibration: float = 0.15
    w_evidence: float = 0.15
    w_novelty: float = 0.20
    w_structure: float = 0.10
    w_risk_penalty: float = 0.10

    top_k: int = 50

    def validate(self):
        s = self.w_frontier + self.w_calibration + self.w_evidence + self.w_novelty + self.w_structure + self.w_risk_penalty
        if abs(s - 1.0) > 0.02:
            raise ValueError(f"Weights must sum to 1.0, got {s:.4f}")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TriageProfile":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


@dataclass
class TriageResult:
    """Result for a single triaged candidate."""
    pack_id: str = ""
    formula: str = ""
    source_type: str = ""

    # Scores
    frontier_score: float = 0.0
    triage_score: float = 0.0

    # Decision
    decision: str = DECISION_WATCHLIST
    next_action: str = ACTION_KEEP
    reason_codes: List[str] = field(default_factory=list)
    risk_flags: List[str] = field(default_factory=list)

    # Context
    calibration_band: str = "unknown"
    evidence_strength: float = 0.0
    novelty_score: float = 0.0
    has_structure: bool = False
    human_summary: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_markdown(self) -> str:
        emoji = {"approved_for_budgeted_validation": "✅",
                 "needs_manual_review": "🔍", "watchlist_only": "👁",
                 "reject_for_now": "❌"}.get(self.decision, "?")
        md = f"**{emoji} {self.formula}** — `{self.decision}`\n"
        md += f"  Frontier: {self.frontier_score:.3f} | Triage: {self.triage_score:.3f}\n"
        md += f"  Action: `{self.next_action}` | Cal: {self.calibration_band}\n"
        if self.reason_codes:
            md += f"  Reasons: {', '.join(self.reason_codes[:4])}\n"
        if self.risk_flags:
            md += f"  Risks: {', '.join(self.risk_flags[:3])}\n"
        return md


# ================================================================
# Presets
# ================================================================

def strict_budget_gate() -> TriageProfile:
    return TriageProfile(
        name="strict_budget_gate",
        description="Only approve candidates with strong evidence and high frontier score",
        approve_min_frontier=0.50, approve_min_novelty=0.15,
        reject_max_risk_flags=3, reject_if_known_low_novelty=True,
        require_structure=True,
        w_frontier=0.30, w_calibration=0.20, w_evidence=0.20,
        w_novelty=0.15, w_structure=0.05, w_risk_penalty=0.10)


def balanced_review_gate() -> TriageProfile:
    return TriageProfile(
        name="balanced_review_gate",
        description="Balanced triage — approve good candidates, flag borderline for review",
        approve_min_frontier=0.40, approve_min_novelty=0.05,
        reject_max_risk_flags=5, reject_if_known_low_novelty=True,
        w_frontier=0.30, w_calibration=0.15, w_evidence=0.15,
        w_novelty=0.20, w_structure=0.10, w_risk_penalty=0.10)


def exotic_patience_gate() -> TriageProfile:
    return TriageProfile(
        name="exotic_patience_gate",
        description="Patient gate for exotic/novel candidates — tolerate higher risk for novelty",
        approve_min_frontier=0.35, approve_min_novelty=0.0,
        reject_max_risk_flags=6, reject_if_known_low_novelty=False,
        w_frontier=0.20, w_calibration=0.10, w_evidence=0.10,
        w_novelty=0.35, w_structure=0.05, w_risk_penalty=0.20)


def stable_semiconductor_gate() -> TriageProfile:
    return TriageProfile(
        name="stable_semiconductor_gate",
        description="Gate for stable semiconductors — strict on stability and BG fit",
        approve_min_frontier=0.45, approve_min_novelty=0.0,
        reject_max_risk_flags=4, reject_if_known_low_novelty=True,
        require_structure=True,
        w_frontier=0.35, w_calibration=0.20, w_evidence=0.15,
        w_novelty=0.10, w_structure=0.10, w_risk_penalty=0.10)


ALL_TRIAGE_PRESETS = {
    "strict_budget_gate": strict_budget_gate,
    "balanced_review_gate": balanced_review_gate,
    "exotic_patience_gate": exotic_patience_gate,
    "stable_semiconductor_gate": stable_semiconductor_gate,
}
