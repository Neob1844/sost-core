"""Evaluator — property prediction on lifted candidate structures.

Phase III.E: Takes generated candidates, lifts structures from parents,
runs real GNN prediction, and produces ranked evaluations.

Pipeline:
  Generated candidates → Structure lift → Property prediction → Ranking → Output
"""

import json
import hashlib
import logging
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple

from ..schema import Material
from ..storage.db import MaterialsDB
from ..inference.predictor import predict_from_structure
from .structure_lift import lift_candidate_structure, LiftResult, LIFT_OK
from .engine import GenerationEngine

log = logging.getLogger(__name__)

EVALUATION_DIR = "artifacts/generation"

# Evaluation decision states
EVAL_ACCEPTED_VALIDATION = "accepted_for_validation"
EVAL_ACCEPTED_WATCHLIST = "accepted_for_watchlist"
EVAL_WATCHLIST_ONLY = "watchlist_only"
EVAL_REJECTED_LOW_CONFIDENCE = "rejected_low_confidence"
EVAL_REJECTED_NOT_LIFTABLE = "rejected_not_liftable"
EVAL_REJECTED_UNSTABLE = "rejected_predicted_unstable"

# Default ranking weights
DEFAULT_WEIGHTS = {
    "novelty": 0.20,
    "exotic": 0.15,
    "plausibility": 0.15,
    "predicted_fe": 0.25,
    "target_fit": 0.15,
    "lift_confidence": 0.10,
}

# Decision thresholds
VALIDATION_THRESHOLD = 0.45
WATCHLIST_THRESHOLD = 0.25


@dataclass
class EvaluatedCandidate:
    """A generated candidate that has been lifted and evaluated."""
    candidate_id: str = ""
    parent_ids: List[str] = field(default_factory=list)
    generation_strategy: str = ""
    formula: str = ""
    elements: List[str] = field(default_factory=list)
    n_elements: int = 0
    spacegroup: Optional[int] = None

    # Lift
    lift_status: str = "not_attempted"
    lift_confidence: float = 0.0
    structure_sha256: Optional[str] = None
    n_atoms: int = 0

    # Predictions
    predicted_formation_energy: Optional[float] = None
    predicted_band_gap: Optional[float] = None
    prediction_model: Optional[str] = None
    prediction_reliability: str = "not_available"

    # Scores
    novelty_score: float = 0.0
    exotic_score: float = 0.0
    plausibility_score: float = 0.0
    evaluation_score: float = 0.0

    # Decision
    evaluation_status: str = "not_evaluated"
    reason_codes: List[str] = field(default_factory=list)
    created_at: str = ""

    def to_dict(self) -> dict:
        d = {
            "candidate_id": self.candidate_id,
            "parent_ids": self.parent_ids,
            "generation_strategy": self.generation_strategy,
            "formula": self.formula,
            "elements": self.elements,
            "n_elements": self.n_elements,
            "spacegroup": self.spacegroup,
            "lift": {
                "status": self.lift_status,
                "confidence": round(self.lift_confidence, 3),
                "structure_sha256": self.structure_sha256,
                "n_atoms": self.n_atoms,
            },
            "predictions": {
                "formation_energy": self.predicted_formation_energy,
                "band_gap": self.predicted_band_gap,
                "model": self.prediction_model,
                "reliability": self.prediction_reliability,
            },
            "scores": {
                "novelty": round(self.novelty_score, 4),
                "exotic": round(self.exotic_score, 4),
                "plausibility": round(self.plausibility_score, 4),
                "evaluation": round(self.evaluation_score, 4),
            },
            "evaluation_status": self.evaluation_status,
            "reason_codes": self.reason_codes,
            "created_at": self.created_at,
        }
        return d


