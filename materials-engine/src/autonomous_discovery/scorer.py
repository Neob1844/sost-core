"""Multi-objective candidate scorer — Phase II hardened.

Philosophy: rare alone is not enough. A candidate must be:
- chemically plausible
- compositionally novel
- potentially valuable
- reasonably stable (or at least not obviously unstable)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from release.rarity import get_rarity
except ImportError:
    def get_rarity(e): return {"rarity": {"label": "unknown"}}

from .chem_filters import normalize_formula, ANIONS, CATIONS, COMMON_OX

STRATEGIC_ELEMENTS = {"Li","Co","Ni","W","Mo","V","Cr","Pt","Pd","Ga","In","Ge","Re","Ta","Nb"}
BATTERY_ELEMENTS = {"Li","Na","Co","Ni","Mn","Fe","O","S","P"}
SEMICONDUCTOR_ELEMENTS = {"Si","Ge","Ga","As","In","P","Sb","Al","N","Cd","Te","Zn","Se"}
CATALYST_ELEMENTS = {"Pt","Pd","Rh","Ru","Ir","Ni","Co","Fe","Ce","Zr","Ti"}

# Known stable binary families (element pair patterns that form real compounds)
KNOWN_BINARY_FAMILIES = {
    frozenset({"Ga","As"}), frozenset({"Ga","N"}), frozenset({"Al","N"}),
    frozenset({"Si","C"}), frozenset({"Si","O"}), frozenset({"Ti","O"}),
    frozenset({"Zn","O"}), frozenset({"Zn","S"}), frozenset({"Cd","Te"}),
    frozenset({"In","P"}), frozenset({"In","As"}), frozenset({"Al","As"}),
    frozenset({"Fe","O"}), frozenset({"Fe","S"}), frozenset({"Cu","O"}),
    frozenset({"Mg","O"}), frozenset({"Ca","O"}), frozenset({"Ba","O"}),
    frozenset({"Na","Cl"}), frozenset({"Li","F"}), frozenset({"Zr","O"}),
}

# Accepted threshold (Phase II: much harder)
ACCEPT_THRESHOLD = 0.45  # Phase IV.B: harder (was 0.42)
WATCHLIST_THRESHOLD = 0.32
MIN_PLAUSIBILITY = 0.30  # raised from 0.25


def score_candidate(formula, elements, method, profile, memory=None, neighbors=None):
    """Score a candidate on multiple dimensions. Phase II: much stricter."""
    n_elem = len(elements)
    elem_set = set(elements)
    norm = normalize_formula(formula)

    # 1. Novelty (element count + composition complexity)
    if n_elem <= 1: novelty = 0.05
    elif n_elem == 2: novelty = 0.25
    elif n_elem == 3: novelty = 0.55
    elif n_elem == 4: novelty = 0.75
    else: novelty = 0.85

    # 2. Exotic (rarity-based)
    rarity_data = get_rarity(elements)
    rarity_label = rarity_data.get("rarity", {}).get("label", "unknown")
    exotic = {"very abundant": 0.05, "abundant": 0.1, "moderately abundant": 0.2,
              "uncommon": 0.4, "rare": 0.6, "very rare": 0.75, "extremely rare": 0.85
              }.get(rarity_label, 0.25)

    # 3. Stability proxy (penalize complexity, reward oxide/chalcogenide patterns)
    stability = 0.5
    has_anion = bool(elem_set & ANIONS)
    has_cation = bool(elem_set & CATIONS)
    if has_anion and has_cation:
        stability = 0.7  # typical compound pattern
    if n_elem > 4:
        stability -= 0.2
    if "O" in elem_set:
        stability += 0.1  # oxides are generally more stable
    stability = max(0.0, min(1.0, stability))

    # 4. Value (strategic + sector relevance)
    strategic = len(elem_set & STRATEGIC_ELEMENTS) / max(n_elem, 1)
    battery = len(elem_set & BATTERY_ELEMENTS) / max(n_elem, 1)
    semi = len(elem_set & SEMICONDUCTOR_ELEMENTS) / max(n_elem, 1)
    catalyst = len(elem_set & CATALYST_ELEMENTS) / max(n_elem, 1)
    value = max(strategic, battery, semi, catalyst) * 0.7 + 0.15

    # 5. Plausibility (Phase II: the key new dimension)
    plausibility = _compute_plausibility(elem_set, n_elem, method)

    # 6. Family support bonus
    family_bonus = 0.0
    if n_elem == 2:
        pair = frozenset(elements)
        if pair in KNOWN_BINARY_FAMILIES:
            family_bonus = 0.15

    # 7. Diversity (method bonus, slightly reduced from Phase I)
    diversity = {"element_substitution": 0.25, "single_site_doping": 0.4,
                 "mixed_parent": 0.5, "cross_substitution": 0.35,
                 }.get(method, 0.2)

    # 8. Uncertainty penalty (moderate in Phase II)
    uncertainty_penalty = 0.10  # base uncertainty (no ML prediction)
    if n_elem >= 4:
        uncertainty_penalty += 0.1
    if not has_anion:
        uncertainty_penalty += 0.05  # intermetallics less predictable

    # 9. Memory penalties
    redundancy_penalty = 0.0
    if memory:
        rule_pen = memory.get_rule_penalty(method)
        family_pen = memory.get_family_penalty(formula)
        redundancy_penalty = max(0, 1.0 - min(rule_pen, family_pen))

    # 10. Noise penalty (penalize things that look random)
    noise = 0.0
    if n_elem >= 4 and exotic > 0.6:
        noise = 0.1  # rare + complex = likely noise
    if plausibility < 0.3:
        noise += 0.15

    # Composite score with profile weights
    from .policy import compute_composite_score
    raw_scores = {
        "novelty": round(novelty, 4),
        "exotic": round(exotic, 4),
        "stability": round(stability, 4),
        "value": round(value, 4),
        "diversity": round(diversity, 4),
    }
    base_composite = compute_composite_score(raw_scores, profile)

    # Apply bonuses and penalties
    composite = base_composite + family_bonus - uncertainty_penalty - noise
    composite *= (1.0 - 0.4 * redundancy_penalty)
    composite = round(max(0.0, min(1.0, composite)), 4)

    return {
        **raw_scores,
        "plausibility": round(plausibility, 4),
        "family_bonus": round(family_bonus, 4),
        "uncertainty_penalty": round(uncertainty_penalty, 4),
        "noise_penalty": round(noise, 4),
        "redundancy_penalty": round(redundancy_penalty, 4),
        "composite_score": composite,
        "rarity_label": rarity_label,
        "decision": "accepted" if composite >= ACCEPT_THRESHOLD and plausibility >= MIN_PLAUSIBILITY
                    else "watchlist" if composite >= WATCHLIST_THRESHOLD
                    else "rejected",
        "confidence": "heuristic",
    }


def _compute_plausibility(elem_set, n_elem, method):
    """Estimate chemical plausibility of a composition."""
    score = 0.5  # base

    # Known family patterns boost plausibility
    has_anion = bool(elem_set & ANIONS)
    has_cation = bool(elem_set & CATIONS)

    if has_anion and has_cation:
        score += 0.2  # cation-anion compound = normal chemistry

    # Oxide/chalcogenide = most common compound type
    if "O" in elem_set:
        score += 0.1
    elif elem_set & {"S", "Se", "Te"}:
        score += 0.05

    # III-V semiconductor pattern
    group_3 = elem_set & {"B", "Al", "Ga", "In"}
    group_5 = elem_set & {"N", "P", "As", "Sb"}
    if group_3 and group_5:
        score += 0.15

    # Substitution from known family = higher plausibility
    if method == "element_substitution":
        score += 0.05
    elif method == "cross_substitution":
        score += 0.03

    # Too many transition metals without anion = dubious
    transition_metals = elem_set & {"Ti","V","Cr","Mn","Fe","Co","Ni","Cu","Zn",
                                     "Zr","Nb","Mo","Ru","Rh","Pd","Ag","Cd",
                                     "Hf","Ta","W","Re","Os","Ir","Pt","Au"}
    if len(transition_metals) >= 3 and not has_anion:
        score -= 0.2

    # Penalty for too many elements without clear pattern
    if n_elem >= 4:
        score -= 0.1
    if n_elem >= 5:
        score -= 0.15

    return max(0.0, min(1.0, score))
