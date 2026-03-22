"""Elemental rarity and crust abundance for plain-language explanations.

Abundances are approximate ppm by weight in Earth's crust (Clarke values).
Sources: CRC Handbook, USGS, Wikipedia geochemistry tables.
"""

# ppm by weight in Earth's crust (approximate)
CRUST_ABUNDANCE = {
    "O": 461000, "Si": 282000, "Al": 82300, "Fe": 56300, "Ca": 41500,
    "Na": 23600, "K": 20900, "Mg": 23300, "Ti": 5650, "H": 1400,
    "P": 1050, "Mn": 950, "F": 585, "Ba": 425, "Sr": 370,
    "S": 350, "C": 200, "Zr": 165, "V": 120, "Cl": 145,
    "Cr": 102, "Ni": 84, "Zn": 70, "Cu": 60, "Co": 25,
    "Li": 20, "N": 19, "Ga": 19, "Nb": 20, "Pb": 14,
    "B": 10, "Th": 9.6, "Sn": 2.3, "As": 1.8, "Mo": 1.2,
    "W": 1.3, "Ge": 1.5, "Cs": 3, "Be": 2.8, "U": 2.7,
    "Ta": 2, "Hf": 3, "Br": 2.4, "Sb": 0.2, "Cd": 0.15,
    "Se": 0.05, "In": 0.25, "Ag": 0.075, "Bi": 0.009,
    "Te": 0.001, "Au": 0.004, "Pt": 0.005, "Pd": 0.015,
    "Ru": 0.001, "Rh": 0.001, "Ir": 0.001, "Os": 0.002,
    "Re": 0.0007, "He": 0.008, "Ne": 0.005, "Ar": 3.5,
    "Kr": 0.0001, "Xe": 0.00003,
    "Sc": 22, "Y": 33, "La": 39, "Ce": 66.5, "Pr": 9.2,
    "Nd": 41.5, "Sm": 7.05, "Eu": 2, "Gd": 6.2, "Tb": 1.2,
    "Dy": 5.2, "Ho": 1.3, "Er": 3.5, "Tm": 0.52, "Yb": 3.2,
    "Lu": 0.8, "Rb": 90, "I": 0.45,
}


def _label_from_ppm(ppm):
    """Classify abundance into human labels."""
    if ppm >= 10000:
        return "very abundant", "one of the most common elements in Earth's crust"
    elif ppm >= 100:
        return "abundant", "well-represented in Earth's crust"
    elif ppm >= 10:
        return "moderately abundant", "present but not dominant in the crust"
    elif ppm >= 1:
        return "uncommon", "relatively scarce in the crust"
    elif ppm >= 0.1:
        return "rare", "rare in Earth's crust"
    elif ppm >= 0.01:
        return "very rare", "very scarce — found in trace quantities"
    else:
        return "extremely rare", "extremely scarce in the crust"


def _comparison(ppm):
    """Generate a human comparison."""
    if ppm >= 10000:
        return "comparable to silicon or aluminum"
    elif ppm >= 1000:
        return "similar to titanium or hydrogen in abundance"
    elif ppm >= 100:
        return "roughly as common as chromium or zinc"
    elif ppm >= 10:
        return "rarer than copper but more common than silver"
    elif ppm >= 1:
        return "similar rarity to tin or arsenic"
    elif ppm >= 0.1:
        return "rarer than most industrial metals"
    elif ppm >= 0.01:
        return "precious-metal territory — comparable to gold or platinum"
    else:
        return "among the rarest naturally occurring elements"


def get_rarity(elements):
    """Get rarity assessment for a material based on its elements.

    For single elements: direct crust abundance.
    For compounds: uses the rarest element as the limiting factor.
    """
    if not elements:
        return None

    # Find the rarest element
    rarest_elem = None
    rarest_ppm = None
    all_known = True

    for elem in elements:
        ppm = CRUST_ABUNDANCE.get(elem)
        if ppm is None:
            all_known = False
            continue
        if rarest_ppm is None or ppm < rarest_ppm:
            rarest_ppm = ppm
            rarest_elem = elem

    if rarest_ppm is None:
        return {
            "rarity": {"label": "unknown", "reason": "Abundance data not available for these elements"},
            "crust_abundance": None,
        }

    label, reason = _label_from_ppm(rarest_ppm)
    comparison = _comparison(rarest_ppm)

    scope = "elemental_abundance" if len(elements) == 1 else "limiting_element_abundance"
    confidence = "high" if all_known and len(elements) <= 2 else "medium"

    if len(elements) > 1:
        reason = f"Limited by {rarest_elem} ({rarest_ppm} ppm) — {reason}"

    return {
        "rarity": {"label": label, "reason": reason},
        "crust_abundance": {
            "technical": {
                "value": rarest_ppm,
                "unit": "ppm",
                "limiting_element": rarest_elem,
                "basis": "approximate Earth crust abundance by weight",
            },
            "human": {
                "label": reason,
                "comparison": comparison,
            },
            "confidence": confidence,
            "scope": scope,
        },
    }
