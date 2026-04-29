"""
M4 — heavy_pgm_replacement_screen

PGM-free replacement screening over a large slice of the pinned formula
pool. No mission dimension. Streams top-50 via a bounded heap so RSS is
bounded regardless of slice size.

Phase 4-B determinism contract: same as M3 (see
heavy_mission_consensus_screen.py).
"""

import heapq
from typing import Dict, List, Tuple

from ..utils.canonical_hash import canonical_sha256
from ..utils.parse_formula import parse_formula
from ..utils.pgm_replacement_tables import pgm_replacement_score_from_counts


TOP_K = 50
HIST_BINS = 10

# Minimum replacement_score to qualify for the shortlist. Mirrors the
# default in pgm_replacement_engine.find_replacements (min_score=0.3).
SHORTLIST_MIN_SCORE = 0.3


class _RevStr:
    """Reverse string compare — see heavy_mission_consensus_screen for
    rationale (alpha-latest formula sinks to heap[0] for tie-break
    eviction)."""
    __slots__ = ("s",)
    def __init__(self, s: str):
        self.s = s
    def __lt__(self, other: "_RevStr") -> bool:
        return self.s > other.s
    def __eq__(self, other: object) -> bool:
        return isinstance(other, _RevStr) and self.s == other.s
    def __hash__(self) -> int:
        return hash(self.s)


def _empty_histogram() -> List[int]:
    return [0] * HIST_BINS


def _bump_histogram(hist: List[int], score: float) -> None:
    if score <= 0.0:
        idx = 0
    elif score >= 1.0:
        idx = HIST_BINS - 1
    else:
        idx = int(score * HIST_BINS)
        if idx >= HIST_BINS:
            idx = HIST_BINS - 1
    hist[idx] += 1


def _slice_pool(pool: List[str], slice_index: int, slice_size: int) -> List[str]:
    n = len(pool)
    if n == 0 or slice_size <= 0:
        return []
    start = (slice_index * slice_size) % n
    out = []
    for i in range(slice_size):
        out.append(pool[(start + i) % n])
    return out


def run(payload: Dict, formula_pool: List[str]) -> Dict:
    slice_index = int(payload.get("slice_index", 0))
    slice_size = int(payload.get("slice_size", 0))
    pool_sha = payload.get("formula_pool_sha256", "")

    formulas = _slice_pool(formula_pool, slice_index, slice_size)

    heap: List[Tuple[float, _RevStr, Dict]] = []
    histogram = _empty_histogram()

    family_coverage: Dict[str, int] = {}

    count_processed = 0
    count_pgm_free = 0
    count_shortlist = 0

    for formula in formulas:
        count_processed += 1
        counts = parse_formula(formula)
        if not counts:
            continue
        scored = pgm_replacement_score_from_counts(formula, counts)

        replacement_score = scored.get("replacement_score", 0.0)
        _bump_histogram(histogram, replacement_score)

        for fam in scored.get("families", []):
            family_coverage[fam] = family_coverage.get(fam, 0) + 1

        if scored.get("pgm_free", False):
            count_pgm_free += 1

        if scored.get("pgm_free", False) and replacement_score >= SHORTLIST_MIN_SCORE:
            count_shortlist += 1
            entry = (replacement_score, _RevStr(formula), scored)
            if len(heap) < TOP_K:
                heapq.heappush(heap, entry)
            else:
                if entry > heap[0]:
                    heapq.heapreplace(heap, entry)

    top_replacements = [rec for (_, _, rec) in heap]
    top_replacements.sort(
        key=lambda r: (-r["replacement_score"], r["formula"])
    )

    # Sort family_coverage by family name for deterministic output.
    family_coverage_sorted = dict(sorted(family_coverage.items()))

    body = {
        "task_type": "heavy_pgm_replacement_screen",
        "task_family": "M4",
        "mission": None,  # M4 has no mission dimension; explicit null
        "slice_index": slice_index,
        "slice_size": slice_size,
        "formula_pool_sha256": pool_sha,
        "version": "phase4b-v1",
        "top_candidates": top_replacements,
        "score_histogram": histogram,
        "family_coverage": family_coverage_sorted,
        "summary_stats": {
            "count_processed": count_processed,
            "count_passed_filter": count_shortlist,
            "count_pgm_free": count_pgm_free,
            "count_shortlist": count_shortlist,
        },
    }
    body["result_hash"] = canonical_sha256(body)
    return body