class CandidateEvaluator:
    """Evaluates generated candidates by lifting structures and predicting properties."""

    def __init__(self, db: MaterialsDB, output_dir: str = EVALUATION_DIR):
        self.db = db
        self.output_dir = output_dir

    def evaluate_run(self, run_id: str,
                     weights: Optional[Dict[str, float]] = None,
                     band_gap_target: Optional[float] = None,
                     band_gap_tolerance: float = 2.0,
                     fe_max_for_stable: float = 0.5,
                     ) -> dict:
        """Evaluate candidates from a generation run.

        Args:
            run_id: ID of the generation run to evaluate
            weights: custom ranking weights (default: DEFAULT_WEIGHTS)
            band_gap_target: target band gap for property-fit scoring
            band_gap_tolerance: tolerance around band_gap_target
            fe_max_for_stable: max formation energy to consider stable
        """
        w = dict(DEFAULT_WEIGHTS)
        if weights:
            w.update(weights)

        gen_engine = GenerationEngine(self.db, output_dir=self.output_dir)
        gen_result = gen_engine.get_run(run_id)
        if gen_result is None:
            return {"error": f"Generation run '{run_id}' not found"}

        now = datetime.now(timezone.utc).isoformat()
        eval_id = hashlib.sha256(
            f"eval|{run_id}|{now}".encode()).hexdigest()[:12]

        candidates_data = gen_result.get("candidates", [])
        if not candidates_data:
            candidates_data = gen_result.get("top_candidates", [])

        evaluated: List[EvaluatedCandidate] = []
        lift_stats = Counter()

        for cdata in candidates_data:
            ec = self._evaluate_one(cdata, w, band_gap_target,
                                    band_gap_tolerance, fe_max_for_stable, now)
            evaluated.append(ec)
            lift_stats[ec.lift_status] += 1

        # Sort by evaluation_score
        evaluated.sort(key=lambda e: -e.evaluation_score)

        # Assign decisions
        for ec in evaluated:
            if ec.lift_status != LIFT_OK:
                ec.evaluation_status = EVAL_REJECTED_NOT_LIFTABLE
                ec.reason_codes.append("structure_not_liftable")
                continue
            if (ec.predicted_formation_energy is not None
                    and ec.predicted_formation_energy > fe_max_for_stable):
                ec.evaluation_status = EVAL_REJECTED_UNSTABLE
                ec.reason_codes.append("predicted_unstable")
                continue
            if ec.evaluation_score >= VALIDATION_THRESHOLD:
                ec.evaluation_status = EVAL_ACCEPTED_VALIDATION
                ec.reason_codes.append("high_evaluation_score")
            elif ec.evaluation_score >= WATCHLIST_THRESHOLD:
                ec.evaluation_status = EVAL_ACCEPTED_WATCHLIST
                ec.reason_codes.append("moderate_evaluation_score")
            elif ec.lift_confidence > 0.3:
                ec.evaluation_status = EVAL_WATCHLIST_ONLY
                ec.reason_codes.append("low_score_but_liftable")
            else:
                ec.evaluation_status = EVAL_REJECTED_LOW_CONFIDENCE
                ec.reason_codes.append("low_confidence_and_score")

        decisions = Counter(ec.evaluation_status for ec in evaluated)
        top_for_validation = [ec.to_dict() for ec in evaluated
                              if ec.evaluation_status == EVAL_ACCEPTED_VALIDATION][:20]

        result = {
            "evaluation_id": eval_id,
            "generation_run_id": run_id,
            "created_at": now,
            "config": {
                "weights": w,
                "band_gap_target": band_gap_target,
                "band_gap_tolerance": band_gap_tolerance,
                "fe_max_for_stable": fe_max_for_stable,
            },
            "summary": {
                "total_candidates": len(evaluated),
                "lift_stats": dict(lift_stats),
                "decisions": dict(decisions),
                "top_for_validation_count": len(top_for_validation),
            },
            "top_for_validation": top_for_validation,
            "all_evaluated": [ec.to_dict() for ec in evaluated],
            "disclaimer": (
                "Predictions use baseline GNN models (MAE ~0.23-0.45). "
                "Structures are lifted from parent prototypes, NOT relaxed. "
                "This is NOT ab-initio validation — candidates are ranked "
                "hypotheses for further computational or experimental study."
            ),
        }

        return result

    def evaluate_run_and_save(self, run_id: str, **kwargs) -> Tuple[dict, Optional[str]]:
        result = self.evaluate_run(run_id, **kwargs)
        if "error" in result:
            return result, None
        path = self._save(result)
        return result, path

    def get_evaluation(self, eval_id: str) -> Optional[dict]:
        path = os.path.join(self.output_dir, f"evaluation_run_{eval_id}.json")
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)

    def list_evaluations(self) -> List[dict]:
        if not os.path.exists(self.output_dir):
            return []
        results = []
        for fname in sorted(os.listdir(self.output_dir)):
            if fname.startswith("evaluation_run_") and fname.endswith(".json"):
                path = os.path.join(self.output_dir, fname)
                try:
                    with open(path) as f:
                        d = json.load(f)
                    results.append({
                        "evaluation_id": d.get("evaluation_id"),
                        "generation_run_id": d.get("generation_run_id"),
                        "total_candidates": d.get("summary", {}).get("total_candidates"),
                        "top_for_validation": d.get("summary", {}).get("top_for_validation_count"),
                        "created_at": d.get("created_at"),
                    })
                except Exception:
                    continue
        return results

    def lift_check(self, candidate_formula: str, candidate_elements: List[str],
                   parent_id: str, generation_strategy: str,
                   spacegroup: Optional[int] = None) -> dict:
        """Check if a candidate can be lifted from a specific parent."""
        parent = self.db.get_material(parent_id)
        if not parent:
            return {"error": "Parent material not found", "lift_status": "missing_parent"}

        lift = lift_candidate_structure(
            parent_structure_data=parent.structure_data,
            parent_formula=parent.formula,
            candidate_formula=candidate_formula,
            candidate_elements=candidate_elements,
            generation_strategy=generation_strategy,
        )

        result = {"lift": lift.to_dict(), "parent_id": parent_id,
                  "parent_formula": parent.formula}
        if lift.status == LIFT_OK and lift.structure is not None:
            # Try prediction
            for target in ["formation_energy", "band_gap"]:
                pred = predict_from_structure(lift.structure, target)
                if "prediction" in pred:
                    result[f"predicted_{target}"] = pred["prediction"]
                    result[f"{target}_model"] = pred.get("model")

        return result

    # ================================================================
    # Internal
    # ================================================================

    def _evaluate_one(self, cdata: dict, weights: dict,
                      band_gap_target: Optional[float],
                      band_gap_tolerance: float,
                      fe_max: float,
                      now: str) -> EvaluatedCandidate:
        """Evaluate a single candidate."""
        ec = EvaluatedCandidate(
            candidate_id=cdata.get("candidate_id", ""),
            parent_ids=cdata.get("parent_ids", []),
            generation_strategy=cdata.get("generation_strategy", ""),
            formula=cdata.get("formula", ""),
            elements=cdata.get("elements", []),
            n_elements=cdata.get("n_elements", 0),
            spacegroup=cdata.get("spacegroup"),
            novelty_score=cdata.get("scores", {}).get("novelty", 0.0),
            exotic_score=cdata.get("scores", {}).get("exotic", 0.0),
            plausibility_score=cdata.get("scores", {}).get("plausibility", 0.0),
            created_at=now,
        )

        # Attempt lift from first parent
        parent = None
        for pid in ec.parent_ids:
            parent = self.db.get_material(pid)
            if parent and parent.structure_data:
                break

        if parent is None or not parent.structure_data:
            ec.lift_status = "missing_parent_structure"
            ec.prediction_reliability = "not_available"
            ec.evaluation_score = self._compute_score_no_lift(ec, weights)
            return ec

        lift = lift_candidate_structure(
            parent_structure_data=parent.structure_data,
            parent_formula=parent.formula,
            candidate_formula=ec.formula,
            candidate_elements=ec.elements,
            generation_strategy=ec.generation_strategy,
        )

        ec.lift_status = lift.status
        ec.lift_confidence = lift.confidence
        ec.structure_sha256 = lift.structure_sha256
        ec.n_atoms = lift.n_atoms

        if lift.status != LIFT_OK or lift.structure is None:
            ec.prediction_reliability = "not_available"
            ec.evaluation_score = self._compute_score_no_lift(ec, weights)
            return ec

        # Run predictions
        ec.prediction_reliability = "lifted_structure_proxy"

        fe_pred = predict_from_structure(lift.structure, "formation_energy")
        if "prediction" in fe_pred:
            ec.predicted_formation_energy = round(fe_pred["prediction"], 4)
            ec.prediction_model = fe_pred.get("model")

        bg_pred = predict_from_structure(lift.structure, "band_gap")
        if "prediction" in bg_pred:
            ec.predicted_band_gap = round(bg_pred["prediction"], 4)

        # Compute evaluation score
        ec.evaluation_score = self._compute_score(
            ec, weights, band_gap_target, band_gap_tolerance)

        return ec

    def _compute_score(self, ec: EvaluatedCandidate, w: dict,
                       bg_target: Optional[float],
                       bg_tolerance: float) -> float:
        """Compute weighted evaluation score."""
        # Predicted FE score: lower fe → higher score
        fe_score = 0.3  # default if no prediction
        if ec.predicted_formation_energy is not None:
            fe_score = max(0.0, min(1.0,
                                    (2.0 - ec.predicted_formation_energy) / 5.0))

        # Target fit: band gap distance to target
        fit_score = 0.5  # neutral if no target
        if bg_target is not None and ec.predicted_band_gap is not None:
            dist = abs(ec.predicted_band_gap - bg_target)
            fit_score = max(0.0, 1.0 - dist / bg_tolerance) if bg_tolerance > 0 else 0.0

        score = (w.get("novelty", 0.2) * ec.novelty_score
                 + w.get("exotic", 0.15) * ec.exotic_score
                 + w.get("plausibility", 0.15) * ec.plausibility_score
                 + w.get("predicted_fe", 0.25) * fe_score
                 + w.get("target_fit", 0.15) * fit_score
                 + w.get("lift_confidence", 0.1) * ec.lift_confidence)

        return max(0.0, min(1.0, score))

    def _compute_score_no_lift(self, ec: EvaluatedCandidate,
                               w: dict) -> float:
        """Score when lift failed — use only novelty/exotic/plausibility."""
        return (w.get("novelty", 0.2) * ec.novelty_score
                + w.get("exotic", 0.15) * ec.exotic_score
                + w.get("plausibility", 0.15) * ec.plausibility_score) * 0.5

    def _save(self, result: dict) -> str:
        os.makedirs(self.output_dir, exist_ok=True)
        eid = result["evaluation_id"]
        path = os.path.join(self.output_dir, f"evaluation_run_{eid}.json")
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        log.info("Saved evaluation: %s", path)
        return path
