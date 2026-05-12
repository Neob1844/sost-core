#!/usr/bin/env python3
"""Trinity / SOST AI Orchestrator Adapter v0.1.

A thin coordinator that the Trinity Autonomous Orchestrator calls to
decide the next action across verticals.

Two execution paths
-------------------
1. Real council critic (default): if ``materials-engine-private`` is
   reachable (``TRINITY_MATERIALS_ENGINE_PATH`` or
   ``~/SOST/materials-engine-private``), the adapter constructs a
   ``Hypothesis`` for each candidate option and asks the free-tier
   ``AICouncil`` (Validator + LocalKnowledge + MockAI) to score them.
   The council is a *critic*, not an authority: its scores are
   combined with the deterministic heuristic.
2. Deterministic heuristic fallback: when the council cannot be
   imported, the adapter ranks options purely with the deterministic
   priority function. This keeps Trinity runnable on hosts that do
   not have the private repo (e.g. VPS, CI).

Hard rules
----------
- Free-tier members only; never instantiate a network or paid member.
- All inputs and decisions are returned to the caller so they can be
  written to ``TRINITY_AUTONOMY_LEDGER.jsonl``.
- The adapter NEVER mutates external state.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def canonical_dumps(obj: Any) -> str:
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def _sha16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _locate_real_council() -> Optional[Path]:
    me_env = os.environ.get("TRINITY_MATERIALS_ENGINE_PATH")
    candidates: List[Path] = []
    if me_env:
        candidates.append(Path(me_env))
    candidates.append(Path.home() / "SOST" / "materials-engine-private")
    for c in candidates:
        try:
            if c.exists() and (c / "src" / "multi_ai_review").is_dir():
                return c
        except OSError:
            continue
    return None


def _try_import_real_council() -> Optional[Dict[str, Any]]:
    """Attempt to import the real free-tier council. Returns None if
    materials-engine-private is not available — the caller falls back
    to the deterministic heuristic."""
    root = _locate_real_council()
    if root is None:
        return None
    me_src = root / "src"
    if str(me_src) not in sys.path:
        sys.path.insert(0, str(me_src))
    try:
        from multi_ai_review.ai_council import AICouncil  # type: ignore
        from multi_ai_review.hypothesis_schema import (  # type: ignore
            Hypothesis, HypothesisScore,
        )
        from multi_ai_review.members.validator_member import (  # type: ignore
            ValidatorMember,
        )
        from multi_ai_review.members.local_knowledge_member import (  # type: ignore
            LocalKnowledgeMember,
        )
        from multi_ai_review.members.mock_ai_member import (  # type: ignore
            MockAIMember,
        )
    except ImportError:
        return None

    members = [ValidatorMember(), LocalKnowledgeMember(), MockAIMember()]
    for m in members:
        if getattr(m, "requires_network", False):
            return None
        if getattr(m, "requires_paid", False):
            return None
    return {
        "AICouncil": AICouncil,
        "Hypothesis": Hypothesis,
        "HypothesisScore": HypothesisScore,
        "members": members,
    }


_DEFAULT_PRIORITY = {
    "geaspirit": 30,
    "materials_engine": 30,
    "useful_compute": 20,
    "sost_ai": 20,
}


def _deterministic_heuristic_rank(
    options: List[Dict[str, Any]],
) -> List[Tuple[Dict[str, Any], float]]:
    """Rank options by a transparent priority + score heuristic.

    Inputs are expected to look like::

        {"vertical": "geaspirit", "objective": "...",
         "candidate_id": "...", "score": 87.0,
         "evidence_strength": 0.5, "novelty": 0.7}

    Score is in 0..100 for geo, 0..1 for materials. We normalise:
    geo / 100; materials kept as is.
    """
    out: List[Tuple[Dict[str, Any], float]] = []
    for opt in options:
        vertical = opt.get("vertical", "")
        score = float(opt.get("score", 0.0))
        if vertical == "geaspirit":
            score_norm = score / 100.0
        else:
            score_norm = score
        priority = _DEFAULT_PRIORITY.get(vertical, 10)
        evidence = float(opt.get("evidence_strength", 0.0))
        novelty = float(opt.get("novelty", 0.0))
        # Weighted combination — kept simple so reviewers can audit it.
        rank = (
            0.40 * score_norm
            + 0.20 * evidence
            + 0.15 * novelty
            + 0.25 * (priority / 100.0)
        )
        out.append((opt, round(rank, 6)))
    out.sort(key=lambda kv: (-kv[1], kv[0].get("candidate_id", "")))
    return out


def _real_council_critic_score(
    council_bundle: Dict[str, Any],
    options: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Ask the free-tier council to score each option as a
    ``Hypothesis``. Returns ``{candidate_id: aggregated_score}``."""
    AICouncil = council_bundle["AICouncil"]
    Hypothesis = council_bundle["Hypothesis"]
    members = council_bundle["members"]
    council = AICouncil(members=members)

    scores: Dict[str, float] = {}
    for opt in options:
        cid = opt.get("candidate_id", "")
        hyp = Hypothesis(
            project="trinity_orchestrator",
            type="orchestrator_decision",
            id=cid,
            payload={
                "vertical": opt.get("vertical", ""),
                "objective": opt.get("objective", ""),
                "score": opt.get("score", 0.0),
                "evidence_strength": opt.get("evidence_strength", 0.0),
                "novelty": opt.get("novelty", 0.0),
            },
        )
        try:
            reviews = council.review(hyp)
        except Exception:  # pragma: no cover — defensive
            scores[cid] = 0.0
            continue
        # Reviews is a list[HypothesisScore]; aggregate as mean of
        # numeric "confidence" field if present, else 0.5.
        vals: List[float] = []
        for r in reviews:
            v = getattr(r, "confidence", None)
            if isinstance(v, (int, float)):
                vals.append(float(v))
        scores[cid] = sum(vals) / len(vals) if vals else 0.5
    return scores


def decide_next_action(
    *,
    options: List[Dict[str, Any]],
    use_real_council: bool = True,
) -> Dict[str, Any]:
    """Combine deterministic heuristic + (optional) real council critic
    into a single ranked decision."""
    if not options:
        return {
            "selected": None,
            "ranking": [],
            "council_used": False,
            "council_path": None,
            "reason": "no options provided",
        }

    heuristic = _deterministic_heuristic_rank(options)
    council_bundle = (
        _try_import_real_council() if use_real_council else None
    )

    council_path = None
    used_council = False
    if council_bundle is not None:
        used_council = True
        council_path = str(_locate_real_council())
        critic_scores = _real_council_critic_score(council_bundle, options)
        # Combine 70% heuristic + 30% council critic (free-tier is
        # informative, not authoritative).
        combined: List[Tuple[Dict[str, Any], float]] = []
        for opt, h in heuristic:
            cid = opt.get("candidate_id", "")
            c = critic_scores.get(cid, 0.5)
            combined_score = 0.70 * h + 0.30 * c
            combined.append((opt, round(combined_score, 6)))
        combined.sort(
            key=lambda kv: (-kv[1], kv[0].get("candidate_id", "")),
        )
        ranked = combined
    else:
        ranked = heuristic

    selected = ranked[0][0]
    return {
        "selected": selected,
        "ranking": [
            {"option": o, "rank_score": s} for (o, s) in ranked
        ],
        "council_used": used_council,
        "council_path": council_path,
        "reason": (
            "real free-tier council combined 70/30 with deterministic "
            "heuristic" if used_council
            else "deterministic heuristic only (council unavailable)"
        ),
    }
