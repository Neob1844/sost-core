"""Phase VII: Uncertainty-aware scoring and validation readiness.

Computes explicit uncertainty, out-of-domain risk, structure reliability,
and validation readiness for each candidate. These are heuristic signals —
NOT physical uncertainty from ensemble models or DFT.
"""
import math

# Strategy success rates (empirical from V.C campaigns)
STRATEGY_RELIABILITY = {
    "element_substitution": 0.85,
    "cross_substitution": 0.70,
    "single_site_doping": 0.55,
    "mixed_parent": 0.40,
}

# Element count → compositional complexity penalty
COMPLEXITY_PENALTY = {1: 0.0, 2: 0.05, 3: 0.15, 4: 0.30, 5: 0.45}


def compute_uncertainty(candidate_context, scores, method="unknown",
                         n_elements=2, neighbors=None):
    """Compute heuristic uncertainty score for a candidate.

    Returns dict with:
      uncertainty_score: 0.0 (very certain) to 1.0 (very uncertain)
      confidence_score: 1.0 - uncertainty_score
      out_of_domain_risk: 0.0 to 1.0
      structure_reliability: 0.0 to 1.0
      family_support_confidence: 0.0 to 1.0
      support_strength: "strong" | "moderate" | "weak" | "none"
      prediction_support_summary: human-readable string
    """
    ctx = candidate_context or {}
    origin = ctx.get("prediction_origin", "unavailable")
    has_lift = ctx.get("has_structure_lift", False)
    has_gnn_fe = ctx.get("has_direct_gnn_fe", False)
    has_gnn_bg = ctx.get("has_direct_gnn_bg", False)
    is_known = ctx.get("is_known_material", False)
    gnn_conf = ctx.get("gnn_confidence", "none")
    plausibility = scores.get("plausibility", 0.5) if isinstance(scores, dict) else 0.5

    # --- Structure reliability ---
    if is_known:
        structure_reliability = 1.0
    elif has_lift and origin == "direct_gnn_lifted":
        structure_reliability = 0.65  # lifted, not relaxed
    elif has_lift:
        structure_reliability = 0.50  # lifted but no GNN confirmation
    else:
        structure_reliability = 0.10  # composition only

    # --- Family support confidence ---
    neighbor_count = len(neighbors) if neighbors else 0
    family_bonus = scores.get("family_bonus", 0) if isinstance(scores, dict) else 0
    family_support = min(1.0, 0.2 + neighbor_count * 0.15 + family_bonus * 2.0)

    # --- Out of domain risk ---
    # High risk: rare elements, many elements, no neighbors, no lift
    complexity = COMPLEXITY_PENALTY.get(min(n_elements, 5), 0.45)
    strategy_rel = STRATEGY_RELIABILITY.get(method, 0.30)

    ood_risk = 0.0
    ood_risk += complexity * 0.4  # compositional complexity
    ood_risk += (1.0 - strategy_rel) * 0.2  # strategy unreliability
    if not has_lift:
        ood_risk += 0.25  # no structure
    if neighbor_count == 0:
        ood_risk += 0.15  # no corpus neighbors
    ood_risk = min(1.0, max(0.0, ood_risk))

    # --- Uncertainty score ---
    # Base uncertainty from prediction origin
    if is_known:
        base_uncertainty = 0.05  # known material
    elif origin == "direct_gnn_lifted" and gnn_conf in ("medium", "high"):
        base_uncertainty = 0.25  # direct GNN with decent confidence
    elif origin == "direct_gnn_lifted":
        base_uncertainty = 0.35  # direct GNN but low confidence
    elif has_lift:
        base_uncertainty = 0.50  # lifted but no GNN
    elif origin == "proxy_only":
        base_uncertainty = 0.70  # proxy estimate only
    else:
        base_uncertainty = 0.85  # no evidence at all

    # Phase XI.C: Chemistry risk adjusts uncertainty and OOD
    chem_risk = ctx.get("risk_level", "unknown")
    if chem_risk == "risky":
        ood_risk = min(1.0, ood_risk + 0.15)
    elif chem_risk == "unusual":
        ood_risk = min(1.0, ood_risk + 0.08)
    elif chem_risk == "familiar":
        family_support = min(1.0, family_support + 0.10)

    # Adjust by other signals
    uncertainty = base_uncertainty
    uncertainty += ood_risk * 0.15  # OOD increases uncertainty
    uncertainty -= family_support * 0.10  # family support decreases it
    uncertainty += (1.0 - plausibility) * 0.10  # low plausibility increases it
    uncertainty = round(min(1.0, max(0.0, uncertainty)), 4)

    confidence = round(1.0 - uncertainty, 4)

    # --- Support strength label ---
    if confidence >= 0.80:
        support = "strong"
    elif confidence >= 0.55:
        support = "moderate"
    elif confidence >= 0.30:
        support = "weak"
    else:
        support = "none"

    # --- Summary ---
    parts = []
    if is_known:
        parts.append("known corpus material")
    elif origin == "direct_gnn_lifted":
        parts.append("direct GNN on lifted structure")
    elif has_lift:
        parts.append("structure lifted, no GNN prediction")
    elif origin == "proxy_only":
        parts.append("proxy estimate from neighbors")
    else:
        parts.append("composition-only, no structural evidence")

    if neighbor_count > 0:
        parts.append(f"{neighbor_count} corpus neighbor(s)")
    if family_bonus > 0:
        parts.append("known binary family")
    if ood_risk > 0.5:
        parts.append("high out-of-domain risk")
    if chem_risk == "risky":
        parts.append("risky chemistry — unusual composition")
    elif chem_risk == "unusual":
        parts.append("unusual chemistry — needs stronger evidence")

    summary = "; ".join(parts)

    return {
        "uncertainty_score": uncertainty,
        "confidence_score": confidence,
        "out_of_domain_risk": round(ood_risk, 4),
        "structure_reliability": round(structure_reliability, 4),
        "family_support_confidence": round(family_support, 4),
        "support_strength": support,
        "prediction_support_summary": summary,
    }


