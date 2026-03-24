"""Physics-aware screening — structure sanity and pre-DFT quality checks.

Validates lifted crystal structures for geometric plausibility before
recommending them for DFT or stronger validation. NOT a substitute
for actual DFT — a heuristic pre-filter.
"""
import numpy as np

try:
    from pymatgen.core import Structure
    HAS_PYMATGEN = True
except ImportError:
    HAS_PYMATGEN = False

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from normalization.structure import load_structure
    HAS_LOADER = True
except ImportError:
    HAS_LOADER = False


# Typical density ranges (g/cm³) by compound family
_DENSITY_RANGES = {
    "oxide": (2.5, 8.0),
    "sulfide": (3.0, 8.5),
    "metal": (2.0, 22.0),
    "semiconductor": (2.0, 7.0),
    "default": (1.5, 15.0),
}

# Minimum plausible bond distance (Å)
_MIN_BOND_DISTANCE = 1.2
# Maximum reasonable bond distance for nearest neighbor (Å)
_MAX_NN_DISTANCE = 4.5


def screen_structure(cif_text, formula="", family=None):
    """Screen a lifted structure for geometric plausibility.

    Args:
        cif_text: CIF string of lifted structure
        formula: chemical formula for context
        family: compound family from chemistry_caution (optional)

    Returns dict with:
        structure_sanity_score: 0.0-1.0 (higher = more plausible)
        bond_distance_sanity: bool
        density_sanity: bool
        volume_per_atom: float or None
        min_bond_distance: float or None
        mean_nn_distance: float or None
        density: float or None
        geometry_warnings: list of strings
        physics_flags: list of strings
        pre_dft_ready: bool
    """
    result = {
        "structure_sanity_score": 0.0,
        "bond_distance_sanity": False,
        "density_sanity": False,
        "volume_per_atom": None,
        "min_bond_distance": None,
        "mean_nn_distance": None,
        "density": None,
        "geometry_warnings": [],
        "physics_flags": [],
        "pre_dft_ready": False,
    }

    if not cif_text or not HAS_PYMATGEN or not HAS_LOADER:
        result["geometry_warnings"].append("NO_STRUCTURE_AVAILABLE")
        return result

    # Load structure
    try:
        struct = load_structure(cif_text)
        if struct is None:
            result["geometry_warnings"].append("STRUCTURE_LOAD_FAILED")
            return result
    except Exception as e:
        result["geometry_warnings"].append(f"STRUCTURE_ERROR: {str(e)[:50]}")
        return result

    score = 0.5  # start neutral
    warnings = []
    flags = []

    # --- Volume per atom ---
    try:
        vol_per_atom = struct.volume / struct.num_sites
        result["volume_per_atom"] = round(vol_per_atom, 2)

        if vol_per_atom < 5.0:
            warnings.append(f"VERY_SMALL_VOLUME ({vol_per_atom:.1f} Å³/atom)")
            score -= 0.15
        elif vol_per_atom < 8.0:
            score -= 0.05  # small but possible
        elif vol_per_atom > 80.0:
            warnings.append(f"VERY_LARGE_VOLUME ({vol_per_atom:.1f} Å³/atom)")
            score -= 0.15
        elif vol_per_atom > 50.0:
            score -= 0.05
        else:
            score += 0.10  # reasonable volume
    except Exception:
        warnings.append("VOLUME_CALCULATION_FAILED")

    # --- Density ---
    try:
        density = struct.density
        result["density"] = round(density, 3)

        fam_key = "default"
        if family:
            fl = family.lower()
            if "oxide" in fl:
                fam_key = "oxide"
            elif "sulfide" in fl or "chalcogenide" in fl:
                fam_key = "sulfide"
            elif "alloy" in fl or "metal" in fl:
                fam_key = "metal"
            elif "semiconductor" in fl or "III-V" in fl or "II-VI" in fl:
                fam_key = "semiconductor"

        lo, hi = _DENSITY_RANGES.get(fam_key, _DENSITY_RANGES["default"])

        if lo <= density <= hi:
            result["density_sanity"] = True
            score += 0.10
        elif density < lo * 0.5 or density > hi * 1.5:
            warnings.append(f"EXTREME_DENSITY ({density:.2f} g/cm³, expected {lo:.1f}-{hi:.1f})")
            score -= 0.15
        else:
            warnings.append(f"UNUSUAL_DENSITY ({density:.2f} g/cm³)")
            score -= 0.05
    except Exception:
        warnings.append("DENSITY_CALCULATION_FAILED")

    # --- Bond distances ---
    try:
        all_nn = struct.get_all_neighbors(4.0)
        if all_nn:
            dists = []
            for site_nn in all_nn:
                for nn in site_nn:
                    dists.append(nn.nn_distance)

            if dists:
                min_d = min(dists)
                mean_d = sum(dists) / len(dists)
                result["min_bond_distance"] = round(min_d, 3)
                result["mean_nn_distance"] = round(mean_d, 3)

                if min_d < _MIN_BOND_DISTANCE:
                    warnings.append(f"ATOMS_TOO_CLOSE ({min_d:.3f} Å < {_MIN_BOND_DISTANCE} Å)")
                    score -= 0.20
                elif min_d < 1.5:
                    warnings.append(f"SHORT_BONDS ({min_d:.3f} Å)")
                    score -= 0.05
                else:
                    result["bond_distance_sanity"] = True
                    score += 0.10

                if mean_d > _MAX_NN_DISTANCE:
                    warnings.append(f"SPARSE_STRUCTURE (mean NN={mean_d:.2f} Å)")
                    score -= 0.10
            else:
                warnings.append("NO_NEIGHBORS_FOUND")
                score -= 0.10
        else:
            warnings.append("NEIGHBOR_SEARCH_FAILED")
    except Exception:
        warnings.append("BOND_ANALYSIS_FAILED")

    # --- Site count ---
    if struct.num_sites < 2:
        warnings.append("SINGLE_ATOM_STRUCTURE")
        score -= 0.20
    elif struct.num_sites > 200:
        warnings.append(f"VERY_LARGE_CELL ({struct.num_sites} atoms)")
        flags.append("LARGE_CELL")

    # --- Determine physics flags ---
    if not warnings:
        flags.append("PHYSICS_SCREENED_PASS")
    if result["bond_distance_sanity"] and result["density_sanity"]:
        flags.append("STRUCTURE_SANITY_PASS")
    if any("EXTREME" in w or "TOO_CLOSE" in w or "SINGLE_ATOM" in w for w in warnings):
        flags.append("GEOMETRY_WARNING")

    score = round(max(0.0, min(1.0, score)), 4)
    result["structure_sanity_score"] = score
    result["geometry_warnings"] = warnings
    result["physics_flags"] = flags
    result["pre_dft_ready"] = score >= 0.55 and "GEOMETRY_WARNING" not in flags

    return result


