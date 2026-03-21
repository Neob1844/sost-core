"""Data structures for stratified/curriculum band_gap retraining.

Phase IV.M: Intelligent mixing preserves global distribution while
overweighting hard regions. Fixes the lesson from IV.L.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

DECISION_PROMOTE = "promote"
DECISION_HOLD = "hold"
DECISION_WATCHLIST = "watchlist"


@dataclass
class StratifiedSample:
    """Describes a stratified dataset composition."""
    name: str = ""
    total_size: int = 0
    strata: Dict[str, int] = field(default_factory=dict)
    strata_sql: Dict[str, str] = field(default_factory=dict)
    actual_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ChallengerResult:
    """Metrics for a stratified/curriculum challenger."""
    challenger_id: str = ""
    name: str = ""
    target: str = "band_gap"
    architecture: str = "alignn_lite"
    strategy: str = ""  # "stratified" or "curriculum"
    dataset_size: int = 0
    train_size: int = 0
    val_size: int = 0
    test_size: int = 0
    strata_summary: Dict = field(default_factory=dict)
    epochs: int = 0
    best_epoch: int = 0
    seed: int = 42
    test_mae: float = 0.0
    test_rmse: float = 0.0
    test_r2: float = 0.0
    training_time_sec: float = 0.0
    checkpoint: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ComparisonEntry:
    """Row in comparison table."""
    name: str = ""
    role: str = ""
    strategy: str = ""
    dataset_size: int = 0
    test_mae: float = 0.0
    test_rmse: float = 0.0
    test_r2: float = 0.0
    mae_delta: float = 0.0
    training_time_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BucketComparison:
    """Per-bucket production vs challenger."""
    bucket_label: str = ""
    production_mae: float = 0.0
    challenger_mae: float = 0.0
    delta: float = 0.0
    improved: bool = False
    sample_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionDecision:
    """Final promotion decision."""
    target: str = "band_gap"
    decision: str = DECISION_HOLD
    promoted_model: Optional[str] = None
    production_mae: float = 0.0
    best_challenger_mae: float = 0.0
    best_challenger_name: str = ""
    mae_improvement: float = 0.0
    improvement_pct: float = 0.0
    bucket_improvements: List[Dict] = field(default_factory=list)
    bucket_regressions: List[Dict] = field(default_factory=list)
    rationale: str = ""
    lessons: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