def compute_validation_readiness(uncertainty_result, scores, candidate_context=None):
    """Compute how ready this candidate is for deeper validation (DFT etc).

    Returns dict with:
      validation_readiness_score: 0.0 to 1.0
      dft_handoff_ready: bool
      next_action: string
      why_not_higher: string or None
      why_not_lower: string or None
      handoff_value_score: 0.0 to 1.0
    """
    ctx = candidate_context or {}
    conf = uncertainty_result["confidence_score"]
    ood = uncertainty_result["out_of_domain_risk"]
    struct_rel = uncertainty_result["structure_reliability"]
    support = uncertainty_result["support_strength"]
    is_known = ctx.get("is_known_material", False)
    is_novel_gnn = scores.get("is_novel_direct_gnn", False) if isinstance(scores, dict) else False
    composite = scores.get("composite_score", 0) if isinstance(scores, dict) else 0
    plausibility = scores.get("plausibility", 0) if isinstance(scores, dict) else 0

    # Validation readiness = weighted combination
    readiness = 0.0
    readiness += conf * 0.30  # confidence matters most
    readiness += struct_rel * 0.25  # structure quality
    readiness += plausibility * 0.20  # chemical plausibility
    readiness += min(1.0, composite * 1.2) * 0.15  # composite score (boosted)
    readiness -= ood * 0.10  # OOD risk reduces readiness

    # Phase XI.C: chemistry risk adjusts readiness
    chem_risk = ctx.get("risk_level", "unknown")
    if chem_risk == "familiar":
        readiness += 0.04
    elif chem_risk == "risky":
        readiness -= 0.08
    elif chem_risk == "unusual":
        readiness -= 0.04

    readiness = round(min(1.0, max(0.0, readiness)), 4)

    # DFT handoff threshold
    dft_ready = (readiness >= 0.60 and not is_known and conf >= 0.50
                 and struct_rel >= 0.50 and plausibility >= 0.50)

    # Handoff value: how valuable would validating this candidate be?
    handoff_value = 0.0
    if not is_known:
        handoff_value += 0.30  # novel is more valuable to validate
    if is_novel_gnn:
        handoff_value += 0.25  # direct GNN evidence adds value
    handoff_value += plausibility * 0.20
    handoff_value += composite * 0.15
    handoff_value -= ood * 0.10
    handoff_value = round(min(1.0, max(0.0, handoff_value)), 4)

    # Next action
    if is_known:
        action = "reference_only"
        why_higher = "known material — no discovery value"
        why_lower = None
    elif dft_ready:
        action = "DFT_handoff_candidate"
        why_higher = None
        why_lower = f"readiness={readiness:.2f}, confidence={conf:.2f}"
    elif readiness >= 0.45:
        action = "prepare_validation_pack"
        why_higher = f"needs better structure (reliability={struct_rel:.2f})" if struct_rel < 0.50 else f"needs higher confidence ({conf:.2f})"
        why_lower = f"readiness={readiness:.2f}, plausibility={plausibility:.2f}"
    elif readiness >= 0.30:
        action = "wait_for_better_support"
        why_higher = f"low confidence ({conf:.2f}) or high OOD risk ({ood:.2f})"
        why_lower = "some structural or compositional support exists"
    elif conf < 0.20:
        action = "deprioritize"
        why_higher = "very low confidence, minimal evidence"
        why_lower = None
    else:
        action = "keep_watchlist"
        why_higher = "insufficient evidence for validation"
        why_lower = "not completely implausible"

    return {
        "validation_readiness_score": readiness,
        "dft_handoff_ready": dft_ready,
        "next_action": action,
        "why_not_higher": why_higher,
        "why_not_lower": why_lower,
        "handoff_value_score": handoff_value,
    }