def compute_pre_dft_score(physics_result, uncertainty=None, readiness=None,
                           scores=None, candidate_context=None):
    """Combine physics screening with existing scores for pre-DFT readiness.

    Returns dict with:
        pre_dft_physics_score: 0.0-1.0
        relaxation_candidate: bool
        relaxation_recommendation: str
    """
    phys = physics_result.get("structure_sanity_score", 0)
    ready = readiness.get("validation_readiness_score", 0) if readiness else 0
    conf = uncertainty.get("confidence_score", 0.5) if uncertainty else 0.5
    composite = scores.get("composite_score", 0.5) if isinstance(scores, dict) else 0.5
    chem_risk = (candidate_context or {}).get("risk_level", "unknown")

    # Weighted combination
    pre_dft = 0.0
    pre_dft += phys * 0.35       # physics screening weight
    pre_dft += ready * 0.25      # validation readiness
    pre_dft += conf * 0.20       # model confidence
    pre_dft += composite * 0.10  # overall score
    # Chemistry risk adjustment
    if chem_risk == "familiar":
        pre_dft += 0.05
    elif chem_risk == "risky":
        pre_dft -= 0.05

    pre_dft = round(max(0.0, min(1.0, pre_dft)), 4)

    # Relaxation candidate?
    relax = pre_dft >= 0.50 and physics_result.get("pre_dft_ready", False)

    if relax:
        rec = "good_relaxation_candidate"
    elif phys >= 0.40 and not physics_result.get("pre_dft_ready"):
        rec = "needs_structure_repair"
    elif phys < 0.30:
        rec = "unstable_geometry_suspected"
    else:
        rec = "watchlist"

    return {
        "pre_dft_physics_score": pre_dft,
        "relaxation_candidate": relax,
        "relaxation_recommendation": rec,
    }
