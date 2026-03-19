"""Element substitution and stoichiometry rules for candidate generation.

Phase III.D: Heuristic-based, cheap, reproducible. NOT ab-initio validated.

Substitution families are based on chemical similarity (group, radius, valence).
These are approximations — generated candidates are plausible hypotheses, not
confirmed stable materials.
"""

import logging
from typing import List, Dict, Set, Optional

log = logging.getLogger(__name__)

# Element substitution families — elements within a family are
# roughly interchangeable in many crystal structures.
# Based on ionic radius / oxidation state / periodic group similarity.
SUBSTITUTION_FAMILIES: Dict[str, List[str]] = {
    # Alkali metals
    "alkali": ["Li", "Na", "K", "Rb", "Cs"],
    # Alkaline earth
    "alkaline_earth": ["Be", "Mg", "Ca", "Sr", "Ba"],
    # 3d transition metals (similar radius)
    "3d_early": ["Sc", "Ti", "V", "Cr"],
    "3d_mid": ["Mn", "Fe", "Co", "Ni"],
    "3d_late": ["Cu", "Zn"],
    # 4d transition metals
    "4d_early": ["Y", "Zr", "Nb", "Mo"],
    "4d_late": ["Ru", "Rh", "Pd", "Ag"],
    # 5d transition metals
    "5d_early": ["Hf", "Ta", "W", "Re"],
    "5d_late": ["Os", "Ir", "Pt", "Au"],
    # Rare earth (lanthanides)
    "rare_earth_light": ["La", "Ce", "Pr", "Nd"],
    "rare_earth_heavy": ["Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu"],
    # Post-transition metals
    "post_transition": ["Al", "Ga", "In", "Tl"],
    # Metalloids / semiconductors
    "group14": ["Si", "Ge", "Sn"],
    "group15": ["N", "P", "As", "Sb", "Bi"],
    # Chalcogens
    "chalcogen": ["O", "S", "Se", "Te"],
    # Halogens
    "halogen": ["F", "Cl", "Br", "I"],
    # Actinides
    "actinide": ["Th", "U", "Np", "Pu"],
}

# Reverse map: element → list of families it belongs to
_ELEM_TO_FAMILIES: Dict[str, List[str]] = {}
for fam, elems in SUBSTITUTION_FAMILIES.items():
    for e in elems:
        _ELEM_TO_FAMILIES.setdefault(e, []).append(fam)

# Valid elements (subset of ELEM_LIST that appears in at least one family)
ALL_SUBSTITUTABLE = set()
for elems in SUBSTITUTION_FAMILIES.values():
    ALL_SUBSTITUTABLE.update(elems)


def get_substitutes(element: str, max_subs: int = 4) -> List[str]:
    """Get plausible substitution elements for a given element.

    Returns elements from the same family, excluding the original.
    """
    families = _ELEM_TO_FAMILIES.get(element, [])
    subs = set()
    for fam in families:
        for e in SUBSTITUTION_FAMILIES[fam]:
            if e != element:
                subs.add(e)
    return sorted(subs)[:max_subs]


def get_family(element: str) -> Optional[str]:
    """Get primary family for an element."""
    families = _ELEM_TO_FAMILIES.get(element, [])
    return families[0] if families else None


# Stoichiometry perturbation rules
COMMON_STOICHIOMETRIES = [
    (1, 1), (1, 2), (1, 3), (2, 1), (2, 3), (3, 1), (3, 2),
    (1, 4), (4, 1), (2, 5), (3, 4), (3, 5),
]


def perturb_formula_counts(element_counts: Dict[str, int],
                           max_delta: int = 1) -> List[Dict[str, int]]:
    """Generate small stoichiometry perturbations.

    Only changes one element count by ±1 at a time.
    Rejects results with any count <= 0.
    """
    results = []
    for elem, count in element_counts.items():
        for delta in range(-max_delta, max_delta + 1):
            if delta == 0:
                continue
            new_count = count + delta
            if new_count <= 0:
                continue
            new_counts = dict(element_counts)
            new_counts[elem] = new_count
            results.append(new_counts)
    return results


def counts_to_formula(element_counts: Dict[str, int]) -> str:
    """Convert element counts to formula string."""
    parts = []
    for elem in sorted(element_counts.keys()):
        c = element_counts[elem]
        if c == 1:
            parts.append(elem)
        else:
            parts.append(f"{elem}{c}")
    return "".join(parts)


def formula_to_counts(formula: str) -> Dict[str, int]:
    """Parse simple formula to element counts. Best-effort."""
    import re
    counts = {}
    for match in re.finditer(r'([A-Z][a-z]?)(\d*)', formula):
        elem = match.group(1)
        num = int(match.group(2)) if match.group(2) else 1
        if elem:
            counts[elem] = counts.get(elem, 0) + num
    return counts


def plausibility_score(elements: List[str], n_elements: int,
                       spacegroup: Optional[int],
                       parent_formula: Optional[str] = None) -> float:
    """Heuristic plausibility score for a generated candidate.

    Returns 0.0 (implausible) to 1.0 (highly plausible).
    NOT a physics validation — just sanity checks.
    """
    score = 0.5  # baseline

    # Penalty for too many unique elements
    if n_elements > 6:
        score -= 0.2
    elif n_elements <= 3:
        score += 0.1

    # Bonus if all elements are in known substitution families
    known_fraction = sum(1 for e in elements if e in ALL_SUBSTITUTABLE) / max(len(elements), 1)
    score += 0.2 * known_fraction

    # Bonus if spacegroup is specified
    if spacegroup and 1 <= spacegroup <= 230:
        score += 0.1

    # Small bonus if derived from a parent
    if parent_formula:
        score += 0.05

    return max(0.0, min(1.0, score))