def generate_handoff_pack(candidate, uncertainty_result, readiness_result):
    """Generate a DFT handoff pack for a candidate.

    Returns dict suitable for JSON export.
    """
    formula = candidate.get("formula", "unknown")
    scores = candidate.get("scores", {})
    ml = candidate.get("ml_evaluation", {})
    lift = candidate.get("structure_lift", {})
    gnn = candidate.get("gnn_combined", {})

    pack = {
        "handoff_version": "VII.1",
        "candidate_formula": formula,
        "parent_a": candidate.get("parent_a", ""),
        "parent_b": candidate.get("parent_b", ""),
        "generation_method": candidate.get("method", "unknown"),
        "composite_score": scores.get("composite_score", 0) if isinstance(scores, dict) else 0,
        "plausibility": scores.get("plausibility", 0) if isinstance(scores, dict) else 0,
        "prediction_origin": scores.get("prediction_origin", "unavailable") if isinstance(scores, dict) else "unavailable",

        # Predictions
        "formation_energy_predicted": gnn.get("direct_fe_value") if isinstance(gnn, dict) else None,
        "band_gap_predicted": gnn.get("direct_bg_value") if isinstance(gnn, dict) else None,
        "fe_confidence": gnn.get("direct_fe_confidence", "none") if isinstance(gnn, dict) else "none",
        "bg_confidence": gnn.get("direct_bg_confidence", "none") if isinstance(gnn, dict) else "none",

        # Structure
        "structure_lift_status": lift.get("structure_lift_status", "unknown") if isinstance(lift, dict) else "unknown",
        "lifted_from_parent": lift.get("lifted_from_parent") if isinstance(lift, dict) else None,
        "lifted_spacegroup": lift.get("lifted_spacegroup") if isinstance(lift, dict) else None,
        "structure_reliability": uncertainty_result.get("structure_reliability", 0),

        # Uncertainty
        "uncertainty_score": uncertainty_result.get("uncertainty_score", 1.0),
        "confidence_score": uncertainty_result.get("confidence_score", 0.0),
        "out_of_domain_risk": uncertainty_result.get("out_of_domain_risk", 1.0),
        "support_strength": uncertainty_result.get("support_strength", "none"),
        "prediction_support_summary": uncertainty_result.get("prediction_support_summary", ""),

        # Readiness
        "validation_readiness_score": readiness_result.get("validation_readiness_score", 0),
        "dft_handoff_ready": readiness_result.get("dft_handoff_ready", False),
        "next_action": readiness_result.get("next_action", "unknown"),
        "handoff_value_score": readiness_result.get("handoff_value_score", 0),

        # Nearest neighbors
        "nearest_neighbors": [
            {"formula": n.get("formula", ""), "formation_energy": n.get("formation_energy")}
            for n in (ml.get("nearest_neighbors") or [])[:3]
        ] if isinstance(ml, dict) else [],

        # Risk flags
        "risk_flags": _compute_risk_flags(uncertainty_result, readiness_result, scores),

        # Phase XIII: Relaxation readiness and repair info
        "structure_sanity_score": (candidate.get("physics_screening") or {}).get("structure_sanity_score"),
        "geometry_warnings": (candidate.get("physics_screening") or {}).get("geometry_warnings", []),
        "relaxation_readiness": candidate.get("relaxation_readiness", {}),
        "structure_repair": candidate.get("structure_repair", {}),
        "stronger_compute_rationale": _build_stronger_compute_rationale(candidate),

        # Rationale
        "validation_rationale": _build_rationale(candidate, uncertainty_result, readiness_result),

        # Disclaimer
        "disclaimer": (
            "This candidate is THEORETICAL. No DFT, phonon, or experimental validation "
            "has been performed. Structure is approximate (not relaxed). GNN predictions "
            "carry model-level uncertainty. Novelty is relative to the 76,193-material corpus."
        ),
    }
    return pack


