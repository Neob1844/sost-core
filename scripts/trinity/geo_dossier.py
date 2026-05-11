#!/usr/bin/env python3
"""Trinity / Geo Discovery — Geo dossier builder v0.1 (real SOST AI).

Reads a ``TRINITY_GEO_SCORECARD_<campaign>.json`` and runs each AOI
through the **real SOST AI Council** from
``materials-engine-private/src/multi_ai_review`` (free-tier members
only: ``ValidatorMember``, ``LocalKnowledgeMember``, ``MockAIMember``).
Emits ``TRINITY_GEO_DOSSIER_<campaign>.json`` and a Markdown sidecar.

Mirrors the Materials Track v0.2 dossier pattern but builds
``Hypothesis(project="geaspirit", type="mineral_target")`` per AOI so
the council's reasoning context is geological, not chemical.

Honesty disclaimers (in the rendered Markdown):
- "autonomous AOI proposal"
- "remote proxy evidence only"
- "no field validation"
- "no drilling evidence"
- "no confirmed mineralization"
- "not a mineral reserve claim"
- "requires geological review before any public claim"

Council resolution
------------------
- By default the builder imports
  ``multi_ai_review.ai_council.AICouncil`` from
  ``$TRINITY_MATERIALS_ENGINE_PATH`` (or
  ``~/SOST/materials-engine-private``). Fails loudly if missing.
- ``--allow-local-mock`` is the explicit escape hatch (deterministic
  three-rule mock, retained for offline use and tests). Default is
  the real council.

Invariants
----------
- DRY-RUN. No network, no RPC, no subprocess, no wallet, no broadcast.
- Canonical JSON, byte-identical given the same pinned time + inputs.
- Cross-machine reproducibility: ``source.scorecard_sha256`` +
  ``scorecard_basename`` instead of an absolute host path. The engine
  path is never stored in the JSON.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCHEMA = "trinity-geo-dossier/v0.1"
_SCORECARD_SCHEMA = "trinity-geo-scorecard/v0.1"
_TRACK = "geaspirit"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")

# Mock thresholds for the --allow-local-mock fallback.
_VALIDATOR_SCORE_ACCEPT = 0.65
_VALIDATOR_SCORE_REJECT = 0.30
_EXPERT_MAX_OPEN_QUESTIONS = 3

_VERDICT_TO_DECISION = {
    "agree": "accept",
    "disagree": "reject",
    "contradicted": "reject",
    "abstain": "abstain",
    "insufficient": "hold",
}

_COUNCIL_DECISION_TO_DOSSIER = {
    "accept": "accept",
    "hold": "hold",
    "reject": "reject",
    "contradicted": "reject",
}


# ---------------------------------------------------------------------------
# Real SOST AI Council import bootstrap
# ---------------------------------------------------------------------------


def _import_real_council() -> Dict[str, Any]:
    me_env = os.environ.get("TRINITY_MATERIALS_ENGINE_PATH")
    candidates: List[Path] = []
    if me_env:
        candidates.append(Path(me_env))
    candidates.append(Path.home() / "SOST" / "materials-engine-private")

    me_root: Optional[Path] = None
    for c in candidates:
        if c.exists() and (c / "src" / "multi_ai_review").is_dir():
            me_root = c
            break

    if me_root is None:
        raise ImportError(
            "cannot locate materials-engine-private. Set "
            "TRINITY_MATERIALS_ENGINE_PATH to its root path, or pass "
            "--allow-local-mock to use the inline deterministic mock "
            "(NOT recommended for v0.1; default is to fail loudly)."
        )

    src_path = str(me_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    try:
        from multi_ai_review.ai_council import AICouncil  # type: ignore[import-not-found]
        from multi_ai_review.council import (  # type: ignore[import-not-found]
            ValidatorMember,
            LocalKnowledgeMember,
            MockAIMember,
        )
        from multi_ai_review.hypothesis_schema import (  # type: ignore[import-not-found]
            Hypothesis,
            HypothesisScore,
        )
    except ImportError as e:
        raise ImportError(
            f"materials-engine-private located at {me_root} but the "
            f"multi_ai_review import failed: {e}."
        )

    return {
        "AICouncil": AICouncil,
        "Hypothesis": Hypothesis,
        "HypothesisScore": HypothesisScore,
        "members_classes": [
            ValidatorMember, LocalKnowledgeMember, MockAIMember,
        ],
        "engine_path": str(me_root),
    }


def _build_aoi_hypothesis(
    aoi: Dict[str, Any],
    council_module: Dict[str, Any],
) -> Any:
    """Build one ``Hypothesis(project='geaspirit', type='mineral_target')``
    from a geo scorecard entry. The hypothesis carries enough context
    for the council members to reason about prospectivity vs.
    speculation."""
    Hyp = council_module["Hypothesis"]
    HypScore = council_module["HypothesisScore"]

    score = float(aoi.get("score") or 0.0) / 100.0
    confidence = float(aoi.get("confidence") or 0.0)
    hyp_list = list(aoi.get("commodity_hypotheses") or [])
    open_qs = list(aoi.get("open_questions") or [])
    aoi_id = aoi.get("id", "unknown")
    name = aoi.get("name", "unknown AOI")
    region = aoi.get("region", "unknown")
    lat = aoi.get("center_lat")
    lon = aoi.get("center_lon")

    s = HypScore(
        novelty=round(score, 3),
        usefulness=min(1.0, max(0.0, len(hyp_list) / 3.0)),
        evidence_strength=round(confidence, 3),
        feasibility=0.5,
        strategic_value=round(score, 3),
        risk=round(max(0.0, 1.0 - confidence), 3),
        cost_score=0.5,
        uncertainty=round(max(0.0, 1.0 - max(score, confidence)), 3),
        final_score=round((score + confidence) / 2.0, 3),
    )

    coord = ""
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        coord = (
            f" centred at "
            f"({'S' if lat < 0 else 'N'}{abs(lat):.2f}, "
            f"{'W' if lon < 0 else 'E'}{abs(lon):.2f})"
        )

    if hyp_list:
        commodity_str = ", ".join(sorted(hyp_list))
    else:
        commodity_str = "unspecified primary commodity"

    claim = (
        f"AOI {aoi_id} in region {region}{coord} is a candidate for "
        f"{commodity_str} prospectivity. Autonomous AOI proposal, not "
        "a deposit confirmation. Remote proxy evidence only; requires "
        "field validation before any public claim."
    )

    return Hyp(
        project="geaspirit",
        type="mineral_target",
        title=f"{aoi_id}: {name}",
        subject=f"geaspirit|{region}|{aoi_id}",
        claim=claim,
        why_it_might_be_true=(
            f"Region {region!r} is on the v0.1 commodity-belt catalog "
            f"with proxy-score {score:.2f} and confidence "
            f"{confidence:.2f}; commodity hypotheses {hyp_list!r} "
            f"intersect belt primaries."
        ),
        evidence_needed=open_qs or [
            "field geological mapping",
            "drilling at AOI center",
            "depth-aware geophysics",
            "soil-geochemistry sampling",
        ],
        validation_path=[
            "remote_sensing_anomaly_review",
            "geophysics_layer_fusion",
            "field_validation_program",
        ],
        expected_value=(
            f"prospectivity_proxy={score:.2f}; "
            f"recommended next layers per scorecard"
        ),
        risk=(
            "remote-proxy candidate; no field, drilling or geophysics "
            "evidence on file"
        ),
        publishability="internal_only",
        score=s,
        metadata={
            "aoi_id": aoi_id,
            "region": region,
            "center_lat": lat,
            "center_lon": lon,
        },
    )


def _council_to_entry(
    aoi: Dict[str, Any],
    decision: Any,
    hypothesis: Any,
) -> Dict[str, Any]:
    reviews: List[Dict[str, Any]] = []
    for op in decision.opinions:
        member = op.get("member", "unknown") if isinstance(op, dict) else getattr(op, "member", "unknown")
        verdict = op.get("verdict", "insufficient") if isinstance(op, dict) else getattr(op, "verdict", "insufficient")
        rationale = op.get("rationale", "") if isinstance(op, dict) else getattr(op, "rationale", "")
        confidence = op.get("confidence", 0.0) if isinstance(op, dict) else getattr(op, "confidence", 0.0)
        reviews.append({
            "member": member,
            "verdict": verdict,
            "decision": _VERDICT_TO_DECISION.get(verdict, "hold"),
            "rationale": rationale,
            "confidence": round(float(confidence or 0.0), 3),
        })

    raw_decision = getattr(decision, "decision", "hold")
    dossier_decision = _COUNCIL_DECISION_TO_DOSSIER.get(raw_decision, "hold")

    validator_review = next(
        (r for r in reviews if "validator" in r["member"].lower()),
        None,
    )
    veto_applied = bool(
        validator_review
        and validator_review["verdict"] in ("contradicted", "disagree")
    )

    return {
        "aoi_id": aoi["id"],
        "name": aoi.get("name"),
        "region": aoi.get("region"),
        "center_lat": aoi.get("center_lat"),
        "center_lon": aoi.get("center_lon"),
        "bbox": aoi.get("bbox"),
        "commodity_hypotheses": list(aoi.get("commodity_hypotheses") or []),
        "score": aoi.get("score"),
        "confidence": aoi.get("confidence"),
        "evidence_level": aoi.get("evidence_level", "remote_proxy_only"),
        "reviews": reviews,
        "decision": dossier_decision,
        "council_raw_decision": raw_decision,
        "council_confidence": round(
            float(getattr(decision, "confidence", 0.0) or 0.0), 3,
        ),
        "council_agreement": list(getattr(decision, "agreement", []) or []),
        "council_disagreement": list(
            getattr(decision, "disagreement", []) or []
        ),
        "council_next_step": getattr(decision, "next_step", "") or "",
        "veto_applied": veto_applied,
        "evidence_gaps": list(aoi.get("open_questions") or []),
        "missing_evidence": list(aoi.get("missing_evidence") or []),
        "recommended_next_data_layers": list(
            aoi.get("recommended_next_data_layers") or []
        ),
        "hypothesis_hash": hypothesis.hypothesis_hash,
    }


# ---------------------------------------------------------------------------
# Legacy inline mock (escape hatch only)
# ---------------------------------------------------------------------------


def _mock_entry(aoi: Dict[str, Any]) -> Dict[str, Any]:
    score = float(aoi.get("score") or 0.0) / 100.0
    n_q = len(aoi.get("open_questions") or [])
    reviews: List[Dict[str, Any]] = []

    if score < _VALIDATOR_SCORE_REJECT:
        v = {"member": "validator", "verdict": "disagree", "decision": "reject",
             "rationale": f"score {score:.2f} below reject floor", "confidence": 0.7}
    elif score >= _VALIDATOR_SCORE_ACCEPT:
        v = {"member": "validator", "verdict": "agree", "decision": "accept",
             "rationale": f"score {score:.2f} clears accept threshold", "confidence": 0.7}
    else:
        v = {"member": "validator", "verdict": "insufficient", "decision": "hold",
             "rationale": f"score {score:.2f} between thresholds", "confidence": 0.5}
    reviews.append(v)

    if n_q > _EXPERT_MAX_OPEN_QUESTIONS:
        e = {"member": "geology_expert", "verdict": "insufficient", "decision": "hold",
             "rationale": f"{n_q} open evidence questions; hold", "confidence": 0.6}
    else:
        e = {"member": "geology_expert", "verdict": "agree", "decision": "accept",
             "rationale": "open-question count manageable", "confidence": 0.6}
    reviews.append(e)

    n = {"member": "novelty_judge", "verdict": "insufficient", "decision": "hold",
         "rationale": "every autonomous proposal carries novelty risk", "confidence": 0.5}
    reviews.append(n)

    decisions = [r["decision"] for r in reviews]
    if "reject" in decisions:
        final = "reject"
    elif "hold" in decisions:
        final = "hold"
    else:
        final = "accept"
    veto = (v["decision"] != "accept" and all(r["decision"] == "accept" for r in reviews[1:]))

    return {
        "aoi_id": aoi["id"],
        "name": aoi.get("name"),
        "region": aoi.get("region"),
        "center_lat": aoi.get("center_lat"),
        "center_lon": aoi.get("center_lon"),
        "bbox": aoi.get("bbox"),
        "commodity_hypotheses": list(aoi.get("commodity_hypotheses") or []),
        "score": aoi.get("score"),
        "confidence": aoi.get("confidence"),
        "evidence_level": aoi.get("evidence_level", "remote_proxy_only"),
        "reviews": reviews,
        "decision": final,
        "veto_applied": veto,
        "evidence_gaps": list(aoi.get("open_questions") or []),
        "missing_evidence": list(aoi.get("missing_evidence") or []),
        "recommended_next_data_layers": list(
            aoi.get("recommended_next_data_layers") or []
        ),
    }


# ---------------------------------------------------------------------------
# Public utilities
# ---------------------------------------------------------------------------


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check_no_host_paths(blob: str) -> None:
    leaked = [m for m in _HOST_PREFIXES if m in blob]
    if leaked:
        raise ValueError(
            f"refusing to emit dossier: host-path markers leaked into "
            f"canonical JSON: {leaked}"
        )


def build_dossier(
    *,
    campaign: str,
    generated_at_utc: str,
    scorecard_path: Path,
    allow_local_mock: bool = False,
) -> Dict[str, Any]:
    if not isinstance(campaign, str) or not campaign.strip():
        raise ValueError("campaign must be a non-empty string")
    if not isinstance(generated_at_utc, str) or not generated_at_utc.endswith(
        "+00:00"
    ):
        raise ValueError(
            "generated_at_utc must be an ISO-8601 string ending in +00:00"
        )
    if not scorecard_path.exists():
        raise FileNotFoundError(
            f"geo scorecard not found at {scorecard_path}"
        )

    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    if scorecard.get("schema") != _SCORECARD_SCHEMA:
        raise ValueError(
            f"scorecard at {scorecard_path.name} does not declare "
            f"schema {_SCORECARD_SCHEMA!r}; got "
            f"{scorecard.get('schema')!r}"
        )
    if scorecard.get("track") != _TRACK:
        raise ValueError(
            f"scorecard at {scorecard_path.name} is not a {_TRACK!r} "
            f"scorecard"
        )

    scorecard_sha = hashlib.sha256(
        scorecard_path.read_bytes()
    ).hexdigest()
    scorecard_schema = scorecard.get("schema", "")

    council_module: Optional[Dict[str, Any]] = None
    council_instance: Any = None
    if allow_local_mock:
        council_implementation = "inline_mock_v0"
        council_members_names = ["validator", "geology_expert", "novelty_judge"]
    else:
        council_module = _import_real_council()
        AICouncilCls = council_module["AICouncil"]
        members_classes = council_module["members_classes"]
        council_instance = AICouncilCls(
            members=[cls() for cls in members_classes],
            use_mock=False,
        )
        council_implementation = "real_sost_ai_free_tier"
        council_members_names = [
            getattr(cls, "name", cls.__name__).lower()
            for cls in members_classes
        ]

    aoi_entries: List[Dict[str, Any]] = []
    counts = {"accept": 0, "hold": 0, "reject": 0, "abstain": 0}
    veto_count = 0
    for aoi in scorecard.get("candidates", []):
        if allow_local_mock:
            entry = _mock_entry(aoi)
        else:
            hyp = _build_aoi_hypothesis(aoi, council_module)
            decision = council_instance.review(
                hyp, allow_network=False, allow_paid=False,
            )
            entry = _council_to_entry(aoi, decision, hyp)
        d = entry["decision"]
        counts[d] = counts.get(d, 0) + 1
        if entry.get("veto_applied"):
            veto_count += 1
        aoi_entries.append(entry)

    dossier = {
        "schema": _SCHEMA,
        "campaign": campaign,
        "track": _TRACK,
        "commodity": scorecard.get("commodity"),
        "generated_at_utc": generated_at_utc,
        "source": {
            "mode": "autonomous_v0.1",
            "scorecard_basename": scorecard_path.name,
            "scorecard_sha256": scorecard_sha,
            "scorecard_schema": scorecard_schema,
            "features_available": scorecard.get("features_available", 0),
            "council_implementation": council_implementation,
            "used_real_council": not allow_local_mock,
        },
        "council_members": council_members_names,
        "summary": {
            "aois_total": len(aoi_entries),
            "decisions_accept": counts.get("accept", 0),
            "decisions_hold": counts.get("hold", 0),
            "decisions_reject": counts.get("reject", 0),
            "decisions_abstain": counts.get("abstain", 0),
            "validator_vetoes_applied": veto_count,
        },
        "aois": aoi_entries,
    }

    blob = canonical_dumps(dossier)
    _check_no_host_paths(blob)
    return dossier


def render_markdown(dossier: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Geo Discovery — Dossier "
        f"`{dossier['campaign']}`"
    )
    lines.append("")
    impl = (dossier.get("source") or {}).get(
        "council_implementation", "unknown"
    )
    real = (impl == "real_sost_ai_free_tier")

    # Operator-required honesty disclaimer block — every required phrase
    # appears verbatim so the audit tests pick them up.
    lines.append(
        "> **AUTONOMOUS AOI PROPOSAL.** The AOIs in this dossier are "
        "**autonomous AOI proposal** entries generated from a pinned "
        "offline commodity-belt catalog and refined by the geo filter "
        "+ anomaly scorer. The evidence is **remote proxy evidence "
        "only**: there is **no field validation**, **no drilling "
        "evidence**, and **no confirmed mineralization** on file for "
        "any candidate. This dossier is **not a mineral reserve "
        "claim**. Every candidate **requires geological review before "
        "any public claim** can be made."
    )
    lines.append("")
    if real:
        lines.append(
            "> **REAL SOST AI COUNCIL.** Reviews below come from the "
            "canonical multi_ai_review AICouncil (free-tier members "
            "only: validator + local_knowledge + mock_ai). No "
            "network, no paid model calls, deterministic. Same engine "
            "used by the Materials Track v0.2 dossier."
        )
    else:
        lines.append(
            "> **INLINE MOCK COUNCIL.** Reviews below come from the "
            "v0 inline three-rule mock (escape hatch via "
            "--allow-local-mock). For offline-isolation only."
        )
    lines.append("")
    lines.append(f"- **Schema**: `{dossier['schema']}`")
    lines.append(f"- **Track**: `{dossier['track']}`")
    lines.append(f"- **Commodity**: `{dossier.get('commodity')}`")
    lines.append(
        f"- **Generated (UTC)**: {dossier['generated_at_utc']}"
    )
    src = dossier["source"]
    lines.append("- **Source**:")
    for k in sorted(src):
        lines.append(f"  - `{k}`: `{src[k]}`")
    lines.append("")
    s = dossier["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **aois_total**: `{s['aois_total']}`")
    lines.append(f"- **decisions_accept**: `{s['decisions_accept']}`")
    lines.append(f"- **decisions_hold**: `{s['decisions_hold']}`")
    lines.append(f"- **decisions_reject**: `{s['decisions_reject']}`")
    lines.append(
        f"- **decisions_abstain**: `{s.get('decisions_abstain', 0)}`"
    )
    lines.append(
        f"- **validator_vetoes_applied**: "
        f"`{s['validator_vetoes_applied']}`"
    )
    lines.append("")
    lines.append("## Top 20 AOIs by upstream score")
    lines.append("")
    top = sorted(
        dossier["aois"],
        key=lambda x: (-(x.get("score") or 0.0), x.get("aoi_id", "")),
    )[:20]
    for a in top:
        lat = a.get("center_lat")
        lon = a.get("center_lon")
        coord = (
            f"{lat:.2f}, {lon:.2f}"
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float))
            else "—"
        )
        lines.append(
            f"### `{a['aoi_id']}` &mdash; {a.get('name')} "
            f"(`{a.get('region')}`) &mdash; "
            f"**{a['decision'].upper()}**"
        )
        lines.append("")
        lines.append(
            f"- center=`{coord}`, score=`{a.get('score')}`, "
            f"confidence=`{a.get('confidence')}`, "
            f"veto_applied=`{a.get('veto_applied')}`"
        )
        if a.get("council_next_step"):
            lines.append(
                f"- council_next_step: {a['council_next_step']}"
            )
        lines.append("- **Reviews**:")
        for r in a.get("reviews", []):
            verdict_suffix = (
                f" (verdict={r.get('verdict')}, "
                f"confidence={r.get('confidence', '-')})"
                if "verdict" in r
                else ""
            )
            lines.append(
                f"  - `{r['member']}`: **{r['decision']}** &mdash; "
                f"{r['rationale']}{verdict_suffix}"
            )
        if a.get("evidence_gaps"):
            lines.append("- **Evidence gaps**:")
            for g in a["evidence_gaps"]:
                lines.append(f"  - {g}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="geo_dossier",
        description=(
            "Build a Trinity / Geo Discovery dossier from a geo "
            "scorecard. Uses the real SOST AI Council (free-tier) "
            "from multi_ai_review by default; never broadcasts."
        ),
    )
    p.add_argument(
        "--campaign", type=str, default="global_phase1",
    )
    p.add_argument(
        "--scorecard", type=str, default=None,
    )
    p.add_argument(
        "--generated-at-utc", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument("--out-json", type=str, default=None)
    p.add_argument("--out-md", type=str, default=None)
    p.add_argument(
        "--allow-local-mock", action="store_true",
        help=(
            "Fall back to the legacy inline mock if the real SOST AI "
            "Council is not available. NOT recommended."
        ),
    )
    args = p.parse_args(argv)

    scorecard_path = Path(
        args.scorecard
        or "TRINITY_GEO_SCORECARD_global_phase1.json"
    )
    out_json = Path(
        args.out_json or f"TRINITY_GEO_DOSSIER_{args.campaign}.json"
    )
    out_md = Path(
        args.out_md or f"TRINITY_GEO_DOSSIER_{args.campaign}.md"
    )

    dossier = build_dossier(
        campaign=args.campaign,
        generated_at_utc=args.generated_at_utc,
        scorecard_path=scorecard_path,
        allow_local_mock=args.allow_local_mock,
    )

    out_json.write_text(canonical_dumps(dossier), encoding="utf-8")
    out_md.write_text(render_markdown(dossier), encoding="utf-8")

    s = dossier["summary"]
    impl = dossier["source"]["council_implementation"]
    print(f"[geo-dossier] wrote {out_json}")
    print(f"[geo-dossier] wrote {out_md}")
    print(f"[geo-dossier] council: {impl}")
    print(
        f"[geo-dossier] decisions: "
        f"accept={s['decisions_accept']} "
        f"hold={s['decisions_hold']} "
        f"reject={s['decisions_reject']} "
        f"abstain={s.get('decisions_abstain', 0)} "
        f"vetoes={s['validator_vetoes_applied']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
