"""Data structures for hierarchical band_gap modeling.

Phase IV.N: Metal gate + non-metal regressor pipeline.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict

METAL_THRESHOLD = 0.05  # eV — below this is "metal"

DECISION_PROMOTE = "promote"
DECISION_HOLD = "hold"
DECISION_WATCHLIST = "watchlist"


@dataclass
class MetalGateResult:
    """Metrics for the binary metal/non-metal classifier."""
    architecture: str = ""
    threshold: float = METAL_THRESHOLD
    dataset_size: int = 0
    train_size: int = 0
    test_size: int = 0
    accuracy: float = 0.0
    precision_metal: float = 0.0
    recall_metal: float = 0.0
    f1_metal: float = 0.0
    precision_nonmetal: float = 0.0
    recall_nonmetal: float = 0.0
    f1_nonmetal: float = 0.0
    confusion_matrix: Dict = field(default_factory=dict)
    training_time_sec: float = 0.0
    checkpoint: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NonMetalRegressorResult:
    """Metrics for the non-metal band_gap regressor."""
    architecture: str = ""
    dataset_size: int = 0
    train_size: int = 0
    test_size: int = 0
    test_mae: float = 0.0
    test_rmse: float = 0.0
    test_r2: float = 0.0
    bucket_mae: Dict[str, float] = field(default_factory=dict)
    training_time_sec: float = 0.0
    checkpoint: str = ""
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HierarchicalBandGapResult:
    """Combined hierarchical pipeline result."""
    name: str = ""
    gate: Dict = field(default_factory=dict)
    regressor: Dict = field(default_factory=dict)
    pipeline_mae: float = 0.0
    pipeline_rmse: float = 0.0
    pipeline_r2: float = 0.0
    bucket_comparison: List[Dict] = field(default_factory=list)
    total_training_time_sec: float = 0.0
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PromotionDecision:
    """Promotion decision for hierarchical model."""
    target: str = "band_gap"
    decision: str = DECISION_HOLD
    promoted_model: Optional[str] = None
    production_mae: float = 0.0
    hierarchical_mae: float = 0.0
    mae_improvement: float = 0.0
    improvement_pct: float = 0.0
    gate_accuracy: float = 0.0
    regressor_mae: float = 0.0
    bucket_improvements: List[Dict] = field(default_factory=list)
    bucket_regressions: List[Dict] = field(default_factory=list)
    rationale: str = ""
    lessons: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
