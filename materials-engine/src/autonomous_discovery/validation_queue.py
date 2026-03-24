"""Validation queue — routes candidates to appropriate next steps.

Categories:
- reject: not worth further investigation
- watchlist: keep monitoring, re-evaluate later
- manual_review: needs human inspection
- validation_candidate: ready for stronger ML or prototype refinement
- priority_validation: high-value, structure-aware, ready for DFT handoff
"""

DECISIONS = {
    "reject": {"label": "Rejected", "color": "#ff4444", "action": "no_action"},
    "known_reference": {"label": "Known Reference", "color": "#888888", "action": "reference_baseline"},
    "watchlist": {"label": "Watchlist", "color": "#fbbf24", "action": "keep_monitoring"},
    "manual_review": {"label": "Manual Review", "color": "#67e8f9", "action": "human_inspection"},
    "validation_candidate": {"label": "Validation Candidate", "color": "#4ade80", "action": "stronger_ml_pass"},
    "priority_validation": {"label": "Priority Validation", "color": "#00ff41", "action": "dft_handoff_candidate"},
}


def route_candidate(scores, ml_eval=None, candidate_context=None):
    """Route a scored candidate to the appropriate validation tier.

    Args:
        scores: dict from scorer (composite_score, plausibility, etc.)
        ml_eval: dict from ml_evaluator (ml_confidence, etc.)
        candidate_context: Phase V.B dict with is_known_material, prediction_origin, etc.

    Returns:
        dict with decision, reason_codes, recommended_next_step, validation_priority
    """
    composite = scores.get("composite_score", 0)
    plausibility = scores.get("plausibility", 0)
    decision_from_scorer = scores.get("decision", "rejected")
    ml_confidence = (ml_eval or {}).get("ml_confidence", "none")
    ml_status = (ml_eval or {}).get("ml_inference_status", "unavailable")
    has_structure = ml_status in ("known_in_corpus", "proxy_from_neighbor")

    ctx = candidate_context or {}
    prediction_origin = ctx.get("prediction_origin", "unavailable")

    reasons = []
    next_step = "no_action"
    priority = 0  # 0=none, 0.5=known_reference, 1=low, 2=medium, 3=high, 4=critical

    # Phase V.B: Known material → known_reference tier regardless of score
    if ctx.get("is_known_material", False):
        decision = "known_reference"
        reasons.append("known_corpus_material")
        next_step = "reference_baseline"
        priority = 0.5
        return {
            "validation_decision": decision,
            "validation_label": DECISIONS[decision]["label"],
            "reason_codes": reasons,
            "recommended_next_step": next_step,
            "validation_priority": priority,
            "confidence_tier": ml_confidence,
            "structure_status": "available" if has_structure else "composition_only",
        }

    # Phase V.B: proxy_only origin caps at validation_candidate (never priority_validation)
    proxy_only_cap = prediction_origin == "proxy_only"

    # Phase V.B: direct_gnn_lifted with good score → boost toward priority_validation
    direct_gnn_boost = prediction_origin == "direct_gnn_lifted" and composite >= 0.50

    # Priority validation: high score + structure + ML context (or direct GNN boost)
    if not proxy_only_cap and (
        (composite >= 0.55 and has_structure and ml_confidence in ("medium", "high")) or
        (direct_gnn_boost and composite >= 0.52)
    ):
        decision = "priority_validation"
        reasons.append("high_composite_with_structure")
        if direct_gnn_boost:
            reasons.append("direct_gnn_lifted_boost")
        next_step = "dft_handoff_candidate"
        priority = 4

    # Validation candidate: good score + some ML context
    elif composite >= 0.45 and plausibility >= 0.5:
        decision = "validation_candidate"
        reasons.append("good_score_and_plausibility")
        next_step = "stronger_ml_pass" if not has_structure else "prototype_refinement"
        priority = 3

    # Manual review: borderline cases
    elif composite >= 0.38 and plausibility >= 0.4:
        decision = "manual_review"
        reasons.append("borderline_needs_inspection")
        next_step = "compare_corpus_neighbors"
        priority = 2

    # Watchlist: marginal but not worthless
    elif decision_from_scorer == "watchlist" or (composite >= 0.30 and plausibility >= 0.3):
        decision = "watchlist"
        reasons.append("marginal_keep_monitoring")
        next_step = "keep_monitoring"
        priority = 1

    # Reject
    else:
        decision = "reject"
        if composite < 0.30:
            reasons.append("low_composite_score")
        if plausibility < 0.25:
            reasons.append("low_plausibility")
        next_step = "no_action"
        priority = 0

    return {
        "validation_decision": decision,
        "validation_label": DECISIONS[decision]["label"],
        "reason_codes": reasons,
        "recommended_next_step": next_step,
        "validation_priority": priority,
        "confidence_tier": ml_confidence,
        "structure_status": "available" if has_structure else "composition_only",
    }
