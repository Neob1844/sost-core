"""Feedback and memory — record outcomes for future learning.

Phase III.G: Scaffold for the learning loop. Records predictions vs observations
so the system can identify model failures and promising regions.

NOT an active retraining system yet — just the memory layer.
"""

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List

log = logging.getLogger(__name__)

FEEDBACK_DIR = "artifacts/learning"
FEEDBACK_FILE = "feedback_log.json"


@dataclass
class FeedbackEntry:
    """A single feedback record: prediction vs observation."""
    feedback_id: str = ""
    validation_id: Optional[str] = None
    candidate_id: Optional[str] = None
    formula: str = ""
    elements: List[str] = field(default_factory=list)
    spacegroup: Optional[int] = None

    # What was predicted
    target_property: str = ""
    predicted_value: Optional[float] = None
    prediction_model: Optional[str] = None
    confidence_before: str = "predicted"

    # What was observed
    observed_result_type: str = "proxy_check"  # manual_review | external_reference | proxy_check | future_dft | future_experiment
    observed_value: Optional[float] = None
    error: Optional[float] = None
    evidence_after: str = "proxy"

    # Decision
    decision: str = "keep"  # keep | downgrade_confidence | promote | archive | needs_retrain
    reviewer: str = "system"
    source_note: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FeedbackEntry":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


class FeedbackMemory:
    """Persistent feedback storage."""

    def __init__(self, output_dir: str = FEEDBACK_DIR):
        self.output_dir = output_dir
        self._entries: List[FeedbackEntry] = []

    @property
    def size(self) -> int:
        return len(self._entries)

    def add(self, entry: FeedbackEntry) -> str:
        """Add a feedback entry. Returns feedback_id."""
        import hashlib
        now = datetime.now(timezone.utc).isoformat()
        if not entry.feedback_id:
            entry.feedback_id = hashlib.sha256(
                f"fb|{entry.formula}|{entry.target_property}|{now}".encode()
            ).hexdigest()[:12]
        if not entry.timestamp:
            entry.timestamp = now

        # Compute error if both values present
        if (entry.predicted_value is not None and entry.observed_value is not None
                and entry.error is None):
            entry.error = round(abs(entry.predicted_value - entry.observed_value), 4)

        self._entries.append(entry)
        log.info("Feedback recorded: %s/%s error=%s decision=%s",
                 entry.formula, entry.target_property, entry.error, entry.decision)
        return entry.feedback_id

    def status(self) -> dict:
        """Summary of feedback memory."""
        from collections import Counter
        decisions = Counter(e.decision for e in self._entries)
        types = Counter(e.observed_result_type for e in self._entries)
        errors = [e.error for e in self._entries if e.error is not None]
        return {
            "total_entries": self.size,
            "by_decision": dict(decisions),
            "by_result_type": dict(types),
            "mean_error": round(sum(errors) / len(errors), 4) if errors else None,
            "entries_with_error": len(errors),
        }

    def get_entries(self, formula: Optional[str] = None,
                    decision: Optional[str] = None) -> List[dict]:
        """Filter feedback entries."""
        results = self._entries
        if formula:
            results = [e for e in results if e.formula == formula]
        if decision:
            results = [e for e in results if e.decision == decision]
        return [e.to_dict() for e in results]

    def save(self) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, FEEDBACK_FILE)
        with open(path, "w") as f:
            json.dump([e.to_dict() for e in self._entries], f, indent=2)
        return path

    def load(self) -> bool:
        path = os.path.join(self.output_dir, FEEDBACK_FILE)
        if not os.path.exists(path):
            return False
        with open(path) as f:
            data = json.load(f)
        self._entries = [FeedbackEntry.from_dict(d) for d in data]
        return True
