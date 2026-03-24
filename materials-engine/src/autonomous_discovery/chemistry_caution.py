"""Chemistry caution labels — flags unusual stoichiometry, family support, risk.

Assigns human-readable caution labels and family tags to candidates.
Does NOT reject candidates — only labels them for informed display.
"""
from .chem_filters import parse_formula

_ANIONS = {"O", "S", "Se", "Te", "N", "F", "Cl", "Br", "I"}

# Well-known compound families (element sets → family name)
_FAMILIES = {
    frozenset({"Li", "Co", "O"}): "Layered oxide (LiCoO2 family)",
    frozenset({"Na", "Co", "O"}): "Layered oxide (NaCoO2 family)",
    frozenset({"K", "Co", "O"}): "Layered oxide (KCoO2 family)",
    frozenset({"Rb", "Co", "O"}): "Layered oxide (RbCoO2 family)",
    frozenset({"Li", "Ti", "O"}): "Battery anode (LiTiO2 family)",
    frozenset({"Li", "Fe", "O"}): "Battery cathode (LiFeO2 family)",
    frozenset({"Ba", "Ti", "O"}): "Perovskite oxide (BaTiO3 family)",
    frozenset({"Sr", "Ti", "O"}): "Perovskite oxide (SrTiO3 family)",
    frozenset({"Ga", "As"}): "III-V semiconductor",
    frozenset({"In", "As"}): "III-V semiconductor",
    frozenset({"Ga", "N"}): "III-V nitride",
    frozenset({"In", "P"}): "III-V semiconductor",
    frozenset({"Al", "N"}): "III-V nitride",
    frozenset({"Cd", "Te"}): "II-VI semiconductor (CdTe)",
    frozenset({"Zn", "O"}): "II-VI oxide (ZnO)",
    frozenset({"Zn", "S"}): "II-VI sulfide",
    frozenset({"Si", "N"}): "Nitride ceramic (Si3N4 family)",
    frozenset({"Si", "C"}): "Carbide ceramic (SiC)",
    frozenset({"Ti", "O"}): "Oxide (TiO2 family)",
    frozenset({"Fe", "O"}): "Iron oxide",
    frozenset({"Si", "Ge"}): "Group IV alloy",
}

_BATTERY_ELEMENTS = {"Li", "Na", "Co", "Ni", "Mn", "Fe"}
_III_V_CATIONS = {"Ga", "In", "Al", "B"}
_III_V_ANIONS = {"N", "P", "As", "Sb"}
_CHALCOGENIDES = {"S", "Se", "Te"}


def label_candidate(formula):
    """Assign chemistry caution labels and family tags.

    Returns dict with:
      family: str or None (e.g. "III-V semiconductor")
      caution_labels: list of strings
      risk_level: "familiar" | "plausible" | "unusual" | "risky"
      short_why: one-line reason for interest
      short_caution: one-line caution note (or None)
    """
    comp = parse_formula(formula)
    if not comp:
        return {"family": None, "caution_labels": ["PARSE_ERROR"],
                "risk_level": "risky", "short_why": "Could not parse formula",
                "short_caution": "Formula could not be analyzed"}

    elems = set(comp.keys())
    anions_present = elems & _ANIONS
    cations_present = elems - _ANIONS
    n_elem = len(comp)
    stoich = list(comp.values())

    labels = []
    family = None
    risk = "plausible"

    # --- Family identification ---
    for fset, fname in _FAMILIES.items():
        if elems == fset or (elems >= fset and n_elem <= len(fset) + 1):
            family = fname
            labels.append("FAMILY SUPPORTED")
            break

    # Broader family patterns
    if not family:
        if cations_present & _III_V_CATIONS and anions_present & _III_V_ANIONS:
            family = "III-V variant"
            labels.append("III-V FAMILY")
        elif cations_present & _BATTERY_ELEMENTS and "O" in elems:
            family = "Battery-relevant oxide"
            labels.append("BATTERY-RELEVANT")
        elif anions_present & _CHALCOGENIDES and len(cations_present) >= 1:
            family = "Chalcogenide"
            labels.append("CHALCOGENIDE VARIANT")
        elif "O" in elems and len(cations_present) >= 2:
            family = "Mixed oxide"
            labels.append("MIXED OXIDE")
        elif not anions_present and n_elem == 2:
            family = "Binary alloy"
            labels.append("ALLOY-LIKE")

    # --- Stoichiometry checks ---
    if "O" in comp:
        metal_count = sum(comp[e] for e in cations_present)
        o_count = comp["O"]
        if metal_count > o_count * 2:
            labels.append("SUBOXIDE-LIKE")
            if "FAMILY SUPPORTED" not in labels:
                risk = "unusual"

    if n_elem == 2:
        ratio = max(stoich) / max(min(stoich), 1)
        if ratio > 3:
            labels.append("UNUSUAL STOICHIOMETRY")
            risk = "unusual"

    if n_elem >= 4:
        labels.append("COMPLEX COMPOSITION")
        if "FAMILY SUPPORTED" not in labels:
            risk = "unusual"

    # --- Risk assessment ---
    if "FAMILY SUPPORTED" in labels or family in ("III-V semiconductor", "III-V nitride",
                                                     "II-VI semiconductor (CdTe)", "Battery anode (LiTiO2 family)"):
        risk = "familiar"
    elif "SUBOXIDE-LIKE" in labels or "UNUSUAL STOICHIOMETRY" in labels:
        risk = max(risk, "unusual") if risk != "risky" else risk
    elif not family and not labels:
        risk = "unusual"
        labels.append("NO FAMILY MATCH")

    # "risky" only for truly extreme cases
    if "UNUSUAL STOICHIOMETRY" in labels and "NO FAMILY MATCH" in labels:
        risk = "risky"

    # --- Short descriptions ---
    why = _short_why(formula, family, comp, elems)
    caution = _short_caution(labels, risk)

    return {
        "family": family,
        "caution_labels": labels,
        "risk_level": risk,
        "short_why": why,
        "short_caution": caution,
    }


def _short_why(formula, family, comp, elems):
    if family:
        return f"{family} — computationally generated variant"
    if not (elems & _ANIONS):
        return "Metallic/alloy composition — potential structural material"
    return "Novel composition — no established family match in engine"


def _short_caution(labels, risk):
    if risk == "familiar":
        return None
    if "SUBOXIDE-LIKE" in labels:
        return "Metal-rich oxide (suboxide) — rare stoichiometry, needs validation"
    if "UNUSUAL STOICHIOMETRY" in labels:
        return "Unusual element ratio — verify stability before further investigation"
    if "NO FAMILY MATCH" in labels:
        return "No known compound family — higher uncertainty, exploratory candidate"
    if risk == "unusual":
        return "Uncommon composition — treat as exploratory"
    return None
