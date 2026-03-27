"""Phase XIII: Relaxation readiness layer.

Determines whether a candidate structure is ready for stronger compute
(relaxation, M3GNet, CHGNet, DFT), needs structural repair first,
or should be deferred/discarded.

NOT a substitute for actual relaxation — a triage layer that decides
which structures deserve computational investment.
"""


def assess_relaxation_readiness(physics_result, uncertainty_result=None,
                                  readiness_result=None, candidate_context=None):
    """Classify a candidate's readiness for stronger compute.

    Args:
        physics_result: dict from physics_screening.screen_structure()
        uncertainty_result: dict from uncertainty.compute_uncertainty()
        readiness_result: dict from uncertainty.compute_validation_readiness()
        candidate_context: dict with prediction_origin, risk_level, etc.

    Returns dict with:
        relaxation_ready: bool
        structure_repair_needed: bool
        geometry_repair_priority: "none" | "low" | "medium" | "high"
        likely_relaxation_stable: bool
        likely_relaxation_fail: bool
        stronger_compute_candidate: bool
        relaxation_readiness_tier: str
        relaxation_rationale: str
    """
    sanity = physics_result.get("structure_sanity_score", 0)
    pre_dft = physics_result.get("pre_dft_ready", False)
    warnings = physics_result.get("geometry_warnings", [])
    flags = physics_result.get("physics_flags", [])
    min_bond = physics_result.get("min_bond_distance")
    vol_per_atom = physics_result.get("volume_per_atom")
    density_ok = physics_result.get("density_sanity", False)
    bond_ok = physics_result.get("bond_distance_sanity", False)

    ctx = candidate_context or {}
    origin = ctx.get("prediction_origin", "unavailable")
    chem_risk = ctx.get("risk_level", "unknown")
    has_lift = ctx.get("has_structure_lift", False)

    unc = uncertainty_result or {}
    struct_rel = unc.get("structure_reliability", 0)
    confidence = unc.get("confidence_score", 0.5)

    ready = readiness_result or {}
    readiness_score = ready.get("validation_readiness_score", 0)

    # --- Classify geometry repair priority ---
    critical_warnings = [w for w in warnings if any(k in w for k in
        ["TOO_CLOSE", "EXTREME_DENSITY", "SINGLE_ATOM", "VERY_SMALL_VOLUME"])]
    moderate_warnings = [w for w in warnings if any(k in w for k in
        ["SHORT_BONDS", "UNUSUAL_DENSITY", "SPARSE_STRUCTURE", "VERY_LARGE_VOLUME"])]
    minor_warnings = [w for w in warnings if w not in critical_warnings + moderate_warnings
                      and w != "NO_STRUCTURE_AVAILABLE"]

    if critical_warnings:
        repair_priority = "high"
    elif moderate_warnings:
        repair_priority = "medium"
    elif minor_warnings:
        repair_priority = "low"
    else:
        repair_priority = "none"

    # --- Determine repair needed ---
    repair_needed = repair_priority in ("high", "medium")

    # --- Likely relaxation stability ---
    # A structure is likely stable if: good sanity, no critical warnings,
    # reasonable density and bonds, and comes from a reliable strategy
    likely_stable = (
        sanity >= 0.55 and
        not critical_warnings and
        bond_ok and
        density_ok and
        has_lift
    )

    # --- Likely relaxation failure ---
    # Very bad geometry, no structure, or composition-only
    likely_fail = (
        sanity < 0.30 or
        not has_lift or
        bool(critical_warnings) and sanity < 0.40 or
        "NO_STRUCTURE_AVAILABLE" in warnings
    )

    # --- Relaxation ready ---
    # Ready = structure is good enough to submit to relaxation backend
    relaxation_ready = (
        pre_dft and
        likely_stable and
        not repair_needed and
        struct_rel >= 0.50 and
        confidence >= 0.40
    )

    # --- Stronger compute candidate ---
    # Broader than relaxation_ready: includes candidates that would benefit
    # from M3GNet/CHGNet/DFT even if not perfectly clean
    stronger_compute = (
        sanity >= 0.45 and
        has_lift and
        not likely_fail and
        readiness_score >= 0.40
    )

    # --- Tier classification ---
    if relaxation_ready:
        tier = "relaxation_ready"
    elif repair_needed and sanity >= 0.35:
        tier = "structure_repair_candidate"
    elif stronger_compute and not relaxation_ready:
        tier = "stronger_compute_with_caveats"
    elif likely_fail:
        tier = "not_ready_discard_or_rebuild"
    else:
        tier = "watchlist_needs_improvement"

    # --- Rationale ---
    parts = []
    if relaxation_ready:
        parts.append(f"Structure passes sanity ({sanity:.2f}), bonds OK, density OK")
        parts.append("Ready for relaxation or stronger compute backend")
    elif repair_needed:
        parts.append(f"Structure needs repair (priority={repair_priority})")
        parts.append(f"Issues: {', '.join(critical_warnings + moderate_warnings)}")
    elif likely_fail:
        parts.append("Structure likely too damaged for useful relaxation")
        if not has_lift:
            parts.append("No structure lift available — composition only")
    else:
        parts.append(f"Marginal structure (sanity={sanity:.2f})")
        parts.append("Needs improvement before stronger compute")

    if chem_risk == "risky":
        parts.append("Chemistry risk: unusual composition may complicate relaxation")

    return {
        "relaxation_ready": relaxation_ready,
        "structure_repair_needed": repair_needed,
        "geometry_repair_priority": repair_priority,
        "likely_relaxation_stable": likely_stable,
        "likely_relaxation_fail": likely_fail,
        "stronger_compute_candidate": stronger_compute,
        "relaxation_readiness_tier": tier,
        "relaxation_rationale": ". ".join(parts) + ".",
    }
