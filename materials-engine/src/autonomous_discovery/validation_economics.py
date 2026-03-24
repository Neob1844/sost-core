"""Validation economics — cost-aware prioritization and evidence gain scoring.

Calculates the expected value of validating each candidate, considering:
- evidence gain (what we learn)
- redundancy (overlap with already-queued candidates)
- family calibration benefit
- cost proxy (complexity of validation)
"""
from .chem_filters import parse_formula


def compute_validation_value(candidate_scores, uncertainty, readiness,
                              candidate_context=None, queued_formulas=None):
    """Compute value-of-validation metrics for a candidate.

    Returns dict with:
      evidence_gain: 0-1 (how much new information this validation would provide)
      redundancy_penalty: 0-1 (overlap with already queued candidates)
      validation_cost_proxy: 0-1 (estimated relative cost of validating)
      validation_roi: 0-1 (return on investment score)
    """
    ctx = candidate_context or {}
    queued = queued_formulas or set()
    formula = ctx.get("formula", "")
    elements = set(parse_formula(formula).keys()) if formula else set()
    chem_risk = ctx.get("risk_level", "unknown")
    family = ctx.get("family")
    origin = ctx.get("prediction_origin", "unavailable")
    is_known = ctx.get("is_known_material", False)

    conf = uncertainty.get("confidence_score", 0.5) if isinstance(uncertainty, dict) else 0.5
    ood = uncertainty.get("out_of_domain_risk", 0.3) if isinstance(uncertainty, dict) else 0.3
    ready = readiness.get("validation_readiness_score", 0.5) if isinstance(readiness, dict) else 0.5
    composite = candidate_scores.get("composite_score", 0.5) if isinstance(candidate_scores, dict) else 0.5

    # --- Evidence gain ---
    # Higher for: novel candidates, uncertain regions, uncalibrated families
    evidence_gain = 0.3  # base
    if is_known:
        evidence_gain = 0.05  # known materials teach little
    elif origin == "direct_gnn_lifted":
        evidence_gain = 0.50  # direct GNN — validation would calibrate the model
    elif origin == "proxy_only":
        evidence_gain = 0.35  # proxy — validation would reduce uncertainty

    # Higher gain for uncertain candidates (we learn more from surprises)
    evidence_gain += ood * 0.15

    # Higher gain for unexplored families
    if chem_risk == "exploratory" or not family:
        evidence_gain += 0.10
    elif chem_risk == "familiar":
        evidence_gain -= 0.05  # familiar families teach less per validation

    evidence_gain = round(min(1.0, max(0.0, evidence_gain)), 4)

    # --- Redundancy penalty ---
    redundancy = 0.0
    if formula in queued:
        redundancy = 1.0  # exact duplicate
    else:
        # Check element overlap with queued
        for qf in queued:
            q_elems = set(parse_formula(qf).keys())
            if q_elems and elements:
                overlap = len(elements & q_elems) / max(len(elements | q_elems), 1)
                if overlap >= 0.8:
                    redundancy = max(redundancy, 0.60)  # very similar
                elif overlap >= 0.5:
                    redundancy = max(redundancy, 0.30)  # somewhat similar
    redundancy = round(min(1.0, redundancy), 4)

    # --- Validation cost proxy ---
    # Higher for: complex compositions, no structure, risky chemistry
    cost = 0.3  # base
    n_elem = len(elements)
    if n_elem >= 4:
        cost += 0.15
    elif n_elem >= 3:
        cost += 0.05
    if not ctx.get("has_structure_lift", False):
        cost += 0.20  # need structure prediction first
    if chem_risk == "risky":
        cost += 0.15  # harder to validate
    elif chem_risk == "unusual":
        cost += 0.08
    cost = round(min(1.0, cost), 4)

    # --- ROI = (evidence_gain × readiness × composite) / (cost × (1 + redundancy)) ---
    numerator = evidence_gain * ready * max(composite, 0.1)
    denominator = max(cost, 0.1) * (1.0 + redundancy)
    roi = round(min(1.0, numerator / denominator), 4)

    return {
        "evidence_gain": evidence_gain,
        "redundancy_penalty": redundancy,
        "validation_cost_proxy": cost,
        "validation_roi": roi,
    }


def select_validation_batch(candidates, max_batch=10):
    """Select a non-redundant batch from scored candidates.

    Candidates should have 'validation_value' dict attached.
    Returns selected candidates sorted by ROI, with redundancy control.
    """
    # Sort by ROI descending
    ranked = sorted(candidates, key=lambda c: c.get("validation_value", {}).get("validation_roi", 0), reverse=True)

    selected = []
    selected_formulas = set()
    selected_families = {}

    for c in ranked:
        if len(selected) >= max_batch:
            break

        formula = c.get("formula", "")
        family = c.get("chemistry", {}).get("family") or c.get("candidate_context", {}).get("family") or ""

        # Skip exact duplicates
        if formula in selected_formulas:
            continue

        # Family quota: max 3 from same family
        fam_count = selected_families.get(family, 0) if family else 0
        if family and fam_count >= 3:
            continue

        selected.append(c)
        selected_formulas.add(formula)
        if family:
            selected_families[family] = fam_count + 1

    return selected