def _compute_risk_flags(uncertainty, readiness, scores):
    flags = []
    if uncertainty.get("out_of_domain_risk", 0) > 0.5:
        flags.append("HIGH_OOD_RISK")
    if uncertainty.get("structure_reliability", 0) < 0.30:
        flags.append("LOW_STRUCTURE_RELIABILITY")
    if uncertainty.get("uncertainty_score", 1) > 0.70:
        flags.append("HIGH_UNCERTAINTY")
    if uncertainty.get("family_support_confidence", 0) < 0.30:
        flags.append("LOW_FAMILY_SUPPORT")
    sc = scores if isinstance(scores, dict) else {}
    if sc.get("plausibility", 0) < 0.40:
        flags.append("LOW_PLAUSIBILITY")
    if sc.get("proxy_only_penalty", 0) > 0:
        flags.append("PROXY_ONLY")
    return flags


def _build_rationale(candidate, uncertainty, readiness):
    parts = []
    formula = candidate.get("formula", "?")
    method = candidate.get("method", "unknown")
    origin = (candidate.get("scores", {}) or {}).get("prediction_origin", "unavailable")

    parts.append(f"{formula} generated via {method}")

    if origin == "direct_gnn_lifted":
        parts.append("with direct CGCNN prediction on lifted structure")
    elif origin == "known_exact":
        parts.append("(known corpus material — reference only)")
    else:
        parts.append("without direct model prediction")

    conf = uncertainty.get("confidence_score", 0)
    parts.append(f"confidence={conf:.2f}")

    ready = readiness.get("validation_readiness_score", 0)
    parts.append(f"validation_readiness={ready:.2f}")

    action = readiness.get("next_action", "unknown")
    parts.append(f"recommended: {action}")

    return ". ".join(parts) + "."


def apply_diversity_constraint(candidates, max_per_family=3, top_k=10):
    """Select top-k candidates with diversity constraint.

    Limits candidates from the same element family to max_per_family.
    """
    selected = []
    family_counts = {}

    for c in candidates:
        if len(selected) >= top_k:
            break

        elements = sorted(c.get("elements", []))
        family_key = "-".join(elements)

        count = family_counts.get(family_key, 0)
        if count >= max_per_family:
            continue

        family_counts[family_key] = count + 1
        selected.append(c)

    return selected


def _build_stronger_compute_rationale(candidate):
    """Build rationale for why this candidate deserves (or doesn't) stronger compute."""
    relax = candidate.get("relaxation_readiness", {})
    repair = candidate.get("structure_repair", {})
    phys = candidate.get("physics_screening", {})

    tier = relax.get("relaxation_readiness_tier", "unknown")
    sanity = phys.get("structure_sanity_score", 0)
    repair_sev = repair.get("repair_severity", "unknown")

    if tier == "relaxation_ready":
        return f"RECOMMENDED for stronger compute. Structure sanity={sanity:.2f}, no repair needed."
    elif tier == "structure_repair_candidate":
        return f"Needs repair first (severity={repair_sev}). After repair, may qualify for compute."
    elif tier == "stronger_compute_with_caveats":
        return f"Possible stronger compute candidate with caveats (sanity={sanity:.2f})."
    elif tier == "not_ready_discard_or_rebuild":
        return f"NOT recommended. Structure too damaged (sanity={sanity:.2f})."
    else:
        return "Relaxation readiness not assessed."
