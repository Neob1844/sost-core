"""Orchestrator data models — coverage, hotspots, proposals.

Phase IV.G: Active learning and corpus expansion planning.
Does NOT retrain or ingest — only analyzes and recommends.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict

# Retraining priorities
PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"
PRIORITY_WAIT = "wait_for_more_evidence"

# Expansion sources
SOURCES = {
    "jarvis": {"status": "integrated", "materials": 75993, "cost": "$0", "difficulty": "done"},
    "cod": {"status": "normalizer_ready", "materials": "~530K", "cost": "$0", "difficulty": "moderate",
            "note": "Crystallography Open Database — structures but fewer computed properties"},
    "aflow": {"status": "normalizer_ready", "materials": "~3.5M", "cost": "$0", "difficulty": "moderate",
              "note": "REST API, may need retry logic for large fetches"},
    "materials_project": {"status": "normalizer_ready", "materials": "~150K", "cost": "$0 (API key)",
                          "difficulty": "easy", "note": "Requires free API key registration"},
    "oqmd": {"status": "not_integrated", "materials": "~1M", "cost": "$0",
             "difficulty": "moderate", "note": "Open Quantum Materials Database"},
    "nomad": {"status": "not_integrated", "materials": "~12M entries", "cost": "$0",
              "difficulty": "hard", "note": "NOMAD repository — heterogeneous formats"},
}


@dataclass
class ErrorHotspot:
    """A region where the model performs poorly."""
    target: str = ""
    bucket_type: str = ""   # element_count | value_range | element_family
    bucket_label: str = ""
    mae: float = 0.0
    sample_count: int = 0
    confidence_band: str = "unknown"
    severity: str = PRIORITY_MEDIUM
    recommendation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CoverageSummary:
    """Chemical space coverage analysis."""
    total_materials: int = 0
    total_elements_seen: int = 0
    total_spacegroups_seen: int = 0
    element_counts: Dict[str, int] = field(default_factory=dict)
    spacegroup_counts: Dict[int, int] = field(default_factory=dict)
    n_element_distribution: Dict[int, int] = field(default_factory=dict)
    rare_elements: List[str] = field(default_factory=list)
    dense_regions: List[str] = field(default_factory=list)
    sparse_regions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["spacegroup_counts"] = {str(k): v for k, v in self.spacegroup_counts.items()}
        return d


@dataclass
class RetrainingProposal:
    """A reasoned proposal for future model retraining."""
    proposal_id: str = ""
    target: str = ""
    priority: str = PRIORITY_MEDIUM
    reason: str = ""
    expected_benefit: str = ""
    required_data: str = ""
    recommended_rung: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CorpusExpansionItem:
    """A source for potential corpus expansion."""
    source: str = ""
    status: str = ""
    estimated_materials: str = ""
    cost: str = "$0"
    difficulty: str = ""
    priority: str = PRIORITY_MEDIUM
    value_for_exotic: str = ""
    dedup_risk: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
