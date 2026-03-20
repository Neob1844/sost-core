"""Corpus sources specification — registry, normalization, dedup models.

Phase IV.H: Multi-source expansion with dedup foundation.
Does NOT merge blindly. Staging + analysis first.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict

DEDUP_EXACT = "exact_duplicate"
DEDUP_PROBABLE = "probable_duplicate"
DEDUP_SAME_FORMULA_DIFF_STRUCT = "same_formula_different_structure"
DEDUP_STRUCTURE_NEAR_MATCH = "structure_near_match"
DEDUP_UNIQUE = "unique_material"
DEDUP_UNIQUE_STRUCTURE_ONLY = "unique_structure_only"
DEDUP_UNIQUE_TRAINING_CANDIDATE = "unique_training_candidate"


@dataclass
class SourceRegistryEntry:
    name: str = ""
    status: str = "planned"         # active | planned | experimental | staging
    access_mode: str = "api"        # api | bulk | download
    data_type: str = "dft"          # dft | experimental | mixed
    expected_materials: str = ""
    cost: str = "$0"
    ingestion_priority: str = "medium"  # high | medium | low | defer
    has_structure: bool = True
    has_formation_energy: bool = True
    has_band_gap: bool = True
    notes: str = ""
    risks: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NormalizedCandidate:
    """A material from any source, normalized to common schema."""
    source_name: str = ""
    source_id: str = ""
    formula: str = ""
    reduced_formula: str = ""
    elements: List[str] = field(default_factory=list)
    n_elements: int = 0
    spacegroup: Optional[int] = None
    has_structure: bool = False
    structure_hash: Optional[str] = None
    formation_energy: Optional[float] = None
    band_gap: Optional[float] = None
    provenance: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DedupDecision:
    """Dedup result for a candidate vs existing corpus."""
    candidate_formula: str = ""
    candidate_source: str = ""
    decision: str = DEDUP_UNIQUE
    match_id: Optional[str] = None
    match_formula: Optional[str] = None
    match_similarity: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StagingReport:
    """Result of staging analysis for a source."""
    source: str = ""
    total_candidates: int = 0
    normalized_ok: int = 0
    normalization_errors: int = 0
    exact_duplicates: int = 0
    probable_duplicates: int = 0
    unique_new: int = 0
    new_elements: List[str] = field(default_factory=list)
    new_spacegroups: List[int] = field(default_factory=list)
    properties_added: List[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ================================================================
# Source Registry (ground truth)
# ================================================================

SOURCE_REGISTRY = [
    SourceRegistryEntry(
        name="jarvis", status="active", access_mode="bulk", data_type="dft",
        expected_materials="75,993 (integrated)", cost="$0", ingestion_priority="done",
        notes="Fully integrated. 100% structures. All FE + BG available."),
    SourceRegistryEntry(
        name="materials_project", status="planned", access_mode="api", data_type="dft",
        expected_materials="~154,000", cost="$0 (API key)", ingestion_priority="high",
        has_structure=True, has_formation_energy=True, has_band_gap=True,
        notes="Best-curated open DFT database. Requires free API key. High overlap with JARVIS for common materials.",
        risks="Some overlap with JARVIS. API rate limits."),
    SourceRegistryEntry(
        name="cod", status="experimental", access_mode="api", data_type="experimental",
        expected_materials="~530,000", cost="$0", ingestion_priority="medium",
        has_structure=True, has_formation_energy=False, has_band_gap=False,
        notes="Experimental crystal structures. Huge structural diversity. No computed properties. Pilot attempted Phase IV.J.",
        risks="No computed properties — structures only. NOT training-ready. API unreachable in current env."),
    SourceRegistryEntry(
        name="aflow", status="planned", access_mode="api", data_type="dft",
        expected_materials="~3,500,000", cost="$0", ingestion_priority="medium",
        has_structure=True, has_formation_energy=True, has_band_gap=True,
        notes="Autonomous DFT library. Very large. Good for rare element combinations.",
        risks="API can be slow/unreliable. Large volume needs batch processing."),
    SourceRegistryEntry(
        name="oqmd", status="planned", access_mode="api", data_type="dft",
        expected_materials="~1,000,000", cost="$0", ingestion_priority="low",
        has_structure=True, has_formation_energy=True, has_band_gap=False,
        notes="Open Quantum Materials Database. Good formation energy coverage.",
        risks="Significant overlap with JARVIS and MP. No band gap data."),
    SourceRegistryEntry(
        name="nomad", status="planned", access_mode="api", data_type="mixed",
        expected_materials="~12,000,000 entries", cost="$0", ingestion_priority="defer",
        has_structure=True, has_formation_energy=True, has_band_gap=True,
        notes="Massive repository. Heterogeneous formats. Needs significant parsing.",
        risks="Very heterogeneous. Dedup nightmare. Only consider after other sources."),
]
