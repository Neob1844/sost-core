"""Score and rank generated candidates."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from release.rarity import get_rarity
except ImportError:
    def get_rarity(elements):
        return {"rarity": {"label": "unknown"}}


def score_candidate(candidate):
    """Score a single candidate on multiple dimensions.

    Returns dict with scores and composite ranking.
    All scores are 0-1 (higher = more interesting).
    """
    formula = candidate["formula"]
    elements = candidate["elements"]
    n_elements = len(elements)

    # Complexity / novelty proxy
    if n_elements <= 1:
        complexity = 0.1
    elif n_elements == 2:
        complexity = 0.3
    elif n_elements == 3:
        complexity = 0.6
    elif n_elements == 4:
        complexity = 0.8
    else:
        complexity = 0.9

    # Rarity proxy from elemental abundance
    rarity_data = get_rarity(elements)
    rarity_label = rarity_data.get("rarity", {}).get("label", "unknown")
    rarity_score = {
        "very abundant": 0.1, "abundant": 0.2, "moderately abundant": 0.4,
        "uncommon": 0.6, "rare": 0.8, "very rare": 0.9, "extremely rare": 1.0,
    }.get(rarity_label, 0.5)

    # Method bonus (more creative methods score higher)
    method_score = {
        "element_substitution": 0.4,
        "single_site_doping": 0.6,
        "mixed_parent": 0.7,
        "cross_substitution": 0.5,
    }.get(candidate.get("method", ""), 0.3)

    # Composite score
    composite = (
        0.30 * complexity +
        0.25 * rarity_score +
        0.25 * method_score +
        0.20 * 0.5  # placeholder for predicted-property score
    )

    return {
        "complexity_score": round(complexity, 3),
        "rarity_score": round(rarity_score, 3),
        "method_score": round(method_score, 3),
        "composite_score": round(composite, 3),
        "rarity_label": rarity_label,
        "confidence": "heuristic",
        "note": "Scored using element count, rarity, and generation method. "
                "No DFT or ML prediction applied. Requires stronger validation.",
    }


def rank_candidates(candidates):
    """Score all candidates and return sorted by composite score."""
    scored = []
    for c in candidates:
        scores = score_candidate(c)
        c["scores"] = scores
        c["composite_score"] = scores["composite_score"]
        scored.append(c)

    scored.sort(key=lambda x: -x["composite_score"])
    for i, c in enumerate(scored):
        c["rank"] = i + 1

    return scored
