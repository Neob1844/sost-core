"""Deduplication engine — detect duplicates across sources.

Phase IV.J: Enhanced dedup with structure-aware decisions.
Conservative: only marks exact when formula+SG match.
New: distinguishes structure_near_match, unique_structure_only, unique_training_candidate.
"""

import logging
from typing import List, Optional

from ..storage.db import MaterialsDB
from .spec import (
    NormalizedCandidate, DedupDecision,
    DEDUP_EXACT, DEDUP_PROBABLE, DEDUP_UNIQUE,
    DEDUP_SAME_FORMULA_DIFF_STRUCT,
    DEDUP_STRUCTURE_NEAR_MATCH,
    DEDUP_UNIQUE_STRUCTURE_ONLY,
    DEDUP_UNIQUE_TRAINING_CANDIDATE,
)

log = logging.getLogger(__name__)


def check_dedup(candidate: NormalizedCandidate, db: MaterialsDB) -> DedupDecision:
    """Check if a candidate is a duplicate of something in the corpus.

    Enhanced decision tree:
    1. formula match + same SG → DEDUP_EXACT
    2. formula match + different SG → DEDUP_SAME_FORMULA_DIFF_STRUCT
    3. no formula match → check if has properties:
       a. has FE or BG → DEDUP_UNIQUE_TRAINING_CANDIDATE
       b. has structure but no props → DEDUP_UNIQUE_STRUCTURE_ONLY
       c. else → DEDUP_UNIQUE
    """
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
                # Check if structure hash matches (near match)
                if (candidate.structure_hash and m.structure_sha256 and
                        candidate.structure_hash == m.structure_sha256):
                    return DedupDecision(
                        candidate_formula=candidate.formula,
                        candidate_source=candidate.source_name,
                        decision=DEDUP_STRUCTURE_NEAR_MATCH,
                        match_id=m.canonical_id,
                        match_formula=m.formula,
                        match_similarity=0.95,
                        reason="Same formula + same structure hash, different SG assignment")

                return DedupDecision(
                    candidate_formula=candidate.formula,
                    candidate_source=candidate.source_name,
                    decision=DEDUP_SAME_FORMULA_DIFF_STRUCT,
                    match_id=m.canonical_id,
                    match_formula=m.formula,
                    match_similarity=0.8,
                    reason=f"Same formula, different/unknown spacegroup")

    # No match — classify by what the candidate brings
    has_props = (candidate.formation_energy is not None or
                 candidate.band_gap is not None)
    has_struct = candidate.has_structure or candidate.spacegroup is not None

    if has_props:
        return DedupDecision(
            candidate_formula=candidate.formula,
            candidate_source=candidate.source_name,
            decision=DEDUP_UNIQUE_TRAINING_CANDIDATE,
            reason="New formula with computed properties — training candidate")
    elif has_struct:
        return DedupDecision(
            candidate_formula=candidate.formula,
            candidate_source=candidate.source_name,
            decision=DEDUP_UNIQUE_STRUCTURE_ONLY,
            reason="New formula with structure but no computed properties")
    else:
        return DedupDecision(
            candidate_formula=candidate.formula,
            candidate_source=candidate.source_name,
            decision=DEDUP_UNIQUE,
            reason="No matching formula in corpus")


def batch_dedup(candidates: List[NormalizedCandidate],
                db: MaterialsDB) -> dict:
    """Dedup a batch of candidates against the corpus.

    Returns summary with counts per decision type, plus first 100 details.
    """
    results = {
        "exact": 0, "probable": 0, "same_formula_diff": 0,
        "structure_near_match": 0,
        "unique": 0, "unique_structure_only": 0, "unique_training_candidate": 0,
        "total": len(candidates),
    }
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
        elif d.decision == DEDUP_STRUCTURE_NEAR_MATCH:
            results["structure_near_match"] += 1
        elif d.decision == DEDUP_UNIQUE_STRUCTURE_ONLY:
            results["unique_structure_only"] += 1
        elif d.decision == DEDUP_UNIQUE_TRAINING_CANDIDATE:
            results["unique_training_candidate"] += 1
        else:
            results["unique"] += 1
    return {"summary": results, "decisions": [d.to_dict() for d in decisions[:100]]}
