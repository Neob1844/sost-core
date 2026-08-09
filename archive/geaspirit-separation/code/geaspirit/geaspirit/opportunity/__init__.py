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
from .canonical import canonical_json, sha256_of_canonical, pretty_json
from .orchestrator import score_opportunity, DefaultConnectors
from .campaign import (
    parse_campaign_file,
    run_campaign,
    run_and_export,
    export_campaign,
    ranking_rows,
    CAMPAIGN_SCHEMA_VERSION,
)
from .registry import (
    build_scorecard_capsule,
    build_campaign_capsule,
    build_capsule,
    suggested_sost_cli_command,
    SCORECARD_CAPSULE_PREFIX,
    CAMPAIGN_CAPSULE_PREFIX,
)

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
    "pretty_json",
    "score_opportunity",
    "DefaultConnectors",
    "parse_campaign_file",
    "run_campaign",
    "run_and_export",
    "export_campaign",
    "ranking_rows",
    "CAMPAIGN_SCHEMA_VERSION",
    "build_scorecard_capsule",
    "build_campaign_capsule",
    "build_capsule",
    "suggested_sost_cli_command",
    "SCORECARD_CAPSULE_PREFIX",
    "CAMPAIGN_CAPSULE_PREFIX",
]

__version__ = "0.4.0"
