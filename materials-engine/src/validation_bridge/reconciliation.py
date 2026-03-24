"""Reconciliation — compare model predictions vs validation observations.

For each candidate with both a prediction and a validation result, compute:
- prediction error (FE, BG)
- confidence assessment
- classification (model_supports, partial_match, overconfident, etc.)
"""
import math


def reconcile(handoff_pack, validation_result):
    """Compare prediction vs observation for a validated candidate.

    Args:
        handoff_pack: dict from generate_handoff_pack()
        validation_result: dict from ValidationResult.to_dict()

    Returns:
        dict with reconciliation details
    """
    pred_fe = handoff_pack.get("formation_energy_predicted")
    obs_fe = validation_result.get("observed_fe")
    pred_bg = handoff_pack.get("band_gap_predicted")
    obs_bg = validation_result.get("observed_bg")
    uncertainty = handoff_pack.get("uncertainty_score", 1.0)
    confidence = handoff_pack.get("confidence_score", 0.0)

    rec = {
        "candidate_id": validation_result.get("candidate_id"),
        "predicted_fe": pred_fe,
        "observed_fe": obs_fe,
        "fe_error": None,
        "fe_abs_error": None,
        "predicted_bg": pred_bg,
        "observed_bg": obs_bg,
        "bg_error": None,
        "bg_abs_error": None,
        "prediction_uncertainty": uncertainty,
        "prediction_confidence": confidence,
        "fe_overestimate": None,
        "fe_underestimate": None,
        "bg_overestimate": None,
        "bg_underestimate": None,
        "confidence_justified": None,
        "classification": "no_comparison_data",
        "family_needs_recalibration": False,
        "notes": [],
    }

    has_fe_comparison = pred_fe is not None and obs_fe is not None
    has_bg_comparison = pred_bg is not None and obs_bg is not None

    if has_fe_comparison:
        rec["fe_error"] = round(pred_fe - obs_fe, 4)
        rec["fe_abs_error"] = round(abs(pred_fe - obs_fe), 4)
        rec["fe_overestimate"] = pred_fe > obs_fe
        rec["fe_underestimate"] = pred_fe < obs_fe

    if has_bg_comparison:
        rec["bg_error"] = round(pred_bg - obs_bg, 4)
        rec["bg_abs_error"] = round(abs(pred_bg - obs_bg), 4)
        rec["bg_overestimate"] = pred_bg > obs_bg
        rec["bg_underestimate"] = pred_bg < obs_bg

    # Classification
    if not has_fe_comparison and not has_bg_comparison:
        rec["classification"] = "no_comparison_data"
        rec["notes"].append("No overlapping predicted+observed values for comparison")
        return rec

    # Thresholds (eV)
    FE_GOOD = 0.15   # within model MAE
    FE_FAIR = 0.40   # within 2.5× model MAE
    BG_GOOD = 0.35   # within model MAE
    BG_FAIR = 0.80   # within 2.5× model MAE

    fe_quality = "none"
    if has_fe_comparison:
        ae = rec["fe_abs_error"]
        if ae <= FE_GOOD:
            fe_quality = "good"
        elif ae <= FE_FAIR:
            fe_quality = "fair"
        else:
            fe_quality = "poor"

    bg_quality = "none"
    if has_bg_comparison:
        ae = rec["bg_abs_error"]
        if ae <= BG_GOOD:
            bg_quality = "good"
        elif ae <= BG_FAIR:
            bg_quality = "fair"
        else:
            bg_quality = "poor"

    # Overall classification
    qualities = [q for q in (fe_quality, bg_quality) if q != "none"]
    if not qualities:
        rec["classification"] = "no_comparison_data"
    elif all(q == "good" for q in qualities):
        rec["classification"] = "model_supports_candidate"
    elif all(q in ("good", "fair") for q in qualities):
        rec["classification"] = "model_partial_match"
    elif any(q == "poor" for q in qualities) and confidence >= 0.60:
        rec["classification"] = "model_overconfident"
        rec["family_needs_recalibration"] = True
        rec["notes"].append("High confidence but large prediction error — recalibration needed")
    elif any(q == "poor" for q in qualities) and confidence < 0.40:
        rec["classification"] = "model_underconfident"
        rec["notes"].append("Low confidence and large error — as expected by model uncertainty")
    else:
        rec["classification"] = "model_partial_match"

    # Confidence justified?
    if any(q == "good" for q in qualities) and confidence >= 0.50:
        rec["confidence_justified"] = True
    elif all(q == "poor" for q in qualities) and confidence >= 0.60:
        rec["confidence_justified"] = False
        rec["notes"].append("Confidence was not justified by validation outcome")
    elif any(q == "poor" for q in qualities) and confidence < 0.40:
        rec["confidence_justified"] = True  # low confidence, poor result — honest
        rec["notes"].append("Model correctly signaled low confidence")

    return rec


def classify_for_learning(reconciliation):
    """Determine what the engine should learn from this reconciliation.

    Returns dict with learning signals.
    """
    cls = reconciliation.get("classification", "no_comparison_data")
    fe_ae = reconciliation.get("fe_abs_error")
    bg_ae = reconciliation.get("bg_abs_error")

    signals = {
        "retraining_relevance": "none",
        "corpus_expansion_relevance": "none",
        "family_recalibration_needed": reconciliation.get("family_needs_recalibration", False),
        "uncertainty_adjustment": 0.0,  # positive = increase uncertainty, negative = decrease
        "strategy_trust_delta": 0.0,
    }

    if cls == "model_supports_candidate":
        signals["uncertainty_adjustment"] = -0.05  # model was right, reduce uncertainty
        signals["strategy_trust_delta"] = +0.02
        signals["retraining_relevance"] = "low"

    elif cls == "model_overconfident":
        signals["uncertainty_adjustment"] = +0.15  # model was wrong AND confident
        signals["strategy_trust_delta"] = -0.05
        signals["retraining_relevance"] = "high"
        signals["corpus_expansion_relevance"] = "high"

    elif cls == "model_underconfident":
        signals["retraining_relevance"] = "medium"
        signals["corpus_expansion_relevance"] = "medium"

    elif cls == "model_partial_match":
        signals["uncertainty_adjustment"] = +0.03
        signals["retraining_relevance"] = "medium"

    return signals
