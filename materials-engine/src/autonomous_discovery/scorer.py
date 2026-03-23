"""Multi-objective candidate scorer for autonomous discovery."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from release.rarity import get_rarity
except ImportError:
    def get_rarity(e): return {"rarity": {"label": "unknown"}}

from .policy import compute_composite_score

# Strategic element sets
STRATEGIC_ELEMENTS = {"Li","Co","Ni","W","Mo","V","Cr","Pt","Pd","Ga","In","Ge","Re","Ta","Nb"}
BATTERY_ELEMENTS = {"Li","Na","Co","Ni","Mn","Fe","O","S","P"}
SEMICONDUCTOR_ELEMENTS = {"Si","Ge","Ga","As","In","P","Sb","Al","N","Cd","Te","Zn","Se"}


def score_candidate(formula, elements, method, profile, memory=None):
    """Score a candidate on multiple dimensions. Returns dict of scores."""
    n_elem = len(elements)
    elem_set = set(elements)

    # Novelty proxy (element count complexity)
    novelty = min(1.0, (n_elem - 1) / 4.0) if n_elem > 1 else 0.1

    # Exotic (rarity-based)
    rarity_data = get_rarity(elements)
    rarity_label = rarity_data.get("rarity", {}).get("label", "unknown")
    exotic = {"very abundant": 0.05, "abundant": 0.1, "moderately abundant": 0.25,
              "uncommon": 0.45, "rare": 0.7, "very rare": 0.85, "extremely rare": 0.95
              }.get(rarity_label, 0.3)

    # Stability proxy (penalize very complex, reward moderate)
    stability = max(0.0, 1.0 - (n_elem - 2) * 0.15) if n_elem >= 2 else 0.8

    # Value (strategic + sector relevance)
    strategic_overlap = len(elem_set & STRATEGIC_ELEMENTS) / max(n_elem, 1)
    battery_overlap = len(elem_set & BATTERY_ELEMENTS) / max(n_elem, 1)
    semi_overlap = len(elem_set & SEMICONDUCTOR_ELEMENTS) / max(n_elem, 1)
    value = max(strategic_overlap, battery_overlap, semi_overlap) * 0.6 + 0.2

    # Diversity (method bonus)
    diversity = {"element_substitution": 0.3, "single_site_doping": 0.5,
                 "mixed_parent": 0.6, "cross_substitution": 0.4,
                 "stoichiometry_perturbation": 0.3, "prototype_remix": 0.5
                 }.get(method, 0.3)

    # Apply memory penalties
    redundancy_penalty = 0.0
    if memory:
        rule_pen = memory.get_rule_penalty(method)
        family_pen = memory.get_family_penalty(formula)
        redundancy_penalty = max(0, 1.0 - min(rule_pen, family_pen))

    raw_scores = {
        "novelty": round(novelty, 4),
        "exotic": round(exotic, 4),
        "stability": round(stability, 4),
        "value": round(value, 4),
        "diversity": round(diversity, 4),
    }

    composite = compute_composite_score(raw_scores, profile)
    # Apply redundancy penalty
    composite = round(composite * (1.0 - 0.3 * redundancy_penalty), 4)

    return {
        **raw_scores,
        "redundancy_penalty": round(redundancy_penalty, 4),
        "composite_score": composite,
        "rarity_label": rarity_label,
        "confidence": "heuristic",
    }
