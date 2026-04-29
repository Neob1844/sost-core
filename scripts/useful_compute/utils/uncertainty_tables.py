"""
Uncertainty scoring tables + helper.

Mirror of internal source (uncertainty_score) with the
function signature reduced to the fields that the Heavy worker actually
provides — formula and (optionally) corpus_count.

The Heavy worker only computes uncertainty over composition (no
formation_energy / band_gap / spacegroup data is shipped with formulas
in the worker's pinned formula pool). That collapses several penalty
branches; the result MUST still be byte-identical to the engine's
output for the same (formula, no other inputs) call signature.

Stdlib only.
"""

from typing import Dict, List

from .abundance_cost_tables import ABUNDANCE_PPM


# Elements well-covered in training corpus (common in Materials Project/JARVIS)
WELL_COVERED_ELEMENTS = {
    "O", "Si", "Al", "Fe", "Ca", "Na", "Mg", "K", "Ti", "P", "Mn",
    "Ba", "C", "S", "Zr", "Cr", "Ni", "Zn", "Cu", "Co", "Li", "N",
    "La", "Ce", "Y", "Nd", "Sr", "V", "Nb", "B", "Ga", "Ge", "Se",
    "Sn", "Pb", "Bi", "Mo", "W", "F", "Cl", "In", "Ag",
}

POORLY_COVERED_ELEMENTS = {
    "Tl", "Po", "At", "Fr", "Ra", "Ac", "Pa", "Np", "Pu", "Am",
    "Cm", "Bk", "Cf", "Es", "Fm", "Md", "No", "Lr",
    "Tc", "Pm", "Os", "Re", "Ir", "Ru", "Rh",
}

CORE_PROPERTIES = ["formation_energy", "band_gap"]
EXTENDED_PROPERTIES = ["formation_energy", "band_gap", "spacegroup", "crystal_system"]


def compute_uncertainty_from_counts(formula: str,
                                    counts: Dict[str, int]) -> Dict:
    """Compute uncertainty score for a candidate (composition-only mode).

    Faithful subset of uncertainty_score.compute_uncertainty for the case
    where formation_energy / band_gap / spacegroup / crystal_system /
    relaxation_survived / composite_score / mission_fit are all None and
    corpus_count == 0.

    Worker-side this is the only signature we need: the Heavy queue only
    ships formula strings. Anything else would require shipping per-
    formula property data, which conflicts with the pinned formula pool
    contract.
    """
    elem_set = set(counts.keys())
    n_elem = len(elem_set)
    reasons: List[str] = []
    penalties: List[float] = []

    unknown_els = elem_set - WELL_COVERED_ELEMENTS
    exotic_els = elem_set & POORLY_COVERED_ELEMENTS
    if exotic_els:
        penalties.append(0.25)
        # Sort exotic_els so the reason string is byte-identical between runs
        reasons.append(
            "exotic elements with poor corpus coverage: "
            + repr(set(sorted(exotic_els)))
        )
    elif unknown_els:
        penalties.append(0.10)
        reasons.append(
            "elements outside core coverage: "
            + repr(set(sorted(unknown_els)))
        )

    if n_elem >= 6:
        penalties.append(0.15)
        reasons.append(f"highly complex composition ({n_elem} elements)")
    elif n_elem >= 5:
        penalties.append(0.08)
        reasons.append(f"complex composition ({n_elem} elements)")

    rare_count = sum(1 for el in elem_set if ABUNDANCE_PPM.get(el, 0) < 1.0)
    if rare_count >= 2:
        penalties.append(0.10)
        reasons.append(f"{rare_count} rare elements (< 1 ppm)")

    # All four properties are missing in the worker context.
    available = 0
    missing = ["formation_energy", "band_gap", "spacegroup", "crystal_system"]
    coverage_ratio = available / len(EXTENDED_PROPERTIES)
    penalties.append(0.20)
    reasons.append(
        f"low property coverage ({available}/{len(EXTENDED_PROPERTIES)}): "
        f"missing {missing}"
    )

    # relaxation_survived is None in the worker context
    penalties.append(0.10)
    reasons.append("no relaxation data — structural stability unknown")

    # No formation_energy / band_gap → no contradiction branch fires.

    # corpus_count == 0
    penalties.append(0.05)
    reasons.append("no exact corpus match — novel composition")

    uncertainty = min(1.0, sum(penalties))

    if uncertainty < 0.15:
        level = "LOW"
    elif uncertainty < 0.35:
        level = "MEDIUM"
    elif uncertainty < 0.60:
        level = "HIGH"
    else:
        level = "EXTREME"

    if not reasons:
        reasons.append("well-covered composition with good property data")

    return {
        "formula": formula,
        "uncertainty_score": round(uncertainty, 4),
        "uncertainty_level": level,
        "uncertainty_reasons": reasons,
        "property_coverage": round(coverage_ratio, 2),
        "n_elements": n_elem,
        "domain_distance": len(unknown_els),
    }
