"""
M3 — heavy_mission_consensus_screen

Single-mission consensus screen over a large slice of the pinned
formula pool. Streams top-50 via heap; never accumulates the full
scored list, so RSS is bounded regardless of slice size.

Phase 4-B determinism contract:
  - No timestamps, PIDs, run_ids in the result.
  - No `random`, no `time.time()`, no `hash()` builtin.
  - Top-K sorted by (-composite_score, formula) so ties break
    alphabetically.
  - All output is JSON-stable (stdlib types, dicts/lists/floats/ints/
    strs/bools).
  - result_hash = canonical_sha256(everything except result_hash itself).
"""

import heapq
from typing import Dict, List, Tuple

from ..utils.canonical_hash import canonical_sha256
from ..utils.mission_profiles import (
    ALL_MISSIONS, get_mission, compute_mission_score_composition_only,
)
from ..utils.parse_formula import parse_formula


# How many candidates we surface to the post-trial DFT priority queue.
TOP_K = 50

# Histogram bin count. Fixed [0, 1] range; bin width = 1/HIST_BINS.
HIST_BINS = 10


class _RevStr:
    """Reverse string comparator — used to invert the tie-break order in
    a stdlib heap so that for tied composite scores, the alphabetically
    EARLIER formula wins (i.e. the LATER formula is the one evicted).

    heapq is a min-heap. We want our bounded "top-K by (-score, formula)"
    invariant to mean: heap[0] is the worst entry. Worst means
    (smallest score, OR equal score AND alphabetically latest formula).
    Tuples compare element-wise. Score we negate naturally (we push the
    score itself, not -score, so smallest score = worst). For the
    formula, we want alpha-late to be "smallest" so it sits at heap[0]
    and gets evicted first. Wrapping the formula in _RevStr inverts <
    and >.
    """
    __slots__ = ("s",)
    def __init__(self, s: str):
        self.s = s
    def __lt__(self, other: "_RevStr") -> bool:
        return self.s > other.s
    def __eq__(self, other: object) -> bool:
        return isinstance(other, _RevStr) and self.s == other.s
    def __hash__(self) -> int:  # not used, but defined for completeness
        return hash(self.s)


def _empty_histogram() -> List[int]:
    return [0] * HIST_BINS


def _bump_histogram(hist: List[int], score: float) -> None:
    """Bin a score in [0, 1] into HIST_BINS buckets. Score 1.0 lands in
    the last bucket (HIST_BINS - 1)."""
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
    """Deterministic, wraparound-aware slice of the pool."""
    n = len(pool)
    if n == 0 or slice_size <= 0:
        return []
    start = (slice_index * slice_size) % n
    out = []
    for i in range(slice_size):
        out.append(pool[(start + i) % n])
    return out


def run(payload: Dict, formula_pool: List[str]) -> Dict:
    """Execute one M3 task.

    Args:
        payload: deterministic task descriptor (echoed in the output for
            verification). Required fields: mission, slice_index,
            slice_size, formula_pool_sha256.
        formula_pool: in-memory copy of the pinned pool (already
            sha256-verified by the worker entrypoint).

    Returns:
        dict with top_candidates, score_histogram, summary_stats,
        result_hash, and the echo fields.
    """
    mission_name = payload.get("mission")
    slice_index = int(payload.get("slice_index", 0))
    slice_size = int(payload.get("slice_size", 0))
    pool_sha = payload.get("formula_pool_sha256", "")

    mission = get_mission(mission_name) if mission_name else None
    if mission is None:
        body = {
            "task_type": "heavy_mission_consensus_screen",
            "task_family": "M3",
            "mission": mission_name,
            "slice_index": slice_index,
            "slice_size": slice_size,
            "formula_pool_sha256": pool_sha,
            "version": "phase4b-v1",
            "error": "unknown_mission",
            "top_candidates": [],
            "score_histogram": _empty_histogram(),
            "summary_stats": {
                "count_processed": 0,
                "count_passed_filter": 0,
                "count_rejected": 0,
                "count_pgm_free": 0,
            },
        }
        body["result_hash"] = canonical_sha256(body)
        return body

    formulas = _slice_pool(formula_pool, slice_index, slice_size)

    # Bounded min-heap of size <= TOP_K. Invariant: heap[0] is the
    # WORST entry currently retained — i.e. the one we'd evict next.
    # Sort key: (composite_score ASC, _RevStr(formula) ASC). _RevStr
    # inverts string compare, so on tied score the alpha-LATEST formula
    # is "smallest" and sits at heap[0].
    heap: List[Tuple[float, _RevStr, Dict]] = []
    histogram = _empty_histogram()

    count_processed = 0
    count_passed = 0
    count_rejected = 0
    count_pgm_free = 0

    for formula in formulas:
        count_processed += 1
        counts = parse_formula(formula)
        if not counts:
            count_rejected += 1
            continue
        scored = compute_mission_score_composition_only(formula, counts, mission)
        if not scored.get("passed_filters", False):
            count_rejected += 1
            continue
        count_passed += 1
        composite = scored.get("composite_score", 0.0)
        _bump_histogram(histogram, composite)
        if scored["components"]["pgm_free"] == 1.0:
            count_pgm_free += 1

        record = {
            "formula": scored["formula"],
            "composite_score": composite,
            "components": scored["components"],
            "families": scored["families"],
            "taxonomy": scored.get("taxonomy", "unclassified"),
            "applications": scored.get("applications", []),
        }

        entry = (composite, _RevStr(formula), record)
        if len(heap) < TOP_K:
            heapq.heappush(heap, entry)
        else:
            # heap[0] is the worst current entry. Replace iff the
            # candidate is strictly better.
            if entry > heap[0]:
                heapq.heapreplace(heap, entry)

    # Final canonical ordering: sort by (-composite_score, formula).
    top_candidates = [rec for (_, _, rec) in heap]
    top_candidates.sort(key=lambda r: (-r["composite_score"], r["formula"]))

    body = {
        "task_type": "heavy_mission_consensus_screen",
        "task_family": "M3",
        "mission": mission_name,
        "slice_index": slice_index,
        "slice_size": slice_size,
        "formula_pool_sha256": pool_sha,
        "version": "phase4b-v1",
        "top_candidates": top_candidates,
        "score_histogram": histogram,
        "summary_stats": {
            "count_processed": count_processed,
            "count_passed_filter": count_passed,
            "count_rejected": count_rejected,
            "count_pgm_free": count_pgm_free,
        },
    }
    body["result_hash"] = canonical_sha256(body)
    return body
