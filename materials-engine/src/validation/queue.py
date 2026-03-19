"""Validation queue — persistent, prioritized, dedup-aware.

Phase III.G: Manages the queue of candidates awaiting validation.
Cheap-first: CPU screening before expensive DFT.
"""

import hashlib
import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone
from typing import List, Optional, Dict

from ..storage.db import MaterialsDB
from ..generation.engine import GenerationEngine
from ..generation.evaluator import CandidateEvaluator
from .spec import (
    ValidationCandidate, VALIDATION_STAGES,
    PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW,
    RC_DUPLICATE, RC_ALREADY_KNOWN, RC_NEAR_KNOWN,
    RC_LOW_PLAUSIBILITY, RC_PREDICTED_UNSTABLE,
    RC_INSUFFICIENT_STRUCTURE, RC_READY_DFT, RC_HIGH_INFO,
    compute_roi_score,
)

log = logging.getLogger(__name__)

QUEUE_DIR = "artifacts/validation"
QUEUE_FILE = "validation_queue.json"

# Dedup similarity threshold
DEDUP_SIM_THRESHOLD = 0.95

# Priority thresholds
HIGH_THRESHOLD = 0.50
MEDIUM_THRESHOLD = 0.25


class ValidationQueue:
    """Persistent validation queue with dedup and priority."""

    def __init__(self, output_dir: str = QUEUE_DIR):
        self.output_dir = output_dir
        self._candidates: List[ValidationCandidate] = []
        self._formula_set: set = set()  # for fast dedup

    @property
    def size(self) -> int:
        return len(self._candidates)

    def add(self, candidate: ValidationCandidate) -> dict:
        """Add a candidate to the queue with dedup check.

        Returns dict with status and reason.
        """
        now = datetime.now(timezone.utc).isoformat()
        if not candidate.validation_id:
            candidate.validation_id = hashlib.sha256(
                f"val|{candidate.formula}|{candidate.spacegroup or 0}|{now}".encode()
            ).hexdigest()[:12]
        if not candidate.created_at:
            candidate.created_at = now
        candidate.updated_at = now

        # Dedup check
        dedup_key = f"{candidate.formula}|{candidate.spacegroup or 0}"
        if dedup_key in self._formula_set:
            candidate.current_status = "rejected"
            candidate.status_reason_codes.append(RC_DUPLICATE)
            return {"status": "rejected", "reason": RC_DUPLICATE,
                    "validation_id": candidate.validation_id}

        # Priority scoring
        roi = compute_roi_score(
            novelty=candidate.novelty_score,
            exotic=candidate.exotic_score,
            eval_score=candidate.evaluation_score,
            structure_confidence=0.5 if candidate.evaluation_ref else 0.0,
            app_relevance=0.3,
        )
        candidate.validation_priority_score = roi

        if roi >= HIGH_THRESHOLD:
            candidate.validation_priority_band = PRIORITY_HIGH
            candidate.status_reason_codes.append(RC_HIGH_INFO)
        elif roi >= MEDIUM_THRESHOLD:
            candidate.validation_priority_band = PRIORITY_MEDIUM
        else:
            candidate.validation_priority_band = PRIORITY_LOW

        # Assign validation plan
        candidate.validation_plan = VALIDATION_STAGES[:3]  # stages 0-2 for now

        self._candidates.append(candidate)
        self._formula_set.add(dedup_key)

        return {"status": "queued", "validation_id": candidate.validation_id,
                "priority": candidate.validation_priority_band,
                "roi_score": round(roi, 4)}

    def build_from_generation(self, run_id: str, db: MaterialsDB) -> dict:
        """Build queue entries from a generation run."""
        gen_engine = GenerationEngine(db)
        gen_result = gen_engine.get_run(run_id)
        if not gen_result:
            return {"error": f"Generation run '{run_id}' not found"}

        candidates = gen_result.get("candidates", [])
        added = 0
        rejected = 0
        for cdata in candidates:
            vc = ValidationCandidate(
                source_type="generated_candidate",
                source_ref=run_id,
                formula=cdata.get("formula", ""),
                spacegroup=cdata.get("spacegroup"),
                elements=cdata.get("elements", []),
                candidate_id=cdata.get("candidate_id"),
                novelty_score=cdata.get("scores", {}).get("novelty", 0.0),
                exotic_score=cdata.get("scores", {}).get("exotic", 0.0),
                evaluation_score=cdata.get("scores", {}).get("generation", 0.0),
            )
            result = self.add(vc)
            if result["status"] == "queued":
                added += 1
            else:
                rejected += 1

        return {"added": added, "rejected": rejected,
                "total_in_queue": self.size}

    def build_from_evaluation(self, eval_id: str, db: MaterialsDB) -> dict:
        """Build queue entries from an evaluation run."""
        evaluator = CandidateEvaluator(db)
        eval_result = evaluator.get_evaluation(eval_id)
        if not eval_result:
            return {"error": f"Evaluation '{eval_id}' not found"}

        candidates = eval_result.get("all_evaluated", [])
        added = 0
        rejected = 0
        for ec in candidates:
            if ec.get("evaluation_status", "").startswith("rejected"):
                rejected += 1
                continue
            vc = ValidationCandidate(
                source_type="evaluation_candidate",
                source_ref=eval_id,
                formula=ec.get("formula", ""),
                spacegroup=ec.get("spacegroup"),
                elements=ec.get("elements", []),
                candidate_id=ec.get("candidate_id"),
                evaluation_ref=eval_id,
                novelty_score=ec.get("scores", {}).get("novelty", 0.0),
                exotic_score=ec.get("scores", {}).get("exotic", 0.0),
                evaluation_score=ec.get("scores", {}).get("evaluation", 0.0),
            )
            result = self.add(vc)
            if result["status"] == "queued":
                added += 1
            else:
                rejected += 1

        return {"added": added, "rejected": rejected,
                "total_in_queue": self.size}

    def get(self, validation_id: str) -> Optional[ValidationCandidate]:
        for c in self._candidates:
            if c.validation_id == validation_id:
                return c
        return None

    def status(self) -> dict:
        """Return queue status summary."""
        statuses = Counter(c.current_status for c in self._candidates)
        priorities = Counter(c.validation_priority_band for c in self._candidates)
        return {
            "total": self.size,
            "by_status": dict(statuses),
            "by_priority": dict(priorities),
            "validation_stages": [s["name"] for s in VALIDATION_STAGES],
        }

    def get_top(self, n: int = 20) -> List[dict]:
        """Get top N candidates by ROI score."""
        queued = [c for c in self._candidates if c.current_status == "queued"]
        queued.sort(key=lambda c: -c.validation_priority_score)
        return [c.to_dict() for c in queued[:n]]

    def save(self) -> str:
        """Save queue to disk."""
        os.makedirs(self.output_dir, exist_ok=True)
        path = os.path.join(self.output_dir, QUEUE_FILE)
        data = {
            "total": self.size,
            "candidates": [c.to_dict() for c in self._candidates],
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path

    def load(self) -> bool:
        """Load queue from disk."""
        path = os.path.join(self.output_dir, QUEUE_FILE)
        if not os.path.exists(path):
            return False
        with open(path) as f:
            data = json.load(f)
        self._candidates = [ValidationCandidate.from_dict(d)
                            for d in data.get("candidates", [])]
        self._formula_set = {f"{c.formula}|{c.spacegroup or 0}"
                             for c in self._candidates}
        return True
