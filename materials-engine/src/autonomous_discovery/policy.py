"""Discovery policy: explore/exploit balance, campaign profiles, scoring weights."""

CAMPAIGN_PROFILES = {
    "exotic_hunt": {
        "description": "Search for novel, rare, and structurally unusual materials",
        "weights": {"novelty": 0.35, "exotic": 0.30, "stability": 0.15, "value": 0.10, "diversity": 0.10},
        "explore_ratio": 0.6, "exploit_ratio": 0.3, "diversify_ratio": 0.1,
        "min_novelty": 0.5, "min_stability": 0.2,
    },
    "valuable_unknowns": {
        "description": "Find high-value materials not yet in the corpus",
        "weights": {"novelty": 0.20, "exotic": 0.10, "stability": 0.25, "value": 0.35, "diversity": 0.10},
        "explore_ratio": 0.4, "exploit_ratio": 0.4, "diversify_ratio": 0.2,
        "min_novelty": 0.3, "min_stability": 0.3,
    },
    "stable_novel_semiconductors": {
        "description": "Find stable, novel semiconductors with useful band gaps",
        "weights": {"novelty": 0.20, "exotic": 0.05, "stability": 0.35, "value": 0.25, "diversity": 0.15},
        "explore_ratio": 0.3, "exploit_ratio": 0.5, "diversify_ratio": 0.2,
        "min_novelty": 0.2, "min_stability": 0.4,
        "target_band_gap": [0.5, 3.0],
    },
    "exploratory_oxides": {
        "description": "Explore oxide chemical space broadly",
        "weights": {"novelty": 0.30, "exotic": 0.15, "stability": 0.20, "value": 0.15, "diversity": 0.20},
        "explore_ratio": 0.6, "exploit_ratio": 0.2, "diversify_ratio": 0.2,
        "element_filter": ["O"],
    },
    "strategic_materials_search": {
        "description": "Find materials with strategic/industrial relevance",
        "weights": {"novelty": 0.15, "exotic": 0.05, "stability": 0.30, "value": 0.40, "diversity": 0.10},
        "explore_ratio": 0.3, "exploit_ratio": 0.5, "diversify_ratio": 0.2,
        "min_stability": 0.3,
    },
    "battery_relevant": {
        "description": "Explore materials relevant to battery technology",
        "weights": {"novelty": 0.15, "exotic": 0.05, "stability": 0.35, "value": 0.35, "diversity": 0.10},
        "explore_ratio": 0.3, "exploit_ratio": 0.5, "diversify_ratio": 0.2,
        "element_filter": ["Li", "Na", "Co", "Mn", "Ni", "Fe", "O", "S", "P"],
    },
    "photonics_candidates": {
        "description": "Find materials with interesting optical/electronic properties",
        "weights": {"novelty": 0.20, "exotic": 0.10, "stability": 0.25, "value": 0.30, "diversity": 0.15},
        "target_band_gap": [1.0, 4.0],
    },
    "balanced": {
        "description": "Default balanced discovery profile",
        "weights": {"novelty": 0.25, "exotic": 0.15, "stability": 0.25, "value": 0.25, "diversity": 0.10},
        "explore_ratio": 0.5, "exploit_ratio": 0.3, "diversify_ratio": 0.2,
    },
}


def get_profile(name):
    """Get a campaign profile by name, defaulting to 'balanced'."""
    return CAMPAIGN_PROFILES.get(name, CAMPAIGN_PROFILES["balanced"])


def compute_composite_score(candidate_scores, profile):
    """Compute weighted composite score for a candidate given a profile."""
    w = profile.get("weights", CAMPAIGN_PROFILES["balanced"]["weights"])
    score = 0.0
    for key, weight in w.items():
        score += weight * candidate_scores.get(key, 0.0)
    return round(min(1.0, max(0.0, score)), 4)
