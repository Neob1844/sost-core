"""Data structures for hard-case mining and selective retraining preparation.

Phase IV.K: Analyze model weaknesses, mine hard cases, build intelligent
retraining datasets. Does NOT retrain — only prepares.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

# --- Difficulty tiers ---
DIFF_EASY = "easy"
DIFF_MEDIUM = "medium"
DIFF_HARD = "hard"
DIFF_SPARSE_EXOTIC = "sparse_exotic"
DIFF_HIGH_VALUE_RETRAIN = "high_value_retrain"
DIFF_HOLDOUT_CANDIDATE = "holdout_candidate"

ALL_DIFFICULTY_TIERS = [
    DIFF_EASY, DIFF_MEDIUM, DIFF_HARD,
    DIFF_SPARSE_EXOTIC, DIFF_HIGH_VALUE_RETRAIN, DIFF_HOLDOUT_CANDIDATE,
]

DIFF_DESCRIPTIONS = {
    DIFF_EASY: "Model predicts well (within HIGH confidence band). Common chemistry, frequent SG.",
    DIFF_MEDIUM: "Model predicts with moderate error (MEDIUM band). Some structural/chemical complexity.",
    DIFF_HARD: "Model struggles (LOW band or known hotspot). Rare value ranges, complex structures.",
    DIFF_SPARSE_EXOTIC: "Rare elements, infrequent SGs, 4+ components. Model has little training signal.",
    DIFF_HIGH_VALUE_RETRAIN: "Hard + high scientific value. Priority for inclusion in retraining sets.",
    DIFF_HOLDOUT_CANDIDATE: "Good for held-out validation. Representative but not critical for training.",
}

# --- Retraining priority levels ---
PRIORITY_CRITICAL = "critical"
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"
PRIORITY_DEFER = "defer"


@dataclass
class HardCaseRecord:
    """A material identified as difficult for the current model."""
    canonical_id: str = ""
    formula: str = ""
    source: str = ""
    target: str = ""
    difficulty_tier: str = DIFF_MEDIUM
    n_elements: int = 0
    spacegroup: Optional[int] = None
    actual_value: Optional[float] = None
    confidence_band: str = "unknown"
    expected_error: float = 0.0
    element_rarity: float = 0.0
    sg_rarity: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DifficultyTierSummary:
    """Summary of difficulty tier distribution for a target."""
    target: str = ""
    total_materials: int = 0
    tier_counts: Dict[str, int] = field(default_factory=dict)
    tier_percentages: Dict[str, float] = field(default_factory=dict)
    hardest_buckets: List[Dict] = field(default_factory=list)
    sparse_elements: List[str] = field(default_factory=list)
    rare_spacegroups: List[int] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SelectiveDatasetPlan:
    """A proposed dataset for selective retraining."""
    dataset_id: str = ""
    name: str = ""
    target: str = ""
    size: int = 0
    selection_logic: str = ""
    composition_summary: Dict = field(default_factory=dict)
    element_diversity: int = 0
    sg_diversity: int = 0
    reason_for_existence: str = ""
    expected_benefit: str = ""
    risk_note: str = ""
    priority_score: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrainingPriorityScore:
    """Scored dataset proposal for retraining prioritization."""
    dataset_id: str = ""
    dataset_name: str = ""
    target: str = ""
    overall_score: float = 0.0
    benefit_score: float = 0.0
    difficulty_concentration: float = 0.0
    diversity_score: float = 0.0
    sparse_coverage: float = 0.0
    exotic_value: float = 0.0
    overfit_risk: float = 0.0
    training_cost: float = 0.0
    rank: int = 0
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrainingPrepReport:
    """Full report combining all retraining preparation analysis."""
    hardcase_summary: Dict = field(default_factory=dict)
    difficulty_tiers: Dict = field(default_factory=dict)
    datasets: List[Dict] = field(default_factory=list)
    priority_ranking: List[Dict] = field(default_factory=list)
    recommendation: str = ""
    next_action: str = ""
    do_not: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
