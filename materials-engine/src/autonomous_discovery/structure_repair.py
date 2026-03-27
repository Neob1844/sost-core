"""Phase XIII: Structure repair heuristics.

Lightweight pre-relaxation repair checks. Does NOT perform actual
structural relaxation — identifies what needs fixing and whether
the structure is repairable without full DFT.

Honest limitation: these are heuristic fixes, not physics-based
optimization. Real repair requires M3GNet/CHGNet/DFT relaxation.
"""


# Minimum plausible interatomic distances by pair type (Å)
_MIN_DISTANCES = {
    "default": 1.2,
    "metal-metal": 2.0,
    "metal-nonmetal": 1.5,
    "nonmetal-nonmetal": 1.0,
}

# Maximum plausible volume per atom ranges (Å³)
_VOLUME_LIMITS = {"min": 5.0, "max": 80.0, "ideal_min": 8.0, "ideal_max": 50.0}


def assess_structure_repair(physics_result, formula="", candidate_context=None):
    """Assess whether a structure can be repaired before stronger compute.

    Args:
        physics_result: dict from physics_screening.screen_structure()
        formula: chemical formula string
        candidate_context: dict with prediction_origin, risk_level, etc.

    Returns dict with:
        repairable_structure: bool
        repair_actions_recommended: list of str
        repair_severity: "none" | "minor" | "moderate" | "severe" | "non_repairable"
        repair_confidence: float (0-1, how confident we are repair would succeed)
        repair_summary: str
    """
    warnings = physics_result.get("geometry_warnings", [])
    sanity = physics_result.get("structure_sanity_score", 0)
    min_bond = physics_result.get("min_bond_distance")
    vol_per_atom = physics_result.get("volume_per_atom")
    density = physics_result.get("density")
    mean_nn = physics_result.get("mean_nn_distance")

    ctx = candidate_context or {}
    has_lift = ctx.get("has_structure_lift", False)

    actions = []
    severity_score = 0  # accumulates severity

    # --- No structure at all ---
    if "NO_STRUCTURE_AVAILABLE" in warnings or not has_lift:
        return {
            "repairable_structure": False,
            "repair_actions_recommended": ["NEEDS_FULL_STRUCTURE_PREDICTION"],
            "repair_severity": "non_repairable",
            "repair_confidence": 0.0,
            "repair_summary": "No structure available — cannot repair what doesn't exist.",
        }

    # --- Atoms too close ---
    if min_bond is not None and min_bond < _MIN_DISTANCES["default"]:
        if min_bond < 0.5:
            actions.append(f"OVERLAPPING_ATOMS (d={min_bond:.3f}Å) — likely non-repairable")
            severity_score += 3
        elif min_bond < 1.0:
            actions.append(f"VERY_SHORT_BONDS (d={min_bond:.3f}Å) — scale cell or remove site")
            severity_score += 2
        else:
            actions.append(f"SHORT_BONDS (d={min_bond:.3f}Å) — minor cell scaling may fix")
            severity_score += 1

    # --- Volume issues ---
    if vol_per_atom is not None:
        if vol_per_atom < _VOLUME_LIMITS["min"]:
            actions.append(f"CELL_TOO_SMALL ({vol_per_atom:.1f}Å³/atom) — expand lattice vectors")
            severity_score += 2
        elif vol_per_atom > _VOLUME_LIMITS["max"]:
            actions.append(f"CELL_TOO_LARGE ({vol_per_atom:.1f}Å³/atom) — shrink or rebuild cell")
            severity_score += 2
        elif vol_per_atom < _VOLUME_LIMITS["ideal_min"]:
            actions.append(f"SMALL_CELL ({vol_per_atom:.1f}Å³/atom) — slight expansion recommended")
            severity_score += 1

    # --- Sparse structure ---
    if mean_nn is not None and mean_nn > 4.0:
        actions.append(f"SPARSE_PACKING (mean_NN={mean_nn:.2f}Å) — check if sites are correct")
        severity_score += 1

    # --- Density anomaly ---
    if density is not None:
        if density < 1.0:
            actions.append(f"VERY_LOW_DENSITY ({density:.2f}g/cm³) — likely missing atoms or wrong cell")
            severity_score += 2
        elif density > 20.0:
            actions.append(f"VERY_HIGH_DENSITY ({density:.2f}g/cm³) — likely compressed cell")
            severity_score += 2

    # --- Single atom ---
    if "SINGLE_ATOM_STRUCTURE" in warnings:
        actions.append("SINGLE_ATOM — needs full structure reconstruction")
        severity_score += 3

    # --- Load/parse failures ---
    if any("FAILED" in w for w in warnings):
        actions.append("PARSE_FAILURE — structure may be malformed CIF")
        severity_score += 2

    # --- Classify severity ---
    if severity_score == 0:
        severity = "none"
        repair_conf = 1.0
    elif severity_score <= 1:
        severity = "minor"
        repair_conf = 0.85
    elif severity_score <= 3:
        severity = "moderate"
        repair_conf = 0.55
    elif severity_score <= 5:
        severity = "severe"
        repair_conf = 0.25
    else:
        severity = "non_repairable"
        repair_conf = 0.05

    repairable = severity in ("none", "minor", "moderate")

    # --- Summary ---
    if severity == "none":
        summary = "Structure looks clean — no repair needed."
    elif repairable:
        summary = f"{len(actions)} repair action(s) recommended ({severity}). Structure may be recoverable."
    else:
        summary = f"Structure has severe issues ({len(actions)} problems). Likely needs full rebuild or discard."

    return {
        "repairable_structure": repairable,
        "repair_actions_recommended": actions if actions else ["NONE_NEEDED"],
        "repair_severity": severity,
        "repair_confidence": round(repair_conf, 2),
        "repair_summary": summary,
    }
