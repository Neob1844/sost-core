"""Deduplication engine — detect duplicates across sources.

Phase IV.H: Formula + spacegroup + fingerprint-based dedup.
Conservative: only marks exact when formula+SG match.
"""

import logging
from typing import List, Optional

from ..storage.db import MaterialsDB
from .spec import NormalizedCandidate, DedupDecision, DEDUP_EXACT, DEDUP_PROBABLE, DEDUP_UNIQUE, DEDUP_SAME_FORMULA_DIFF_STRUCT

log = logging.getLogger(__name__)


def check_dedup(candidate: NormalizedCandidate, db: MaterialsDB) -> DedupDecision:
    """Check if a candidate is a duplicate of something in the corpus."""
    # Exact: same formula + same spacegroup
    matches = db.search_materials(formula=candidate.formula, limit=10)
    for m in matches:
        if m.formula == candidate.formula:
            if candidate.spacegroup and m.spacegroup and m.spacegroup == candidate.spacegroup:
                return DedupDecision(
                    candidate_formula=candidate.formula,
                    candidate_source=candidate.source_name,
                    decision=DEDUP_EXACT,
                    match_id=m.canonical_id,
                    match_formula=m.formula,
                    match_similarity=1.0,
                    reason=f"Exact match: formula={candidate.formula}, SG={candidate.spacegroup}")
            else:
                return DedupDecision(
                    candidate_formula=candidate.formula,
                    candidate_source=candidate.source_name,
                    decision=DEDUP_SAME_FORMULA_DIFF_STRUCT,
                    match_id=m.canonical_id,
                    match_formula=m.formula,
                    match_similarity=0.8,
                    reason=f"Same formula, different/unknown spacegroup")

    # No match
    return DedupDecision(
        candidate_formula=candidate.formula,
        candidate_source=candidate.source_name,
        decision=DEDUP_UNIQUE,
        reason="No matching formula in corpus")


def batch_dedup(candidates: List[NormalizedCandidate],
                db: MaterialsDB) -> dict:
    """Dedup a batch of candidates against the corpus."""
    results = {"exact": 0, "probable": 0, "same_formula_diff": 0, "unique": 0, "total": len(candidates)}
    decisions = []
    for c in candidates:
        d = check_dedup(c, db)
        decisions.append(d)
        if d.decision == DEDUP_EXACT:
            results["exact"] += 1
        elif d.decision == DEDUP_PROBABLE:
            results["probable"] += 1
        elif d.decision == DEDUP_SAME_FORMULA_DIFF_STRUCT:
            results["same_formula_diff"] += 1
        else:
            results["unique"] += 1
    return {"summary": results, "decisions": [d.to_dict() for d in decisions[:100]]}
