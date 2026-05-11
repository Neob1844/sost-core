#!/usr/bin/env python3
"""Trinity / Materials Track — materials dossier builder (v0.2: real council).

Reads a ``TRINITY_MATERIALS_SCORECARD_<campaign>.json`` and runs each
candidate through the **real SOST AI Council** from
``materials-engine-private/src/multi_ai_review`` (free-tier members
only: ``ValidatorMember``, ``LocalKnowledgeMember``, ``MockAIMember``).
Emits ``TRINITY_MATERIALS_DOSSIER_<campaign>.json`` and a Markdown
sidecar.

This is the v0.2 refactor that replaces the previous inline mock
council (three hard-coded rules in this file) with the canonical
AICouncil used by Earth Track. The free-tier configuration is
deterministic (no LLM, no network, no paid calls) so the dossier and
the proof bundle SHA-256 remain byte-identical across machines given
the same scorecard and pinned UTC time.

Council resolution
------------------
- By default the builder imports ``multi_ai_review.ai_council.AICouncil``
  from ``$TRINITY_MATERIALS_ENGINE_PATH`` (falling back to
  ``~/SOST/materials-engine-private`` if the env var is unset).
- If the import fails, the builder **fails loudly** with a clear
  message. There is no silent fallback.
- The explicit escape hatch is ``--allow-local-mock`` on the CLI (or
  ``allow_local_mock=True`` on ``build_dossier``); when passed, the
  builder uses the legacy three-rule inline mock instead. This is
  retained for emergency offline use and for tests that need to
  exercise the codepath without ``multi_ai_review`` on sys.path.

Invariants
----------
- DRY-RUN. No network, no RPC, no subprocess, no wallet.
- Canonical JSON: byte-identical given the same pinned time and
  inputs. The free-tier council uses only deterministic Python logic
  (no LLM); we audited that the three free-tier member files contain
  zero ``random`` / ``datetime`` / ``time`` calls.
- Cross-machine reproducibility. ``source.scorecard_sha256`` +
  ``scorecard_basename`` instead of an absolute host path. The engine
  path is **not** stored in the JSON (only the boolean
  ``used_real_council`` is recorded) so the bundle does not leak the
  reviewer host.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


_SCHEMA = "trinity-materials-dossier/v0.2"
# Accept both the original v0 scorecard (fixed 5 demo candidates) and
# the v0.1 superset scorecard (autonomous N-candidate discovery output).
_SCORECARD_SCHEMAS_ACCEPTED = (
    "trinity-materials-scorecard/v0",
    "trinity-materials-scorecard/v0.1",
)
_TRACK = "materials"
_HOST_PREFIXES = ("/home/", "/opt/", "/Users/", "C:/", "C:\\")

# Thresholds for the legacy inline mock (used only when
# --allow-local-mock is passed).
_VALIDATOR_FRONTIER_ACCEPT = 0.70
_VALIDATOR_NOVELTY_ACCEPT = 0.60
_VALIDATOR_FRONTIER_REJECT = 0.50
_VALIDATOR_NOVELTY_REJECT = 0.35
_EXPERT_MAX_OPEN_QUESTIONS = 2
_NOVELTY_ACCEPT = 0.55
_NOVELTY_HOLD = 0.40

# Mapping council verdict → dossier decision space.
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
    """Locate materials-engine-private and import the canonical
    AICouncil + Hypothesis classes. Raises ``ImportError`` with a
    clear, actionable message when the engine cannot be found.

    Returns a dict with keys:
      - ``AICouncil``: AICouncil class
      - ``Hypothesis``: Hypothesis dataclass
      - ``HypothesisScore``: HypothesisScore dataclass
      - ``members_classes``: list of three free-tier member classes
      - ``engine_path``: resolved path (kept in memory only — never
        written to the dossier JSON)
    """
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
            "(NOT recommended for v0.2; default is to fail loudly)."
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
            f"multi_ai_review import failed: {e}. Verify the "
            f"multi_ai_review subdirectory is present and importable."
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


def _build_hypothesis(
    candidate: Dict[str, Any],
    council_module: Dict[str, Any],
) -> Any:
    """Translate one materials scorecard candidate into a
    ``multi_ai_review.hypothesis_schema.Hypothesis``."""
    Hyp = council_module["Hypothesis"]
    HypScore = council_module["HypothesisScore"]

    fp = float(candidate.get("seed_frontier_proximity") or 0.0)
    nv = float(candidate.get("seed_novelty") or 0.0)
    open_qs = list(candidate.get("open_questions") or [])
    industrial = list(candidate.get("industrial_hypotheses") or [])

    score = HypScore(
        novelty=nv,
        usefulness=min(1.0, max(0.0, len(industrial) / 3.0)),
        evidence_strength=fp,
        feasibility=0.5,
        strategic_value=0.5,
        risk=max(0.0, 1.0 - fp),
        cost_score=0.5,
        uncertainty=max(0.0, 1.0 - max(fp, nv)),
        final_score=round((fp + nv) / 2.0, 3),
    )

    cid = candidate.get("id", "unknown")
    formula = candidate.get("formula", "unknown")
    family = candidate.get("family", "unknown")
    title = f"{cid}: {formula} ({family})"
    subject = f"materials|{family}|{formula}|{cid}"

    if industrial:
        claim = (
            f"{formula} is a candidate {family} for applications including "
            f"{', '.join(sorted(industrial))}. Autonomous proposal, not a "
            "validated discovery."
        )
    else:
        claim = (
            f"{formula} is a candidate {family} composition. Autonomous "
            "proposal, not a validated discovery."
        )

    evidence_needed = open_qs or [
        "DFT formation energy",
        "MLIP relaxation baseline",
        "synthesis polymorph reference",
    ]

    return Hyp(
        project="materials",
        type="new_material_candidate",
        title=title,
        subject=subject,
        claim=claim,
        why_it_might_be_true=(
            f"composition passes the v0.1 chemistry filter; "
            f"frontier-proximity proxy is {fp:.2f}, novelty proxy is "
            f"{nv:.2f}; {len(open_qs)} open evidence questions on file"
        ),
        evidence_needed=evidence_needed,
        validation_path=[
            "mlip_relaxation",
            "dft_input_preparation",
            "synthesis_route_review",
        ],
        expected_value=(
            ", ".join(sorted(industrial)) if industrial
            else "industrial relevance to be assessed once chemistry validated"
        ),
        risk="autonomous candidate; no experimental or DFT validation",
        publishability="internal_only",
        score=score,
        metadata={"candidate_id": cid, "formula": formula, "family": family},
    )


def _council_to_entry(
    candidate: Dict[str, Any],
    decision: Any,
    hypothesis: Any,
) -> Dict[str, Any]:
    """Translate a ``CouncilDecision`` into the dossier per-hypothesis
    dict schema. Preserves both the raw council verdict per member and
    the translated dossier-level decision for backward-compat with the
    v0 schema consumers."""
    reviews: List[Dict[str, Any]] = []
    for op in decision.opinions:
        # CouncilDecision._aggregate already stores opinions as dicts
        # via to_dict() in ai_council.py, so op is a Mapping.
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

    # Validator veto detection: validator's own verdict was contradicted
    # or disagree (i.e. validator alone forced a non-accept outcome).
    validator_review = next(
        (r for r in reviews if "validator" in r["member"].lower()),
        None,
    )
    veto_applied = bool(
        validator_review
        and validator_review["verdict"] in ("contradicted", "disagree")
    )

    return {
        "candidate_id": candidate["id"],
        "formula": candidate["formula"],
        "family": candidate["family"],
        "seed_novelty": candidate.get("seed_novelty"),
        "seed_frontier_proximity": candidate.get("seed_frontier_proximity"),
        "reviews": reviews,
        "decision": dossier_decision,
        "council_raw_decision": raw_decision,
        "council_confidence": round(
            float(getattr(decision, "confidence", 0.0) or 0.0), 3
        ),
        "council_agreement": list(getattr(decision, "agreement", []) or []),
        "council_disagreement": list(
            getattr(decision, "disagreement", []) or []
        ),
        "council_next_step": getattr(decision, "next_step", "") or "",
        "council_unsupported_claims": list(
            getattr(decision, "unsupported_claims", []) or []
        ),
        "council_contradictions": list(
            getattr(decision, "contradictions", []) or []
        ),
        "veto_applied": veto_applied,
        "evidence_gaps": list(candidate.get("open_questions") or []),
        "hypothesis_hash": hypothesis.hypothesis_hash,
    }


# ---------------------------------------------------------------------------
# Legacy inline mock (escape hatch, --allow-local-mock only)
# ---------------------------------------------------------------------------


def _mock_review_validator(c: Dict[str, Any]) -> Dict[str, Any]:
    fp = float(c["seed_frontier_proximity"])
    nv = float(c["seed_novelty"])
    if fp < _VALIDATOR_FRONTIER_REJECT or nv < _VALIDATOR_NOVELTY_REJECT:
        return {
            "member": "validator",
            "verdict": "disagree",
            "decision": "reject",
            "rationale": (
                f"frontier_proximity {fp:.2f} and/or novelty {nv:.2f} "
                f"below calibration floor "
                f"({_VALIDATOR_FRONTIER_REJECT:.2f} / "
                f"{_VALIDATOR_NOVELTY_REJECT:.2f})"
            ),
            "confidence": 0.7,
        }
    if fp >= _VALIDATOR_FRONTIER_ACCEPT and nv >= _VALIDATOR_NOVELTY_ACCEPT:
        return {
            "member": "validator",
            "verdict": "agree",
            "decision": "accept",
            "rationale": (
                f"frontier_proximity {fp:.2f} and novelty {nv:.2f} both "
                f"clear validator thresholds "
                f"({_VALIDATOR_FRONTIER_ACCEPT:.2f} / "
                f"{_VALIDATOR_NOVELTY_ACCEPT:.2f})"
            ),
            "confidence": 0.7,
        }
    return {
        "member": "validator",
        "verdict": "insufficient",
        "decision": "hold",
        "rationale": (
            f"insufficient baseline; frontier_proximity {fp:.2f} or "
            f"novelty {nv:.2f} below accept thresholds but above the "
            f"reject floor"
        ),
        "confidence": 0.5,
    }


def _mock_review_materials_expert(c: Dict[str, Any]) -> Dict[str, Any]:
    family = c.get("family", "")
    n_q = len(c.get("open_questions") or [])
    if "reference" in family.lower():
        return {
            "member": "materials_expert",
            "verdict": "insufficient",
            "decision": "hold",
            "rationale": (
                f"family {family!r} marked as reference / calibration "
                f"anchor; not advanced past hold without an explicit "
                f"campaign goal"
            ),
            "confidence": 0.6,
        }
    if n_q > _EXPERT_MAX_OPEN_QUESTIONS:
        return {
            "member": "materials_expert",
            "verdict": "insufficient",
            "decision": "hold",
            "rationale": (
                f"{n_q} open synthesis / characterization questions; "
                f"more than the {_EXPERT_MAX_OPEN_QUESTIONS} the mock "
                f"reviewer will advance past hold"
            ),
            "confidence": 0.6,
        }
    return {
        "member": "materials_expert",
        "verdict": "agree",
        "decision": "accept",
        "rationale": (
            "open-question count is manageable and family is not a "
            "reference anchor; expert sees no blocker for further work"
        ),
        "confidence": 0.65,
    }


def _mock_review_novelty_judge(c: Dict[str, Any]) -> Dict[str, Any]:
    nv = float(c["seed_novelty"])
    if nv >= _NOVELTY_ACCEPT:
        return {
            "member": "novelty_judge",
            "verdict": "agree",
            "decision": "accept",
            "rationale": (
                f"seed_novelty {nv:.2f} >= {_NOVELTY_ACCEPT:.2f}; "
                f"frontier-worthy in the mock scale"
            ),
            "confidence": 0.6,
        }
    if nv >= _NOVELTY_HOLD:
        return {
            "member": "novelty_judge",
            "verdict": "insufficient",
            "decision": "hold",
            "rationale": (
                f"seed_novelty {nv:.2f} in [{_NOVELTY_HOLD:.2f}, "
                f"{_NOVELTY_ACCEPT:.2f}); not enough novelty to advance"
            ),
            "confidence": 0.55,
        }
    return {
        "member": "novelty_judge",
        "verdict": "disagree",
        "decision": "reject",
        "rationale": (
            f"seed_novelty {nv:.2f} < {_NOVELTY_HOLD:.2f}; treated as "
            f"calibration / reference, not a discovery candidate"
        ),
        "confidence": 0.6,
    }


def _mock_combine(reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
    decisions = [r["decision"] for r in reviews]
    if "reject" in decisions:
        final = "reject"
    elif "hold" in decisions:
        final = "hold"
    else:
        final = "accept"
    validator = next(r for r in reviews if r["member"] == "validator")
    others = [r["decision"] for r in reviews if r["member"] != "validator"]
    veto_applied = False
    if validator["decision"] != "accept" and all(
        d == "accept" for d in others
    ):
        veto_applied = True
    return {"decision": final, "veto_applied": veto_applied}


def _mock_entry(c: Dict[str, Any]) -> Dict[str, Any]:
    """Build a per-candidate dossier entry using the legacy inline mock."""
    reviews = [
        _mock_review_validator(c),
        _mock_review_materials_expert(c),
        _mock_review_novelty_judge(c),
    ]
    combined = _mock_combine(reviews)
    return {
        "candidate_id": c["id"],
        "formula": c["formula"],
        "family": c["family"],
        "seed_novelty": c.get("seed_novelty"),
        "seed_frontier_proximity": c.get("seed_frontier_proximity"),
        "reviews": reviews,
        "decision": combined["decision"],
        "veto_applied": combined["veto_applied"],
        "evidence_gaps": list(c.get("open_questions") or []),
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
    live_mode: bool = False,  # legacy CLI flag, kept for back-compat
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
            f"materials scorecard not found at {scorecard_path}"
        )

    if live_mode:
        # The old --live-materials-engine flag now has the OPPOSITE
        # default behaviour: real council is enabled unless --allow-
        # local-mock is passed. We keep the legacy flag silent.
        pass

    scorecard = json.loads(scorecard_path.read_text(encoding="utf-8"))
    if scorecard.get("schema") not in _SCORECARD_SCHEMAS_ACCEPTED:
        raise ValueError(
            f"scorecard at {scorecard_path.name} does not declare a "
            f"supported schema; expected one of "
            f"{_SCORECARD_SCHEMAS_ACCEPTED!r}, got "
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

    # Resolve the council. Real council is the default; --allow-local-
    # mock is the only escape.
    council_module: Optional[Dict[str, Any]] = None
    council_instance: Any = None
    council_implementation: str
    council_members_names: List[str]
    if allow_local_mock:
        council_implementation = "inline_mock_v0"
        council_members_names = ["validator", "materials_expert", "novelty_judge"]
    else:
        council_module = _import_real_council()
        AICouncilCls = council_module["AICouncil"]
        members_classes = council_module["members_classes"]
        council_instance = AICouncilCls(
            members=[cls() for cls in members_classes],
            use_mock=False,  # all three free-tier members already added
        )
        council_implementation = "real_sost_ai_free_tier"
        council_members_names = [
            getattr(cls, "name", cls.__name__).lower()
            for cls in members_classes
        ]

    hypotheses: List[Dict[str, Any]] = []
    counts = {"accept": 0, "hold": 0, "reject": 0, "abstain": 0}
    veto_count = 0

    for c in scorecard.get("candidates", []):
        if allow_local_mock:
            entry = _mock_entry(c)
        else:
            hyp = _build_hypothesis(c, council_module)
            decision = council_instance.review(
                hyp, allow_network=False, allow_paid=False,
            )
            entry = _council_to_entry(c, decision, hyp)
        d = entry["decision"]
        counts[d] = counts.get(d, 0) + 1
        if entry.get("veto_applied"):
            veto_count += 1
        hypotheses.append(entry)

    # Mode discriminator. v0 scorecards came from the fixed 5-candidate
    # mock; v0.1 scorecards came from the autonomous generator. v0.2
    # adds council_implementation so a reader can tell at a glance
    # whether the reviews are from the real SOST AI free-tier council
    # or from the inline mock escape hatch.
    source_mode = (
        "autonomous_v0.1"
        if scorecard_schema == "trinity-materials-scorecard/v0.1"
        else "mock_v0"
    )
    source_block = {
        "mode": source_mode,
        "scorecard_basename": scorecard_path.name,
        "scorecard_sha256": scorecard_sha,
        "scorecard_schema": scorecard_schema,
        "features_available": scorecard.get("features_available", 0),
        "council_implementation": council_implementation,
        "used_real_council": not allow_local_mock,
    }

    dossier = {
        "schema": _SCHEMA,
        "campaign": campaign,
        "track": _TRACK,
        "generated_at_utc": generated_at_utc,
        "source": source_block,
        "council_members": council_members_names,
        "summary": {
            "candidates_total": len(hypotheses),
            "decisions_accept": counts.get("accept", 0),
            "decisions_hold": counts.get("hold", 0),
            "decisions_reject": counts.get("reject", 0),
            "decisions_abstain": counts.get("abstain", 0),
            "validator_vetoes_applied": veto_count,
        },
        "hypotheses": hypotheses,
    }

    blob = canonical_dumps(dossier)
    _check_no_host_paths(blob)
    return dossier


def render_markdown(dossier: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(
        f"# Trinity / Materials Track — Dossier "
        f"`{dossier['campaign']}`"
    )
    lines.append("")
    src_mode = (dossier.get("source") or {}).get("mode")
    council_impl = (
        dossier.get("source") or {}
    ).get("council_implementation", "unknown")
    real = (council_impl == "real_sost_ai_free_tier")
    if src_mode == "autonomous_v0.1":
        lines.append(
            "> **AUTONOMOUS CANDIDATE PROPOSAL.** The hypotheses in this "
            "dossier are **autonomous candidate proposal** entries "
            "produced by Trinity / Materials Discovery from a pinned "
            "seed and a closed chemistry filter. They are **not "
            "experimentally validated**, **not DFT validated**, **not "
            "a patent claim**, and **not a commercial performance "
            "claim**. Each candidate **requires Useful Compute / DFT "
            "/ synthesis review** before any further claim can be made."
        )
        lines.append("")
        if real:
            lines.append(
                "> **REAL SOST AI COUNCIL.** Reviews below come from "
                "the canonical multi_ai_review AICouncil (free-tier "
                "members only: validator + local_knowledge + mock_ai). "
                "No network, no paid model calls, deterministic. Same "
                "engine used by Earth Track."
            )
        else:
            lines.append(
                "> **INLINE MOCK COUNCIL.** Reviews below come from "
                "the v0 inline three-rule mock (escape hatch via "
                "--allow-local-mock). Not the canonical AICouncil. "
                "For demonstration / offline-isolation only."
            )
    else:
        if real:
            lines.append(
                "> **DRY-RUN dossier.** Real SOST AI Council "
                "(free-tier) reviews of the candidate set declared in "
                "the materials scorecard. Not a materials discovery "
                "claim."
            )
        else:
            lines.append(
                "> **DRY-RUN dossier.** Inline mock-council reviews "
                "of the candidate set declared in the materials "
                "scorecard. Not a materials discovery claim. Inline "
                "mock — use --allow-local-mock only when the real "
                "council is unavailable."
            )
    lines.append("")
    lines.append(f"- **Schema**: `{dossier['schema']}`")
    lines.append(f"- **Track**: `{dossier['track']}`")
    lines.append(f"- **Generated (UTC)**: {dossier['generated_at_utc']}")
    src = dossier["source"]
    lines.append("- **Source**:")
    for k in sorted(src):
        lines.append(f"  - `{k}`: `{src[k]}`")
    lines.append("")
    s = dossier["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **candidates_total**: `{s['candidates_total']}`")
    lines.append(f"- **decisions_accept**: `{s['decisions_accept']}`")
    lines.append(f"- **decisions_hold**: `{s['decisions_hold']}`")
    lines.append(f"- **decisions_reject**: `{s['decisions_reject']}`")
    if "decisions_abstain" in s:
        lines.append(
            f"- **decisions_abstain**: `{s['decisions_abstain']}`"
        )
    lines.append(
        f"- **validator_vetoes_applied**: "
        f"`{s['validator_vetoes_applied']}`"
    )
    lines.append("")
    lines.append("## Hypotheses")
    lines.append("")
    for h in dossier["hypotheses"]:
        lines.append(
            f"### `{h['candidate_id']}` &mdash; {h['formula']} "
            f"({h['family']}) &mdash; **{h['decision'].upper()}**"
        )
        lines.append("")
        nv = h.get("seed_novelty")
        fp = h.get("seed_frontier_proximity")
        nv_s = f"{nv:.2f}" if isinstance(nv, (int, float)) else "n/a"
        fp_s = f"{fp:.2f}" if isinstance(fp, (int, float)) else "n/a"
        line = (
            f"- seed_novelty=`{nv_s}`, "
            f"seed_frontier_proximity=`{fp_s}`, "
            f"veto_applied=`{h.get('veto_applied')}`"
        )
        if "council_confidence" in h:
            line += f", council_confidence=`{h['council_confidence']}`"
        lines.append(line)
        if h.get("council_next_step"):
            lines.append(
                f"- council_next_step: {h['council_next_step']}"
            )
        lines.append("- **Reviews**:")
        for r in h["reviews"]:
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
        if h.get("evidence_gaps"):
            lines.append("- **Evidence gaps**:")
            for g in h["evidence_gaps"]:
                lines.append(f"  - {g}")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="materials_dossier",
        description=(
            "Build a Trinity / Materials Track dossier from a materials "
            "scorecard. Uses the real SOST AI Council (free-tier) from "
            "multi_ai_review by default; never broadcasts."
        ),
    )
    p.add_argument(
        "--campaign", type=str, default="novel_frontier_phase1",
    )
    p.add_argument(
        "--scorecard", type=str, default=None,
        help=(
            "Path to TRINITY_MATERIALS_SCORECARD_<campaign>.json. "
            "Defaults to TRINITY_MATERIALS_SCORECARD_<campaign>.json "
            "in the current directory."
        ),
    )
    p.add_argument(
        "--generated-at-utc", type=str,
        default="2026-05-10T00:00:00+00:00",
    )
    p.add_argument(
        "--out-json", type=str, default=None,
    )
    p.add_argument(
        "--out-md", type=str, default=None,
    )
    p.add_argument(
        "--allow-local-mock", action="store_true",
        help=(
            "Fall back to the legacy inline three-rule mock if the real "
            "SOST AI Council is not available. NOT recommended; the "
            "default is to fail loudly when multi_ai_review cannot be "
            "imported."
        ),
    )
    p.add_argument(
        "--live-materials-engine", action="store_true",
        help=(
            "Legacy flag from v0; ignored in v0.2 (real council is "
            "now the default)."
        ),
    )
    args = p.parse_args(argv)

    scorecard_path = Path(
        args.scorecard
        or f"TRINITY_MATERIALS_SCORECARD_{args.campaign}.json"
    )
    out_json = Path(
        args.out_json
        or f"TRINITY_MATERIALS_DOSSIER_{args.campaign}.json"
    )
    out_md = Path(
        args.out_md
        or f"TRINITY_MATERIALS_DOSSIER_{args.campaign}.md"
    )

    dossier = build_dossier(
        campaign=args.campaign,
        generated_at_utc=args.generated_at_utc,
        scorecard_path=scorecard_path,
        allow_local_mock=args.allow_local_mock,
        live_mode=args.live_materials_engine,
    )

    out_json.write_text(canonical_dumps(dossier), encoding="utf-8")
    out_md.write_text(render_markdown(dossier), encoding="utf-8")

    s = dossier["summary"]
    impl = dossier["source"]["council_implementation"]
    print(f"[materials_dossier] wrote {out_json}")
    print(f"[materials_dossier] wrote {out_md}")
    print(f"[materials_dossier] council: {impl}")
    print(
        f"[materials_dossier] decisions: "
        f"accept={s['decisions_accept']} "
        f"hold={s['decisions_hold']} "
        f"reject={s['decisions_reject']} "
        f"abstain={s.get('decisions_abstain', 0)} "
        f"vetoes={s['validator_vetoes_applied']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
