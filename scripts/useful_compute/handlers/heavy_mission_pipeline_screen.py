"""
MCOMB — heavy_mission_pipeline_screen

Combined per-formula pipeline (M3 + M4 + M5) per (formula_batch,
mission). Streams a top-50 DFT-priority queue (passed_filters AND
pgm_free AND uncertainty<0.35) via a bounded heap, so RSS is bounded
regardless of slice size.

Phase 4-B determinism contract: same as M3 / M4.
"""

import heapq
from typing import Dict, List, Tuple

from ..utils.canonical_hash import canonical_sha256
from ..utils.mission_profiles import (
    get_mission, compute_mission_score_composition_only,
)
from ..utils.parse_formula import parse_formula
from ..utils.pgm_replacement_tables import pgm_replacement_score_from_counts
from ..utils.uncertainty_tables import compute_uncertainty_from_counts


TOP_K = 50
HIST_BINS = 10

# Uncertainty threshold for the DFT-priority queue. Lower = more
# confident. Mirrors the audit's MCOMB filter (uncertainty<0.35).
UNCERTAINTY_MAX = 0.35


class _RevStr:
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
    mission_name = payload.get("mission")
    slice_index = int(payload.get("slice_index", 0))
    slice_size = int(payload.get("slice_size", 0))
    pool_sha = payload.get("formula_pool_sha256", "")

    mission = get_mission(mission_name) if mission_name else None
    if mission is None:
        body = {
            "task_type": "heavy_mission_pipeline_screen",
            "task_family": "MCOMB",
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
                "count_pgm_free": 0,
                "count_low_uncertainty": 0,
                "count_dft_queue": 0,
            },
        }
        body["result_hash"] = canonical_sha256(body)
        return body

    formulas = _slice_pool(formula_pool, slice_index, slice_size)

    heap: List[Tuple[float, _RevStr, Dict]] = []
    histogram = _empty_histogram()

    count_processed = 0
    count_passed = 0
    count_pgm_free = 0
    count_low_uncertainty = 0
    count_dft_queue = 0

    for formula in formulas:
        count_processed += 1
        counts = parse_formula(formula)
        if not counts:
            continue

        ms = compute_mission_score_composition_only(formula, counts, mission)
        pr = pgm_replacement_score_from_counts(formula, counts)
        un = compute_uncertainty_from_counts(formula, counts)

        passed = ms.get("passed_filters", False)
        composite = ms.get("composite_score", 0.0)
        is_pgm_free = pr.get("pgm_free", False)
        uncertainty = un.get("uncertainty_score", 1.0)

        _bump_histogram(histogram, composite)

        if passed:
            count_passed += 1
        if is_pgm_free:
            count_pgm_free += 1
        if uncertainty < UNCERTAINTY_MAX:
            count_low_uncertainty += 1

        if passed and is_pgm_free and uncertainty < UNCERTAINTY_MAX:
            count_dft_queue += 1
            record = {
                "formula": formula,
                "mission_score": composite,
                "replacement_score": pr.get("replacement_score", 0.0),
                "uncertainty_score": uncertainty,
                "uncertainty_level": un.get("uncertainty_level", "UNKNOWN"),
                "pgm_free": is_pgm_free,
                "families": pr.get("families", []),
                "components": ms.get("components", {}),
            }
            entry = (composite, _RevStr(formula), record)
            if len(heap) < TOP_K:
                heapq.heappush(heap, entry)
            else:
                if entry > heap[0]:
                    heapq.heapreplace(heap, entry)

    top_dft_queue = [rec for (_, _, rec) in heap]
    top_dft_queue.sort(key=lambda r: (-r["mission_score"], r["formula"]))

    body = {
        "task_type": "heavy_mission_pipeline_screen",
        "task_family": "MCOMB",
        "mission": mission_name,
        "slice_index": slice_index,
        "slice_size": slice_size,
        "formula_pool_sha256": pool_sha,
        "version": "phase4b-v1",
        "top_candidates": top_dft_queue,
        "score_histogram": histogram,
        "summary_stats": {
            "count_processed": count_processed,
            "count_passed_filter": count_passed,
            "count_pgm_free": count_pgm_free,
            "count_low_uncertainty": count_low_uncertainty,
            "count_dft_queue": count_dft_queue,
        },
    }
    body["result_hash"] = canonical_sha256(body)
    return body
