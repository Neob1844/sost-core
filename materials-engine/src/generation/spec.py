"""Generation specification — configurable candidate generation parameters.

Phase III.D: Defines what candidates to generate, how many, and with what filters.
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List

log = logging.getLogger(__name__)

GENERATION_STRATEGIES = [
    "element_substitution",
    "stoichiometry_perturbation",
    "prototype_remix",
    "mixed",  # combines all strategies
]

GENERATION_PRESETS = [
    "exotic_search",
    "stable_search",
    "band_gap_search",
    "tp_sensitive_search",
]


class GenerationValidationError(ValueError):
    pass


@dataclass
class GenerationSpec:
    """Full specification for a candidate generation run."""
    strategy: str = "mixed"
    max_parents: int = 100
    max_candidates: int = 500
    random_seed: int = 42

    # Element filters
    allowed_elements: Optional[List[str]] = None
    excluded_elements: Optional[List[str]] = None
    max_n_elements: int = 5

    # Structure filter
    require_spacegroup: bool = False

    # Post-generation novelty/viability filters
    novelty_threshold: float = 0.0     # min novelty to keep
    formation_energy_max: Optional[float] = None
    band_gap_min: Optional[float] = None
    band_gap_max: Optional[float] = None

    # T/P context
    temperature_K: Optional[float] = None
    pressure_GPa: Optional[float] = None

    # Corpus sampling
    pool_limit: int = 5000

    def validate(self) -> None:
        if self.strategy not in GENERATION_STRATEGIES:
            raise GenerationValidationError(
                f"Unknown strategy '{self.strategy}'. Valid: {GENERATION_STRATEGIES}")
        if self.max_parents < 1:
            raise GenerationValidationError("max_parents must be >= 1")
        if self.max_candidates < 1:
            raise GenerationValidationError("max_candidates must be >= 1")
        if self.max_n_elements < 1 or self.max_n_elements > 10:
            raise GenerationValidationError("max_n_elements must be 1-10")

    def run_id(self) -> str:
        key = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "GenerationSpec":
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in d.items() if k in valid})


# ================================================================
# Presets
# ================================================================

def exotic_search() -> GenerationSpec:
    return GenerationSpec(
        strategy="mixed", max_parents=200, max_candidates=1000,
        novelty_threshold=0.0, max_n_elements=5, random_seed=42)


def stable_search() -> GenerationSpec:
    return GenerationSpec(
        strategy="element_substitution", max_parents=100, max_candidates=500,
        formation_energy_max=0.5, max_n_elements=4, random_seed=42)


def band_gap_search() -> GenerationSpec:
    return GenerationSpec(
        strategy="mixed", max_parents=100, max_candidates=500,
        band_gap_min=0.5, band_gap_max=3.0, max_n_elements=4, random_seed=42)


def tp_sensitive_search() -> GenerationSpec:
    return GenerationSpec(
        strategy="element_substitution", max_parents=100, max_candidates=500,
        temperature_K=1200.0, pressure_GPa=10.0, max_n_elements=4, random_seed=42)


ALL_GENERATION_PRESETS = {
    "exotic_search": exotic_search,
    "stable_search": stable_search,
    "band_gap_search": band_gap_search,
    "tp_sensitive_search": tp_sensitive_search,
}
