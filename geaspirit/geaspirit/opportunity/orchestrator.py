"""
Opportunity orchestrator — runs connectors, decomposes the result
into five sub-scores, classifies the opportunity, blends a final
commercial score.

Why decompose
-------------
One number hides nuance. An AOI can be geologically strong AND
commercially blocked by permitting risk — those are two different
stories that need two different numbers. The Sprint 1.1 schema
returns BOTH the per-axis sub-scores AND a final blended commercial
score so the human reader (and the buyer of the report) can see
where the friction is.

Sub-score formulas (0-100 each, higher = more favourable)
---------------------------------------------------------
geological:
    base 30 if any metal_of_interest declared
    +15 if at least one strategic metal (W/Sn/Cu/Li/Co/Ni/REE/Ga/Ge/Ta)
    +25 if nearby_tailings_facility (TSF density as legacy-mineralisation proxy)
    +20 if biggest TSF volume > 10M m³,  else +10 if > 1M m³
    clamp 0-100

logistics:
    base 50
    road  < 5km +20 · <15km +12 · <30km +6
    rail  <10km +15 · <30km +9  · <60km +4
    port  <30km +10 · <80km +6
    air   <30km +5
    clamp 0-100

environmental:
    environmental_clear           → 100
    no env data (skipped/error)   → 50   (unknown, NOT good)
    environmental_risk_medium     → 60   (radius touches Natura 2000)
    environmental_risk_high       → 25   (AOI center inside protected polygon)

legal (Sprint 2.1: MITECO Catastro Minero connector now feeds this):
    no MITECO data (skipped/error)  → 50   (unknown ≠ good)
    title_clear                     → 80   (single owner, contactable)
    title_cancelled                 → 75   (clearly free-and-clear, low title risk)
    title_expired                   → 72   (reactivation angle, due diligence on lapse)
    title_active_or_pending         → 70   (right exists, identifiable counterparty)
    title_active_by_third_party     → 55   (partnership angle, deal required)
    title_pending_request           → 55   (in-flight application by third party)
    title_unknown_in_catastro       → 45   (records consulted, none found nearby —
                                              treated cautiously, not as positive)
    title_conflicting               → 30   (litigation / overlap / disputed)
    Multiple hits → most-blocking status dominates (priority order in
    connectors/miteco_catastro.py::_STATUS_PRIORITY). Never average,
    never optimistic — we underscore rather than overscore.

commercial: blended final score the customer cares about.
    raw = 0.40·geological + 0.25·logistics + 0.25·environmental + 0.10·legal
    if environmental <= 30:  raw -= 25   (hard penalty for high env risk)
    if legal         <= 35:  raw -= 10   (hard penalty for legal block / conflict)
    if data_uncertainty:     raw -= 10   (fewer than 3 connectors ok)
    clamp 0-100

opportunity_class
-----------------
    env <= 30 AND geological <  40                      → "blocked"
        env risk too high, no clear mineral case worth the fight.
    env <= 30 AND geological >= 40                      → "remediation_led"
        legacy mineralisation IS there, but the angle is clean-up +
        secondary recovery, not fresh extraction.
    legal_tag == "title_conflicting"                    → "blocked"
        legal dispute alone is enough to park the AOI commercially.
    legal_tag == "title_active_by_third_party"
        AND geological >= 40                            → "partnership_led"
        the only commercial path is a deal with the existing holder.
    legal_tag in {title_expired, title_cancelled}
        AND env > 30 AND geological >= 40               → "reactivation_led"
        re-permit + due diligence on the lapsed title is the angle.
    env in (30, 65] AND geological >= 50                → "mixed"
        manageable constraint, mineral case strong enough to push.
    env > 65                                            → "extraction_led"
        classic mining angle, no permitting drama from this radius.

Language guardrail (contracts.py) still applies to thesis +
next_step. Generated copy never claims confirmed resources, JORC
compliance or guarantees.
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable, List, Optional, Tuple

from .contracts import (
    AOI, ConnectorResult, Evidence, OpportunityScorecard, SubScores,
)
from .connectors import (
    osm_logistics, env_constraints, tailings_portal, miteco_catastro,
)


_STRATEGIC_METALS = {
    "w", "tungsten",
    "sn", "tin",
    "cu", "copper",
    "li", "lithium",
    "co", "cobalt",
    "ni", "nickel",
    "ree", "rare earth", "rare earths",
    "ga", "gallium",
    "ge", "germanium",
    "ta", "tantalum",
}

DefaultConnectors: Tuple[Callable[[AOI], ConnectorResult], ...] = (
    osm_logistics.query,
    env_constraints.query,
    tailings_portal.query,
    miteco_catastro.query,
)


# Title-status Evidence tags → legal subscore band.
# See orchestrator module docstring for the full rationale.
_LEGAL_TAG_TO_SCORE: dict = {
    "title_clear":                  80,
    "title_cancelled":              75,
    "title_expired":                72,
    "title_active_or_pending":      70,
    "title_active_by_third_party":  55,
    "title_pending_request":        55,
    "title_unknown_in_catastro":    45,
    "title_conflicting":            30,
}

# Subset that DOWNGRADES opportunity to "blocked" purely on legal grounds.
_LEGAL_BLOCKING_TAGS = ("title_conflicting",)

# Tags that flip classification when env is not the dominant constraint.
_PARTNERSHIP_TAGS    = ("title_active_by_third_party", "title_active_or_pending")
_REACTIVATION_TAGS   = ("title_expired", "title_cancelled")

# Priority order for picking the dominant legal tag when multiple are
# present. Higher in the list = more commercially blocking.
_LEGAL_TAG_PRIORITY: Tuple[str, ...] = (
    "title_conflicting",
    "title_active_by_third_party",
    "title_active_or_pending",
    "title_pending_request",
    "title_expired",
    "title_cancelled",
    "title_clear",
    "title_unknown_in_catastro",
)


# ─── helpers ──────────────────────────────────────────────────────

def _ev_lookup(evidence: List[Evidence], tag: str, key: str) -> Optional[float]:
    for e in evidence:
        if e.tag == tag and isinstance(e.data.get(key), (int, float)):
            return float(e.data[key])
    return None


def _has_tag(evidence: List[Evidence], tag: str) -> bool:
    return any(e.tag == tag for e in evidence)


def _tag_count(tags: Tuple[str, ...]) -> dict:
    out = {}
    for t in tags:
        out[t] = out.get(t, 0) + 1
    return out


# ─── sub-scores ───────────────────────────────────────────────────

def _geological_subscore(aoi: AOI, evidence: List[Evidence]) -> int:
    s = 0
    if aoi.metals_of_interest:
        s += 30
    if any(m.strip().lower() in _STRATEGIC_METALS for m in aoi.metals_of_interest):
        s += 15
    if _has_tag(evidence, "nearby_tailings_facility"):
        s += 25
        biggest = 0.0
        for e in evidence:
            if e.tag == "nearby_tailings_facility":
                biggest = float(e.data.get("largest_volume_m3", 0) or 0)
                break
        if   biggest >= 1e7: s += 20
        elif biggest >= 1e6: s += 10
    return max(0, min(100, s))


def _logistics_subscore(evidence: List[Evidence]) -> int:
    s = 50
    road = _ev_lookup(evidence, "nearby_road_access", "distance_km")
    rail = _ev_lookup(evidence, "nearby_railway",     "distance_km")
    port = _ev_lookup(evidence, "nearby_port",        "distance_km")
    air  = _ev_lookup(evidence, "nearby_airport",     "distance_km")
    if road is not None:
        if   road <  5: s += 20
        elif road < 15: s += 12
        elif road < 30: s += 6
    if rail is not None:
        if   rail < 10: s += 15
        elif rail < 30: s += 9
        elif rail < 60: s += 4
    if port is not None:
        if   port < 30: s += 10
        elif port < 80: s += 6
    if air is not None and air < 30:
        s += 5
    return max(0, min(100, s))


def _environmental_subscore(
    evidence: List[Evidence], env_status: str
) -> int:
    if _has_tag(evidence, "environmental_risk_high"):
        return 25
    if _has_tag(evidence, "environmental_risk_medium"):
        return 60
    if _has_tag(evidence, "environmental_clear"):
        return 100
    # No env data at all → unknown ≠ good. Neutral 50 with a flag in tags.
    return 50


def _dominant_legal_tag(evidence: List[Evidence]) -> Optional[str]:
    """Pick the single most-blocking title tag across all evidence.
    Returns None if no legal evidence was emitted (MITECO skipped /
    error / no titles in radius)."""
    present = {e.tag for e in evidence if e.tag in _LEGAL_TAG_TO_SCORE}
    if not present:
        return None
    for tag in _LEGAL_TAG_PRIORITY:
        if tag in present:
            return tag
    return None


def _legal_subscore(evidence: List[Evidence]) -> int:
    """Map the dominant title tag to its band. No legal data → 50
    (unknown ≠ good — same convention as environmental)."""
    tag = _dominant_legal_tag(evidence)
    if tag is None:
        return 50
    return _LEGAL_TAG_TO_SCORE[tag]


# ─── commercial blend + classification ─────────────────────────────

def _commercial_blend(
    geo: int, log: int, env: int, leg: int,
    results: Tuple[ConnectorResult, ...],
) -> int:
    raw = 0.40 * geo + 0.25 * log + 0.25 * env + 0.10 * leg
    if env <= 30:
        raw -= 25
    if leg <= 35:
        raw -= 10
    ok_count = sum(1 for r in results if r.status in ("ok", "cache"))
    if ok_count < 3:
        raw -= 10
    return max(0, min(100, int(round(raw))))


def _classify(env: int, geo: int, legal_tag: Optional[str]) -> str:
    # Env-driven blocks come first — env is the hardest constraint.
    if env <= 30 and geo < 40:
        return "blocked"
    if env <= 30 and geo >= 40:
        return "remediation_led"
    # Legal block (litigation / overlap) is also enough to park the AOI.
    if legal_tag in _LEGAL_BLOCKING_TAGS:
        return "blocked"
    # Legal-driven classes (only when env is not the dominant signal).
    if legal_tag in _PARTNERSHIP_TAGS and geo >= 40:
        return "partnership_led"
    if legal_tag in _REACTIVATION_TAGS and geo >= 40:
        return "reactivation_led"
    # Env-driven classes (legacy Sprint 1.1 paths).
    if 30 < env <= 65 and geo >= 50:
        return "mixed"
    if env > 65:
        return "extraction_led"
    return "mixed"   # fallback for edge combinations


def _grade_from_commercial(s: int) -> str:
    if s >= 80: return "A"
    if s >= 65: return "B+"
    if s >= 50: return "B"
    if s >= 30: return "C"
    return "F"


# ─── narrative ────────────────────────────────────────────────────

def _build_thesis(
    aoi: AOI,
    sub: SubScores,
    opp_class: str,
    grade: str,
    tags: Tuple[str, ...],
    legal_tag: Optional[str] = None,
) -> str:
    metals = ", ".join(aoi.metals_of_interest) or "unspecified metals"
    head = (f"{aoi.name} is a {grade} candidate for {metals} "
            f"(classification: {opp_class.replace('_', '-')}).")
    parts = [head]

    if opp_class == "blocked":
        if legal_tag in _LEGAL_BLOCKING_TAGS:
            parts.append("Title-chain is in dispute / litigation / overlap. "
                         "No commercial entry is recommended until the legal "
                         "conflict is resolved by the relevant authority.")
        else:
            parts.append("Environmental constraints are HIGH and the "
                         "geological case is weak — opening this AOI "
                         "commercially is not recommended without a stronger "
                         "mineral signal.")
    elif opp_class == "remediation_led":
        parts.append("Environmental constraints are HIGH but legacy "
                     "mineralisation is documented. Frame the angle as "
                     "remediation + secondary recovery, NOT fresh extraction.")
    elif opp_class == "mixed":
        parts.append("Environmental constraints are present but manageable; "
                     "the geological case justifies pushing forward with care.")
    elif opp_class == "extraction_led":
        parts.append("No protected-area overlap detected in the search "
                     "radius; the mineral case can be pursued on standard "
                     "extraction terms (still subject to title check).")
    elif opp_class == "partnership_led":
        parts.append("A CURRENT third-party mining right covers the AOI; "
                     "solo entry is not viable. The only commercial path "
                     "is a deal with the existing holder (option, JV, "
                     "sub-licence) — subject to operator-led negotiation.")
    elif opp_class == "reactivation_led":
        parts.append("A lapsed (expired/cancelled) mining right covers the "
                     "AOI and the environment is workable; the angle is "
                     "re-permit + due diligence on the lapsed title chain, "
                     "NOT a fresh greenfield application.")

    if _has_tag_list(tags, "nearby_tailings_facility"):
        parts.append("Historical tailings storage facilities are documented "
                     "within the search radius (subject to verification).")

    sub_line = (f"Sub-scores — geological {sub.geological}, "
                f"logistics {sub.logistics}, environmental {sub.environmental}, "
                f"legal {sub.legal}.")
    parts.append(sub_line)
    parts.append("Merits desk validation; legal title check and on-site "
                 "sampling are required before any further action.")
    return " ".join(parts)


def _build_next_step(tags: Tuple[str, ...], opp_class: str,
                     legal_tag: Optional[str] = None) -> str:
    steps = [
        "Run desk validation: cross-check published historical occurrence "
        "with national mineral catastro / geological survey."
    ]
    if opp_class in ("remediation_led", "mixed") or (
        opp_class == "blocked" and legal_tag not in _LEGAL_BLOCKING_TAGS
    ):
        steps.append("Obtain environmental authority opinion before any "
                     "physical access; document the protected-area code(s) "
                     "the AOI overlaps.")
    if opp_class == "remediation_led":
        steps.append("Re-frame the commercial angle: pitch as "
                     "remediation contract + secondary metal recovery, not "
                     "as a fresh mining venture.")
    if opp_class == "blocked":
        if legal_tag in _LEGAL_BLOCKING_TAGS:
            steps.append("Wait for the legal conflict to clear in the "
                         "MITECO Catastro Minero record before any further "
                         "action; track the expediente for resolution.")
        else:
            steps.append("Park the AOI; revisit only if new mineral evidence "
                         "or a permitting change appears.")
    if opp_class == "partnership_led":
        steps.append("Verify the holder identity and standing in the "
                     "MITECO Catastro Minero record before any approach. "
                     "Outreach must be operator-led and respect the "
                     "no-automated-contact rule.")
    if opp_class == "reactivation_led":
        steps.append("Build a re-permit file: pull the lapsed-title "
                     "history from MITECO, confirm there is no successor "
                     "claim, scope environmental clearances anew.")
    steps.append("Identify current concession holder (if any) and verify "
                 "title status.")
    if _has_tag_list(tags, "nearby_tailings_facility"):
        steps.append("Request operator-tier access to the GRID-Arendal full "
                     "tailings record for the identified facilities.")
    if opp_class != "blocked":
        steps.append("If desk passes: scope a first sampling campaign "
                     "with an accredited lab (e.g. SGS / ALS / Bureau Veritas).")
    return " ".join(steps)


def _has_tag_list(tags: Tuple[str, ...], target: str) -> bool:
    return target in tags


# ─── public API ───────────────────────────────────────────────────

def score_opportunity(
    aoi: AOI,
    connectors: Tuple[Callable[[AOI], ConnectorResult], ...] = DefaultConnectors,
) -> OpportunityScorecard:
    """Run every connector, combine evidence, return a v1 scorecard."""
    results: List[ConnectorResult] = [c(aoi) for c in connectors]
    all_ev: List[Evidence] = []
    for r in results:
        all_ev.extend(r.evidence)
    tags = tuple(e.tag for e in all_ev)
    env_status = next(
        (r.status for r in results if r.connector == "env_constraints"),
        "missing",
    )

    geo = _geological_subscore(aoi, all_ev)
    log = _logistics_subscore(all_ev)
    env = _environmental_subscore(all_ev, env_status)
    leg = _legal_subscore(all_ev)
    legal_tag = _dominant_legal_tag(all_ev)
    com = _commercial_blend(geo, log, env, leg, tuple(results))

    sub = SubScores(
        geological=geo,
        logistics=log,
        environmental=env,
        legal=leg,
        commercial=com,
    )
    opp_class = _classify(env, geo, legal_tag)
    grade = _grade_from_commercial(com)

    generated_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return OpportunityScorecard(
        aoi=aoi,
        score=com,                       # mirror of subscores.commercial
        class_grade=grade,
        opportunity_class=opp_class,
        subscores=sub,
        thesis=_build_thesis(aoi, sub, opp_class, grade, tags, legal_tag),
        next_step=_build_next_step(tags, opp_class, legal_tag),
        evidence_tags=tags,
        connector_results=tuple(results),
        generated_at=generated_at,
    )
