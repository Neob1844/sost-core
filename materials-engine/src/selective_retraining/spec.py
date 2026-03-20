"""Data structures for selective retraining challengers and promotion decisions.

Phase IV.L: Train band_gap challengers on selective datasets,
compare vs production, decide promotion.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

DECISION_PROMOTE = "promote"
DECISION_HOLD = "hold"
DECISION_WATCHLIST = "watchlist"


@dataclass
class ChallengerResult:
    """Metrics for a single challenger model."""
    challenger_id: str = ""
    name: str = ""
    target: str = "band_gap"
    architecture: str = "alignn_lite"
    dataset_name: str = ""
    dataset_sql: str = ""
    dataset_size: int = 0
    train_size: int = 0
    val_size: int = 0
    test_size: int = 0
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
    """Single row in the comparison table."""
    name: str = ""
    role: str = ""  # "production" or "challenger"
    dataset_name: str = ""
    dataset_size: int = 0
    test_mae: float = 0.0
    test_rmse: float = 0.0
    test_r2: float = 0.0
    mae_delta: float = 0.0
    rmse_delta: float = 0.0
    r2_delta: float = 0.0
    training_time_sec: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BucketComparison:
    """Per-bucket comparison between production and best challenger."""
    bucket_label: str = ""
    bucket_type: str = ""  # "value_range" or "element_count"
    production_mae: float = 0.0
    challenger_mae: float = 0.0
    delta: float = 0.0
    improved: bool = False
    sample_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionDecision:
    """Final promotion decision for the retraining round."""
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
    do_not: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
