"""Evidence-Feedback auto-linker — connects evidence to prediction feedback.

Phase III.H Delta: When external evidence arrives with an observed_value,
automatically creates a FeedbackEntry if a matching prediction exists.

Match criteria (strict):
  - Same formula
  - Same property_name
  - Prediction exists in corpus (known property from DB)

If match is not reliable, marks as unlinked — never invents a connection.
"""

import logging
from typing import Optional, List

from ..storage.db import MaterialsDB
from ..evidence.spec import EvidenceRecord, EvidenceRegistry
from ..learning.feedback import FeedbackEntry, FeedbackMemory

log = logging.getLogger(__name__)

# Error thresholds for auto-decision
SMALL_ERROR = 0.3     # → keep
MEDIUM_ERROR = 1.0    # → downgrade_confidence
LARGE_ERROR = 2.0     # → needs_retrain


def link_evidence_to_feedback(evidence: EvidenceRecord,
                              db: MaterialsDB,
                              feedback: FeedbackMemory) -> dict:
    """Try to link an evidence record to a prediction and create feedback.

    Returns dict with link status and feedback_id if created.
    """
    if evidence.observed_value is None:
        return {"linked": False, "reason": "no_observed_value"}

    if not evidence.formula or not evidence.property_name:
        return {"linked": False, "reason": "missing_formula_or_property"}

    # Find matching material in corpus
    materials = db.search_materials(formula=evidence.formula, limit=5)
    match = None
    for m in materials:
        if m.formula == evidence.formula:
            match = m
            break

    if match is None:
        return {"linked": False, "reason": "no_corpus_match"}

    # Get the predicted/known value for this property
    predicted_value = getattr(match, evidence.property_name, None)
    if predicted_value is None:
        return {"linked": False, "reason": "no_predicted_value_for_property"}

    # Compute error and decide
    error = abs(predicted_value - evidence.observed_value)
    if error < SMALL_ERROR:
        decision = "keep"
    elif error < MEDIUM_ERROR:
        decision = "downgrade_confidence"
    elif error < LARGE_ERROR:
        decision = "needs_retrain"
    else:
        decision = "needs_retrain"

    # Create feedback entry
    entry = FeedbackEntry(
        formula=evidence.formula,
        elements=match.elements,
        spacegroup=match.spacegroup,
        target_property=evidence.property_name,
        predicted_value=predicted_value,
        observed_value=evidence.observed_value,
        error=round(error, 4),
        observed_result_type=evidence.source_type,
        confidence_before="known" if predicted_value is not None else "predicted",
        evidence_after=evidence.evidence_level,
        decision=decision,
        reviewer=evidence.reviewer or "auto_linker",
        source_note=f"Auto-linked from evidence {evidence.evidence_id}",
        validation_id=evidence.linked_validation_id,
        candidate_id=evidence.linked_candidate_id,
    )

    feedback_id = feedback.add(entry)

    return {
        "linked": True,
        "feedback_id": feedback_id,
        "corpus_value": predicted_value,
        "observed_value": evidence.observed_value,
        "error": round(error, 4),
        "decision": decision,
    }


def batch_link(registry: EvidenceRegistry,
               db: MaterialsDB,
               feedback: FeedbackMemory) -> dict:
    """Link all unlinked evidence records to feedback."""
    linked = 0
    unlinked = 0
    results = []

    for record in registry._records:
        if record.observed_value is None:
            continue
        result = link_evidence_to_feedback(record, db, feedback)
        results.append({
            "evidence_id": record.evidence_id,
            "formula": record.formula,
            **result,
        })
        if result["linked"]:
            linked += 1
        else:
            unlinked += 1

    return {
        "linked": linked,
        "unlinked": unlinked,
        "details": results,
    }
