"""
GeaSpirit opportunity intelligence — Sprint 1 scaffold.

Isolated subpackage that ranks abandoned / undervalued mineral assets
(tailings, dumps, lapsed concessions, e-waste) for due-diligence
prioritisation. Output is a deterministic JSON OpportunityScorecard
that can be SHA-256 anchored on chain via the Protocol Registry.

NOT a resource estimate. NOT a financial promise. The whole package
exists to surface candidates that merit desk validation, not to
confirm reserves.

Sister to (and deliberately separate from) the existing GeaSpirit
prospectivity stack in geaspirit/geaspirit/{dataset,indices,model,
spectral,ee_download}.py — those modules are NOT modified by this
subpackage.
"""

from .contracts import (
    AOI,
    Evidence,
    ConnectorResult,
    SubScores,
    OpportunityScorecard,
    FORBIDDEN_PHRASES,
    OPPORTUNITY_CLASSES,
)
from .canonical import canonical_json, sha256_of_canonical
from .orchestrator import score_opportunity

__all__ = [
    "AOI",
    "Evidence",
    "ConnectorResult",
    "SubScores",
    "OpportunityScorecard",
    "FORBIDDEN_PHRASES",
    "OPPORTUNITY_CLASSES",
    "canonical_json",
    "sha256_of_canonical",
    "score_opportunity",
]

__version__ = "0.3.0"
