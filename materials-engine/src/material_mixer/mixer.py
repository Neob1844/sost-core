"""Main mixer entry point — combines generator, scorer, and reporter."""
from .generator import generate_candidates
from .scorer import rank_candidates
from .report import build_report


def run_mix(parent_a, parent_b, max_candidates=20):
    """Run a full material mixing operation.

    Args:
        parent_a: Chemical formula (e.g., "GaAs")
        parent_b: Chemical formula (e.g., "AlN")
        max_candidates: Maximum candidates to generate

    Returns:
        dict with full report including ranked candidates and disclaimer
    """
    candidates = generate_candidates(parent_a, parent_b, max_candidates=max_candidates)
    if not candidates:
        return {
            "parent_a": parent_a,
            "parent_b": parent_b,
            "total_candidates": 0,
            "candidates": [],
            "error": "No valid candidates could be generated from these parents",
            "disclaimer": "This is a theoretical exploration tool, not a prediction.",
        }

    ranked = rank_candidates(candidates)
    return build_report(parent_a, parent_b, ranked)
