"""Novelty and exotic scoring — reproducible material assessment.

Phase III.A: Scores are computed relative to the current ingested corpus only.
They do NOT claim novelty relative to all scientific literature.

Novelty score (0-1):
  0.0 = exact match in corpus
  0.5 = near-duplicate (high similarity to known material)
  1.0 = maximally distant from all known materials

Exotic score (0-1):
  Weighted combination of novelty, element rarity, structural rarity,
  and neighbor sparsity. "Exotic" means "rare/unexplored in corpus",
  NOT "better" or "useful".

Novelty bands:
  known           — exact formula+spacegroup match OR similarity > 0.98
  near_known      — similarity > 0.85
  novel_candidate — similarity <= 0.85
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger(__name__)

# Thresholds
EXACT_MATCH_THRESHOLD = 0.98    # cosine similarity above this = effectively identical
NEAR_KNOWN_THRESHOLD = 0.85     # above this = near-duplicate

# Exotic score weights (must sum to 1.0)
W_NOVELTY = 0.40
W_ELEMENT_RARITY = 0.20
W_STRUCTURE_RARITY = 0.15
W_NEIGHBOR_SPARSITY = 0.25


@dataclass
class NoveltyResult:
    """Full novelty assessment for a material."""
    novelty_score: float = 0.0
    novelty_band: str = "known"          # known | near_known | novel_candidate
    exact_match: bool = False
    exact_match_id: Optional[str] = None
    nearest_neighbor_id: Optional[str] = None
    nearest_neighbor_formula: Optional[str] = None
    nearest_neighbor_similarity: float = 0.0
    reason_codes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = {
            "novelty_score": round(self.novelty_score, 4),
            "novelty_band": self.novelty_band,
            "exact_match": self.exact_match,
            "nearest_neighbor_id": self.nearest_neighbor_id,
            "nearest_neighbor_formula": self.nearest_neighbor_formula,
            "nearest_neighbor_similarity": round(self.nearest_neighbor_similarity, 4),
            "reason_codes": self.reason_codes,
        }
        if self.exact_match_id:
            d["exact_match_id"] = self.exact_match_id
        return d


@dataclass
class ExoticResult:
    """Exotic candidate assessment."""
    exotic_score: float = 0.0
    novelty_score: float = 0.0
    element_rarity: float = 0.0
    structure_rarity: float = 0.0
    neighbor_sparsity: float = 0.0
    exotic_factors: List[str] = field(default_factory=list)
    top_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "exotic_score": round(self.exotic_score, 4),
            "components": {
                "novelty_score": round(self.novelty_score, 4),
                "element_rarity": round(self.element_rarity, 4),
                "structure_rarity": round(self.structure_rarity, 4),
                "neighbor_sparsity": round(self.neighbor_sparsity, 4),
            },
            "weights": {
                "novelty": W_NOVELTY,
                "element_rarity": W_ELEMENT_RARITY,
                "structure_rarity": W_STRUCTURE_RARITY,
                "neighbor_sparsity": W_NEIGHBOR_SPARSITY,
            },
            "exotic_factors": self.exotic_factors,
            "top_reason": self.top_reason,
        }


def compute_novelty(max_similarity: float,
                    exact_formula_match: bool = False,
                    nearest_id: Optional[str] = None,
                    nearest_formula: Optional[str] = None) -> NoveltyResult:
    """Compute novelty result from pre-computed similarity data.

    Args:
        max_similarity: highest cosine similarity to any corpus material
        exact_formula_match: True if formula+spacegroup match exists
        nearest_id: canonical_id of nearest neighbor
        nearest_formula: formula of nearest neighbor
    """
    result = NoveltyResult(
        nearest_neighbor_id=nearest_id,
        nearest_neighbor_formula=nearest_formula,
        nearest_neighbor_similarity=max_similarity,
    )

    # Novelty score = 1 - max_similarity
    result.novelty_score = max(0.0, min(1.0, 1.0 - max_similarity))

    # Exact match check
    if exact_formula_match:
        result.exact_match = True
        result.exact_match_id = nearest_id
        result.novelty_band = "known"
        result.novelty_score = 0.0
        result.reason_codes.append("exact_formula_and_structure_match")
        return result

    # Band classification
    if max_similarity >= EXACT_MATCH_THRESHOLD:
        result.novelty_band = "known"
        result.reason_codes.append("high_composition_similarity")
        if max_similarity > 0.95:
            result.reason_codes.append("high_structure_similarity")
    elif max_similarity >= NEAR_KNOWN_THRESHOLD:
        result.novelty_band = "near_known"
        result.reason_codes.append("high_composition_similarity")
    else:
        result.novelty_band = "novel_candidate"
        if max_similarity < 0.5:
            result.reason_codes.append("low_neighbor_density")
        if max_similarity < 0.3:
            result.reason_codes.append("outlier_candidate")

    return result


def compute_exotic(novelty_score: float,
                   element_rarity: float,
                   structure_rarity: float,
                   neighbor_sparsity: float) -> ExoticResult:
    """Compute exotic score from component scores.

    All inputs should be in [0,1]. Output is weighted combination.

    neighbor_sparsity: how sparse the local neighborhood is.
      Computed as 1 - mean_similarity_to_top_k_neighbors.
    """
    exotic = (W_NOVELTY * novelty_score
              + W_ELEMENT_RARITY * element_rarity
              + W_STRUCTURE_RARITY * structure_rarity
              + W_NEIGHBOR_SPARSITY * neighbor_sparsity)
    exotic = max(0.0, min(1.0, exotic))

    result = ExoticResult(
        exotic_score=exotic,
        novelty_score=novelty_score,
        element_rarity=element_rarity,
        structure_rarity=structure_rarity,
        neighbor_sparsity=neighbor_sparsity,
    )

    # Determine factors and top reason
    components = [
        ("rare_elements", element_rarity),
        ("novel_composition", novelty_score),
        ("sparse_neighborhood", neighbor_sparsity),
        ("rare_structure", structure_rarity),
    ]
    components.sort(key=lambda x: -x[1])

    for name, val in components:
        if val > 0.3:
            result.exotic_factors.append(name)

    result.top_reason = components[0][0] if components else "unknown"

    return result
