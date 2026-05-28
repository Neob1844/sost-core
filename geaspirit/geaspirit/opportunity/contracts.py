"""
Data contracts for the opportunity intelligence pipeline.

Every connector returns a ConnectorResult containing a tuple of
Evidence items. The orchestrator combines all Evidence into one
OpportunityScorecard with a score, a thesis string and a next-step
recommendation.

Stdlib-only (dataclasses + typing). No pydantic / no schema lib.
JSON round-trip lives in canonical.py.

Language guardrail
------------------
Public-facing strings on opportunity scorecards MUST NOT claim
confirmed resources or guarantee returns. Every string field that
ends up in JSON output (thesis / next_step / notes) is validated at
construction time against FORBIDDEN_PHRASES. A forbidden phrase
raises ValueError so the code can never silently ship misleading
copy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Tuple


# --- Editorial guardrail -------------------------------------------------

FORBIDDEN_PHRASES: Tuple[str, ...] = (
    "confirmed resource",
    "confirmed reserves",
    "guaranteed recovery",
    "guaranteed return",
    "guaranteed profit",
    "guaranteed yield",
    "proven reserves",
    "reserves estimate",
    "resource estimate",
    "jorc-compliant",
    "ni 43-101 compliant",
    "will produce",
    "will recover",
)

# Vocabulary the orchestrator should prefer when generating thesis /
# next_step strings. Kept as a hint, not enforced.
ALLOWED_VOCAB: Tuple[str, ...] = (
    "candidate",
    "opportunity",
    "due diligence",
    "historical occurrence",
    "potential",
    "subject to verification",
    "merits desk validation",
)


def _check_language(text: str, where: str) -> str:
    """Raise ValueError if `text` contains any forbidden phrase."""
    if text is None or text == "":
        return text
    low = text.lower()
    for bad in FORBIDDEN_PHRASES:
        if bad in low:
            raise ValueError(
                f"{where}: forbidden phrase {bad!r} detected. "
                f"Opportunity scorecards must not claim confirmed resources "
                f"or guaranteed returns. Use 'candidate', "
                f"'due diligence target' or 'historical occurrence' instead."
            )
    return text


# --- Core dataclasses ----------------------------------------------------

@dataclass(frozen=True)
class AOI:
    """A geographic area of interest. Sprint 1 form is center + radius.
    Future versions may add an explicit polygon."""
    name: str
    lat: float                  # WGS84 degrees
    lon: float                  # WGS84 degrees
    radius_km: float            # search radius
    country: str = ""           # ISO 3166-1 alpha-2 (free-form fallback)
    metals_of_interest: Tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def __post_init__(self):
        if not (-90.0 <= self.lat <= 90.0):
            raise ValueError(f"AOI[{self.name}]: lat out of range {self.lat}")
        if not (-180.0 <= self.lon <= 180.0):
            raise ValueError(f"AOI[{self.name}]: lon out of range {self.lon}")
        if self.radius_km <= 0:
            raise ValueError(
                f"AOI[{self.name}]: radius_km must be > 0 (got {self.radius_km})"
            )
        _check_language(self.notes, f"AOI[{self.name}].notes")


@dataclass(frozen=True)
class Evidence:
    """One observation contributed by one connector to one AOI.

    All fields must round-trip cleanly to JSON. `data` may hold
    connector-specific structured payload; keep it small + canonical.
    """
    tag: str                    # short canonical id, e.g. "nearby_road_access"
    source: str                 # human-readable origin, e.g. "OpenStreetMap (Overpass)"
    fetched_at: str             # ISO-8601 UTC, e.g. "2026-05-28T11:00:00Z"
    confidence: float           # 0.0 - 1.0
    license: str                # short id, e.g. "ODbL-1.0"
    notes: str = ""
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"Evidence[{self.tag}]: confidence out of range {self.confidence}"
            )
        _check_language(self.notes, f"Evidence[{self.tag}].notes")


@dataclass(frozen=True)
class ConnectorResult:
    """Output of one connector for one AOI."""
    connector: str              # e.g. "osm_logistics"
    status: str                 # "ok" | "cache" | "skipped" | "error"
    evidence: Tuple[Evidence, ...] = field(default_factory=tuple)
    fetched_at: str = ""
    error_message: str = ""

    def __post_init__(self):
        if self.status not in {"ok", "cache", "skipped", "error"}:
            raise ValueError(
                f"ConnectorResult[{self.connector}]: status {self.status!r} invalid"
            )


@dataclass(frozen=True)
class SubScores:
    """Decomposed scoring so one number doesn't hide nuance.

    All fields are 0..100. Higher is more favourable. The orchestrator
    keeps these separate AND surfaces them in the JSON so an AOI can
    be geologically interesting but commercially blocked by
    environmental constraints (or vice versa).
    """
    geological:    int   # mineral evidence, historic occurrence, tailings as legacy signal
    logistics:     int   # road / rail / port / airport proximity
    environmental: int   # 100 = no protected-area overlap; 0 = AOI center inside Natura 2000
    legal:         int   # title-chain clarity (Sprint 1 fixed at 50, MITECO connector lands in S2)
    commercial:    int   # final blended score — also what `OpportunityScorecard.score` mirrors

    def __post_init__(self):
        for name in ("geological", "logistics", "environmental", "legal", "commercial"):
            v = getattr(self, name)
            if not (0 <= v <= 100):
                raise ValueError(f"SubScores.{name} out of range: {v}")


# Allowed values for OpportunityScorecard.opportunity_class.
# extraction_led:   classic mining angle — env clear, title clear, geology + logistics OK
# remediation_led:  env risk HIGH but legacy mineralisation exists; product is
#                   "clean up + recover", not "extract fresh"
# reactivation_led: env clear AND a mining right exists but is expired / cancelled /
#                   verifiable as inactive — angle is re-permit + due diligence on
#                   the lapsed title chain, not a greenfield application
# partnership_led:  env clear but the AOI is covered by a CURRENT third-party title —
#                   the only commercial path is a deal with the existing holder
#                   (option, JV, sub-licence). No solo entry possible.
# mixed:            moderate constraint, multiple angles possible
# blocked:          env risk HIGH and no mineral case, OR legal conflict so severe
#                   no commercial entry is viable
OPPORTUNITY_CLASSES = (
    "extraction_led",
    "remediation_led",
    "reactivation_led",
    "partnership_led",
    "mixed",
    "blocked",
)


@dataclass(frozen=True)
class OpportunityScorecard:
    """Final product: ranked opportunity for one AOI.

    The structure is deliberately flat and explicit so a SHA-256 of the
    canonical JSON is reproducible across machines. `class_grade` is a
    coarse bucket — humans read it faster than the raw score.

    `score` mirrors `subscores.commercial` for backwards-compat and
    for "show me one number" UIs. The full picture lives in
    `subscores` + `opportunity_class`.
    """
    aoi: AOI
    score: int                  # 0 - 100 (mirror of subscores.commercial)
    class_grade: str            # "A" | "B+" | "B" | "C" | "F"
    opportunity_class: str      # one of OPPORTUNITY_CLASSES
    subscores: SubScores
    thesis: str                 # one-paragraph human summary
    next_step: str              # concrete recommended action
    evidence_tags: Tuple[str, ...] = field(default_factory=tuple)
    connector_results: Tuple[ConnectorResult, ...] = field(default_factory=tuple)
    generated_at: str = ""
    schema_version: str = "opportunity_scorecard.v1"
    not_a_resource_estimate: bool = True

    def __post_init__(self):
        if not (0 <= self.score <= 100):
            raise ValueError(
                f"Scorecard[{self.aoi.name}]: score out of range {self.score}"
            )
        if self.class_grade not in {"A", "B+", "B", "C", "F"}:
            raise ValueError(
                f"Scorecard[{self.aoi.name}]: class_grade {self.class_grade!r} invalid"
            )
        if self.opportunity_class not in OPPORTUNITY_CLASSES:
            raise ValueError(
                f"Scorecard[{self.aoi.name}]: opportunity_class "
                f"{self.opportunity_class!r} invalid (one of {OPPORTUNITY_CLASSES})"
            )
        if self.score != self.subscores.commercial:
            raise ValueError(
                f"Scorecard[{self.aoi.name}]: score ({self.score}) must equal "
                f"subscores.commercial ({self.subscores.commercial})"
            )
        _check_language(self.thesis, f"Scorecard[{self.aoi.name}].thesis")
        _check_language(self.next_step, f"Scorecard[{self.aoi.name}].next_step")
