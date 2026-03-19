"""Validation spec — candidate model, plan, and priority scoring.

Phase III.G: Defines the data contract for the validation queue.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List, Dict

log = logging.getLogger(__name__)

# Current statuses
STATUSES = [
    "queued",
    "screened",
    "ready_for_dft",
    "validated_proxy_only",
    "validated_external",
    "rejected",
    "archived",
]

# Priority bands
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

# Reason codes
RC_DUPLICATE = "duplicate_validation_candidate"
RC_ALREADY_KNOWN = "already_known_material"
RC_NEAR_KNOWN = "near_known_material"
RC_LOW_PLAUSIBILITY = "low_plausibility"
RC_PREDICTED_UNSTABLE = "predicted_unstable"
RC_INSUFFICIENT_STRUCTURE = "insufficient_structure"
RC_NEEDS_REVIEW = "needs_manual_review"
RC_READY_DFT = "ready_for_dft"
RC_HIGH_INFO = "high_information_value"

# Validation ladder stages
VALIDATION_STAGES = [
    {
        "stage": 0, "name": "dedup_rejection",
        "method": "corpus_match + fingerprint_dedup",
        "cost_class": "zero", "compute_class": "cpu_light",
        "acceptance_rule": "not duplicate, not exact_known",
        "rejection_rule": "exact_known OR duplicate in queue",
        "outputs": ["status: rejected or queued"],
    },
    {
        "stage": 1, "name": "novelty_exotic_screen",
        "method": "novelty_filter + exotic_score + plausibility",
        "cost_class": "zero", "compute_class": "cpu_light",
        "acceptance_rule": "novelty_band != known, plausibility > 0.3",
        "rejection_rule": "known duplicate OR plausibility < 0.2",
        "outputs": ["novelty_score", "exotic_score", "plausibility"],
    },
    {
        "stage": 2, "name": "proxy_screening",
        "method": "T/P heuristic + application fit + lift confidence",
        "cost_class": "zero", "compute_class": "cpu_light",
        "acceptance_rule": "evaluation_score > 0.3, no critical risk flags",
        "rejection_rule": "predicted_unstable OR insufficient_structure",
        "outputs": ["evaluation_score", "tp_risk", "application_label"],
    },
    {
        "stage": 3, "name": "ready_for_dft",
        "method": "top candidates after proxy screening",
        "cost_class": "medium", "compute_class": "dft",
        "acceptance_rule": "priority=high AND structure available",
        "rejection_rule": "N/A — manual decision",
        "outputs": ["dft_formation_energy", "dft_band_gap"],
    },
    {
        "stage": 4, "name": "validated_external",
        "method": "human review / literature / experiment",
        "cost_class": "high", "compute_class": "external",
        "acceptance_rule": "external confirmation",
        "rejection_rule": "external rejection",
        "outputs": ["observed_value", "confidence_update"],
    },
    {
        "stage": 5, "name": "learning_candidate",
        "method": "feeds back into model retraining queue",
        "cost_class": "low", "compute_class": "cpu_heavy",
        "acceptance_rule": "validated with observed value + high info value",
        "rejection_rule": "N/A",
        "outputs": ["retrain_queue_entry"],
    },
]


@dataclass
class ValidationCandidate:
    """A candidate in the validation queue."""
    validation_id: str = ""
    source_type: str = ""       # corpus_material | generated_candidate | evaluation_candidate
    source_ref: str = ""        # canonical_id or candidate_id or run_id
    formula: str = ""
    spacegroup: Optional[int] = None
    elements: List[str] = field(default_factory=list)
    candidate_id: Optional[str] = None
    dossier_ref: Optional[str] = None
    evaluation_ref: Optional[str] = None

    # Scores
    novelty_score: float = 0.0
    exotic_score: float = 0.0
    evaluation_score: float = 0.0
    validation_priority_score: float = 0.0
    validation_priority_band: str = PRIORITY_LOW

    # Status
    current_status: str = "queued"
    status_reason_codes: List[str] = field(default_factory=list)

    # Metadata
    created_at: str = ""
    updated_at: str = ""
    tags: List[str] = field(default_factory=list)
    notes: str = ""

    # Calibration
    benchmark_confidence_band: str = "unknown"
    expected_error_band: Optional[float] = None
    benchmark_support_score: float = 0.0
    evidence_count: int = 0
    external_evidence_present: bool = False
    calibrated_priority_note: str = ""

    # Context
    evidence_summary: Optional[dict] = None
    thermo_pressure_context: Optional[dict] = None
    validation_plan: Optional[List[dict]] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationCandidate":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


def compute_roi_score(novelty: float, exotic: float, eval_score: float,
                      structure_confidence: float, app_relevance: float,
                      estimated_cost: float = 0.0,
                      duplicate_penalty: float = 0.0) -> float:
    """Compute Return-on-Investment score for validation prioritization.

    Favors high information value + low cost.
    """
    info_value = (0.25 * novelty + 0.15 * exotic + 0.25 * eval_score
                  + 0.20 * structure_confidence + 0.15 * app_relevance)

    cost_factor = max(0.1, 1.0 - estimated_cost)  # lower cost → higher factor
    dedup_factor = max(0.0, 1.0 - duplicate_penalty)

    return max(0.0, min(1.0, info_value * cost_factor * dedup_factor))
